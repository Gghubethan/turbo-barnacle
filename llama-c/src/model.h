/* model.h — LLaMA-2 transformer: config, weights, KV-cached forward pass.
 *
 * Architecture (LLaMA-2): token embedding -> N decoder blocks -> RMSNorm ->
 * classifier. Each block is: RMSNorm, multi-head self-attention with RoPE and
 * a KV cache, residual add, RMSNorm, SwiGLU feed-forward, residual add.
 * Grouped-query attention is supported via n_kv_heads <= n_heads. */
#ifndef LLAMA_MODEL_H
#define LLAMA_MODEL_H

#include "quant.h"
#include <sys/types.h>

typedef struct {
    int dim;          /* transformer hidden size (e.g. 4096 for 7B)        */
    int hidden_dim;   /* SwiGLU inner size       (e.g. 11008 for 7B)       */
    int n_layers;     /* number of decoder blocks (32 for 7B)              */
    int n_heads;      /* number of query heads   (32 for 7B)               */
    int n_kv_heads;   /* number of key/value heads (<= n_heads for GQA)    */
    int vocab_size;   /* token vocabulary size   (32000 for LLaMA-2)       */
    int seq_len;      /* max sequence length the cache is sized for        */
} Config;

/* All learned parameters. Matmul weights are int8-quantized; the small RMSNorm
 * vectors stay in fp32 because they are cheap and accuracy-sensitive. */
typedef struct {
    QuantizedTensor *q_tokens;  /* (vocab_size, dim) token embeddings        */
    float *token_embedding;     /* dequantized embedding scratch (vocab,dim) */

    float *rms_att;             /* (n_layers, dim)  attention RMSNorm gain    */
    float *rms_ffn;             /* (n_layers, dim)  ffn RMSNorm gain          */
    float *rms_final;           /* (dim,)           final RMSNorm gain        */

    QuantizedTensor *wq;        /* (n_layers, dim, n_heads*head_size)         */
    QuantizedTensor *wk;        /* (n_layers, dim, n_kv_heads*head_size)      */
    QuantizedTensor *wv;        /* (n_layers, dim, n_kv_heads*head_size)      */
    QuantizedTensor *wo;        /* (n_layers, n_heads*head_size, dim)         */

    QuantizedTensor *w1;        /* (n_layers, hidden_dim, dim)  gate          */
    QuantizedTensor *w2;        /* (n_layers, dim, hidden_dim)  down          */
    QuantizedTensor *w3;        /* (n_layers, hidden_dim, dim)  up            */

    QuantizedTensor *wcls;      /* (vocab_size, dim) classifier (may share)   */
} Weights;

/* Per-step activation buffers and the persistent KV cache. */
typedef struct {
    float *x;        /* (dim,)        residual stream                         */
    float *xb;       /* (dim,)        scratch after a sublayer                */
    float *xb2;      /* (dim,)        scratch                                 */
    float *hb;       /* (hidden_dim,) ffn scratch (gate)                      */
    float *hb2;      /* (hidden_dim,) ffn scratch (up)                        */
    QuantizedTensor xq;  /* quantized x for dim-sized matmuls                 */
    QuantizedTensor hq;  /* quantized x for hidden_dim-sized matmuls          */
    float *q;        /* (dim,)        query                                   */
    float *att;      /* (n_heads, seq_len) attention scores                   */
    float *logits;   /* (vocab_size,) output logits                           */
    float *key_cache;   /* (n_layers, seq_len, kv_dim) cached keys            */
    float *value_cache; /* (n_layers, seq_len, kv_dim) cached values          */
} RunState;

typedef struct {
    Config config;
    Weights weights;
    RunState state;
    /* memory-mapped file backing the weights, freed on unload */
    float *mapped_data;
    ssize_t file_size;
    int fd;
} Transformer;

/* Load a quantized model file (see tools/export.py for the format). Exits the
 * process with a message on any error. */
void model_load(Transformer *t, const char *path);

/* Release all model memory and the mmap. */
void model_free(Transformer *t);

/* Run one decoding step for `token` at sequence position `pos`, returning a
 * pointer to the (vocab_size,) logits owned by the transformer state. */
float *model_forward(Transformer *t, int token, int pos);

#endif /* LLAMA_MODEL_H */
