#include "model.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/stat.h>

/* ---- model file format ----------------------------------------------------
 * Header (256 bytes, zero-padded):
 *   int32 magic   = 0x616b3432  ("ak42")
 *   int32 version = 2
 *   int32 dim, hidden_dim, n_layers, n_heads, n_kv_heads, vocab_size, seq_len
 *   uint8 shared_classifier   (1 = wcls shares the token-embedding weights)
 *   int32 group_size          (must equal GS this binary was built with)
 * Body:
 *   fp32 rms_att   (n_layers*dim)
 *   fp32 rms_ffn   (n_layers*dim)
 *   fp32 rms_final (dim)
 *   then, for each quantized tensor in order
 *     {q_tokens, wq, wk, wv, wo, w1, w2, w3, [wcls if not shared]}:
 *       int8  q[n]
 *       fp32  s[n/GS]
 * See tools/export.py for the writer. ------------------------------------- */

#define MODEL_MAGIC   0x616b3432
#define MODEL_VERSION 2

static void die(const char *msg) {
    fprintf(stderr, "model: %s\n", msg);
    exit(EXIT_FAILURE);
}

static void *xcalloc(size_t n, size_t sz) {
    void *p = calloc(n, sz);
    if (!p) die("out of memory");
    return p;
}

/* Read `count` weight matrices laid out back-to-back starting at *ptr, each of
 * `each` elements, in the model's quantization (q4 = 1 for int4, else int8).
 * Advances *ptr past the data it consumes. */
static Linear *map_weights(void **ptr, int count, int each, int q4) {
    void *p = *ptr;
    Linear *w = xcalloc(count, sizeof(Linear));
    for (int i = 0; i < count; i++) {
        w[i].q4 = q4;
        if (q4) {
            w[i].q4t.q = (uint8_t *)p;
            p = (uint8_t *)p + each / 2;       /* packed nibbles */
            w[i].q4t.s = (float *)p;
        } else {
            w[i].q8.q = (int8_t *)p;
            p = (int8_t *)p + each;             /* int8 payload   */
            w[i].q8.s = (float *)p;
        }
        p = (float *)p + each / GS;            /* fp32 scales     */
    }
    *ptr = p;
    return w;
}

static void alloc_state(RunState *s, const Config *c) {
    int kv_dim = (c->dim * c->n_kv_heads) / c->n_heads;
    s->x   = xcalloc(c->dim, sizeof(float));
    s->xb  = xcalloc(c->dim, sizeof(float));
    s->xb2 = xcalloc(c->dim, sizeof(float));
    s->hb  = xcalloc(c->hidden_dim, sizeof(float));
    s->hb2 = xcalloc(c->hidden_dim, sizeof(float));
    s->xq.q = xcalloc(c->dim, sizeof(int8_t));
    s->xq.s = xcalloc(c->dim / GS, sizeof(float));
    s->hq.q = xcalloc(c->hidden_dim, sizeof(int8_t));
    s->hq.s = xcalloc(c->hidden_dim / GS, sizeof(float));
    s->q   = xcalloc(c->dim, sizeof(float));
    s->att = xcalloc((size_t)c->n_heads * c->seq_len, sizeof(float));
    s->logits = xcalloc(c->vocab_size, sizeof(float));
    s->key_cache   = xcalloc((size_t)c->n_layers * c->seq_len * kv_dim, sizeof(float));
    s->value_cache = xcalloc((size_t)c->n_layers * c->seq_len * kv_dim, sizeof(float));
}

static void free_state(RunState *s) {
    free(s->x); free(s->xb); free(s->xb2); free(s->hb); free(s->hb2);
    free(s->xq.q); free(s->xq.s); free(s->hq.q); free(s->hq.s);
    free(s->q); free(s->att); free(s->logits);
    free(s->key_cache); free(s->value_cache);
}

void model_load(Transformer *t, const char *path) {
    Config *c = &t->config;
    Weights *w = &t->weights;

    FILE *f = fopen(path, "rb");
    if (!f) die("could not open model file");

    int32_t header[10];
    if (fread(header, sizeof(int32_t), 10, f) != 10) die("truncated header");
    if (header[0] != MODEL_MAGIC)   die("bad magic (not a llama-c model)");
    if (header[1] != MODEL_VERSION) die("unsupported model version");
    c->dim        = header[2];
    c->hidden_dim = header[3];
    c->n_layers   = header[4];
    c->n_heads    = header[5];
    c->n_kv_heads = header[6];
    c->vocab_size = header[7];
    c->seq_len    = header[8];
    /* header[9] packs shared_classifier (byte 0) and quant_type (byte 1),
     * followed by GS. quant_type: 0 = Q8 (int8), 1 = Q4 (int4). */
    uint8_t shared_classifier = header[9] & 0xff;
    c->quant_type = (header[9] >> 8) & 0xff;
    if (c->quant_type != 0 && c->quant_type != 1) die("unknown quant_type");
    int q4 = c->quant_type;
    int32_t group_size;
    if (fread(&group_size, sizeof(int32_t), 1, f) != 1) die("truncated header");
    if (group_size != GS)
        die("model group_size does not match this build's GS (rebuild with matching GS)");

    /* mmap the whole file; weights are read straight out of the mapping */
    int fd = open(path, O_RDONLY);
    if (fd == -1) die("could not reopen model file");
    struct stat st;
    if (fstat(fd, &st) != 0) die("fstat failed");
    t->file_size = st.st_size;
    void *data = mmap(NULL, t->file_size, PROT_READ, MAP_PRIVATE, fd, 0);
    if (data == MAP_FAILED) die("mmap failed");
    t->fd = fd;
    t->mapped_data = data;
    fclose(f);

    int head_size = c->dim / c->n_heads;
    int kv_dim    = head_size * c->n_kv_heads;

    /* body begins after the 256-byte header */
    void *p = (char *)data + 256;

    /* fp32 RMSNorm weights first */
    w->rms_att = (float *)p;   p = (float *)p + (size_t)c->n_layers * c->dim;
    w->rms_ffn = (float *)p;   p = (float *)p + (size_t)c->n_layers * c->dim;
    w->rms_final = (float *)p; p = (float *)p + c->dim;

    /* quantized tensors */
    w->q_tokens = map_weights(&p, 1, c->vocab_size * c->dim, q4);
    w->wq = map_weights(&p, c->n_layers, c->dim * (c->n_heads * head_size), q4);
    w->wk = map_weights(&p, c->n_layers, c->dim * kv_dim, q4);
    w->wv = map_weights(&p, c->n_layers, c->dim * kv_dim, q4);
    w->wo = map_weights(&p, c->n_layers, (c->n_heads * head_size) * c->dim, q4);
    w->w1 = map_weights(&p, c->n_layers, c->dim * c->hidden_dim, q4);
    w->w2 = map_weights(&p, c->n_layers, c->hidden_dim * c->dim, q4);
    w->w3 = map_weights(&p, c->n_layers, c->dim * c->hidden_dim, q4);
    w->wcls = shared_classifier ? w->q_tokens
                                : map_weights(&p, 1, c->vocab_size * c->dim, q4);

    /* dequantize the token embedding table once (used by gather, not matmul) */
    w->token_embedding = xcalloc((size_t)c->vocab_size * c->dim, sizeof(float));
    if (q4) dequantize_q4(&w->q_tokens->q4t, w->token_embedding, c->vocab_size * c->dim);
    else    dequantize(&w->q_tokens->q8, w->token_embedding, c->vocab_size * c->dim);

    alloc_state(&t->state, c);
}

void model_free(Transformer *t) {
    Weights *w = &t->weights;
    free(w->token_embedding);
    free(w->q_tokens);
    free(w->wq); free(w->wk); free(w->wv); free(w->wo);
    free(w->w1); free(w->w2); free(w->w3);
    if (w->wcls != w->q_tokens) free(w->wcls);
    free_state(&t->state);
    if (t->mapped_data) munmap(t->mapped_data, t->file_size);
    if (t->fd != -1) close(t->fd);
}

/* RMSNorm: o = x / sqrt(mean(x^2) + eps) * gain */
static void rmsnorm(float *o, const float *x, const float *gain, int size) {
    float ss = 0.0f;
    for (int i = 0; i < size; i++) ss += x[i] * x[i];
    ss = 1.0f / sqrtf(ss / size + 1e-5f);
    for (int i = 0; i < size; i++) o[i] = gain[i] * (ss * x[i]);
}

/* Quantized linear: out(d) = W(d x n) * x(n), dispatching on the weight's
 * quantization. Activation x is always Q8. */
static void linear(float *out, const QuantizedTensor *x, const Linear *w,
                   int n, int d) {
    if (w->q4) matmul_q4(out, x, &w->q4t, n, d);
    else       matmul_q8(out, x, &w->q8,  n, d);
}

/* Numerically stable in-place softmax over the first `size` elements. */
static void softmax(float *x, int size) {
    float maxv = x[0];
    for (int i = 1; i < size; i++) if (x[i] > maxv) maxv = x[i];
    float sum = 0.0f;
    for (int i = 0; i < size; i++) { x[i] = expf(x[i] - maxv); sum += x[i]; }
    for (int i = 0; i < size; i++) x[i] /= sum;
}

float *model_forward(Transformer *t, int token, int pos) {
    const Config *c = &t->config;
    const Weights *w = &t->weights;
    RunState *s = &t->state;

    const int dim = c->dim;
    const int head_size = dim / c->n_heads;
    const int kv_dim = head_size * c->n_kv_heads;
    const int kv_mul = c->n_heads / c->n_kv_heads;  /* GQA query-per-kv ratio */
    const int hidden_dim = c->hidden_dim;
    const float inv_sqrt_hs = 1.0f / sqrtf((float)head_size);

    /* gather the token embedding into the residual stream */
    memcpy(s->x, w->token_embedding + (size_t)token * dim, dim * sizeof(float));

    for (int l = 0; l < c->n_layers; l++) {
        /* --- attention --- */
        rmsnorm(s->xb, s->x, w->rms_att + l * dim, dim);

        /* project to q,k,v. k/v are written straight into the cache at pos. */
        size_t kv_off = (size_t)l * c->seq_len * kv_dim + (size_t)pos * kv_dim;
        float *k = s->key_cache + kv_off;
        float *v = s->value_cache + kv_off;
        quantize(&s->xq, s->xb, dim);
        linear(s->q, &s->xq, &w->wq[l], dim, dim);
        linear(k,    &s->xq, &w->wk[l], dim, kv_dim);
        linear(v,    &s->xq, &w->wv[l], dim, kv_dim);

        /* RoPE: rotate each adjacent (even,odd) pair in q and k by position. */
        for (int i = 0; i < dim; i += 2) {
            int hd = i % head_size;
            float freq = 1.0f / powf(10000.0f, (float)hd / (float)head_size);
            float val = pos * freq;
            float fcr = cosf(val), fci = sinf(val);
            /* always rotate q; rotate k only within the kv_dim span */
            int rotn = (i < kv_dim) ? 2 : 1;
            for (int r = 0; r < rotn; r++) {
                float *vec = (r == 0) ? s->q : k;
                float v0 = vec[i], v1 = vec[i + 1];
                vec[i]     = v0 * fcr - v1 * fci;
                vec[i + 1] = v0 * fci + v1 * fcr;
            }
        }

        /* multi-head attention over cached keys/values up to pos */
#if defined(_OPENMP)
#pragma omp parallel for schedule(static)
#endif
        for (int h = 0; h < c->n_heads; h++) {
            const float *qh = s->q + h * head_size;
            float *att = s->att + (size_t)h * c->seq_len;
            const float *kv_base_k =
                s->key_cache + (size_t)l * c->seq_len * kv_dim
                + (size_t)(h / kv_mul) * head_size;
            const float *kv_base_v =
                s->value_cache + (size_t)l * c->seq_len * kv_dim
                + (size_t)(h / kv_mul) * head_size;

            for (int tpos = 0; tpos <= pos; tpos++) {
                const float *kh = kv_base_k + (size_t)tpos * kv_dim;
                float score = 0.0f;
                for (int i = 0; i < head_size; i++) score += qh[i] * kh[i];
                att[tpos] = score * inv_sqrt_hs;
            }
            softmax(att, pos + 1);

            float *out = s->xb + h * head_size;
            memset(out, 0, head_size * sizeof(float));
            for (int tpos = 0; tpos <= pos; tpos++) {
                const float *vh = kv_base_v + (size_t)tpos * kv_dim;
                float a = att[tpos];
                for (int i = 0; i < head_size; i++) out[i] += a * vh[i];
            }
        }

        /* output projection and residual add */
        quantize(&s->xq, s->xb, dim);
        linear(s->xb2, &s->xq, &w->wo[l], dim, dim);
        for (int i = 0; i < dim; i++) s->x[i] += s->xb2[i];

        /* --- feed-forward (SwiGLU): w2( silu(w1 x) * (w3 x) ) --- */
        rmsnorm(s->xb, s->x, w->rms_ffn + l * dim, dim);
        quantize(&s->xq, s->xb, dim);
        linear(s->hb,  &s->xq, &w->w1[l], dim, hidden_dim);
        linear(s->hb2, &s->xq, &w->w3[l], dim, hidden_dim);
        for (int i = 0; i < hidden_dim; i++) {
            float x = s->hb[i];
            s->hb[i] = (x / (1.0f + expf(-x))) * s->hb2[i];  /* SiLU * gate */
        }
        quantize(&s->hq, s->hb, hidden_dim);
        linear(s->xb, &s->hq, &w->w2[l], hidden_dim, dim);
        for (int i = 0; i < dim; i++) s->x[i] += s->xb[i];
    }

    /* final norm + classifier -> logits */
    rmsnorm(s->x, s->x, w->rms_final, dim);
    quantize(&s->xq, s->x, dim);
    linear(s->logits, &s->xq, w->wcls, dim, c->vocab_size);
    return s->logits;
}
