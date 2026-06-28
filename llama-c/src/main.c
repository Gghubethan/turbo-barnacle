/* main.c — CLI for the pure-C int8 LLaMA-2 inference engine.
 *
 * Loads a quantized model + tokenizer, encodes the prompt, then autoregressively
 * decodes tokens with a KV cache, streaming each piece to stdout as soon as it
 * is produced. */
#include "model.h"
#include "tokenizer.h"
#include "sampler.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <ctype.h>

static long time_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000L + ts.tv_nsec / 1000000L;
}

/* Print a decoded piece, skipping unprintable control bytes (except \n \t). */
static void emit(const char *piece) {
    if (!piece || piece[0] == '\0') return;
    if (piece[1] == '\0') {
        unsigned char c = piece[0];
        if (!(isprint(c) || c == '\n' || c == '\t' || c == ' ')) {
            if (c < 0x20) return;  /* drop stray control bytes */
        }
    }
    fputs(piece, stdout);
    fflush(stdout);
}

static void generate(Transformer *t, Tokenizer *tok, Sampler *sampler,
                     const char *prompt, int steps) {
    int *prompt_tokens = malloc((strlen(prompt) + 3) * sizeof(int));
    int n_prompt = 0;
    tokenizer_encode(tok, prompt, /*bos=*/1, /*eos=*/0, prompt_tokens, &n_prompt);
    if (n_prompt < 1) {
        fprintf(stderr, "error: empty prompt after encoding\n");
        exit(EXIT_FAILURE);
    }

    long t_start = 0;
    int token = prompt_tokens[0];
    int pos = 0;
    int generated = 0;

    while (pos < steps) {
        float *logits = model_forward(t, token, pos);

        int next;
        if (pos < n_prompt - 1) {
            next = prompt_tokens[pos + 1];   /* still feeding the prompt */
        } else {
            next = sampler_sample(sampler, logits);
            generated++;
        }
        pos++;

        if (next == 2) break;                /* EOS ends the sequence */

        emit(tokenizer_decode(tok, token, next));
        token = next;

        if (pos == n_prompt) t_start = time_ms();  /* start timing after prompt */
    }
    printf("\n");

    if (generated > 1 && t_start) {
        long elapsed = time_ms() - t_start;
        if (elapsed > 0)
            fprintf(stderr, "\n[%d tokens, %.1f tok/s]\n",
                    generated, (generated - 1) / (elapsed / 1000.0));
        else
            fprintf(stderr, "\n[%d tokens]\n", generated);
    }
    free(prompt_tokens);
}

static void usage(const char *prog) {
    fprintf(stderr,
        "usage: %s <model.bin> [options]\n"
        "  -z <path>   tokenizer file (default: tokenizer.bin)\n"
        "  -i <text>   prompt text (default: \"\")\n"
        "  -n <int>    max steps to run (default: 256)\n"
        "  -t <float>  temperature, 0 = greedy (default: 1.0)\n"
        "  -p <float>  top-p nucleus sampling (default: 0.9)\n"
        "  -s <int>    RNG seed (default: time-based)\n",
        prog);
    exit(EXIT_FAILURE);
}

int main(int argc, char **argv) {
    if (argc < 2) usage(argv[0]);

    const char *model_path = argv[1];
    const char *tok_path = "tokenizer.bin";
    const char *prompt = "";
    int steps = 256;
    float temperature = 1.0f;
    float topp = 0.9f;
    unsigned long long seed = (unsigned long long)time(NULL);

    for (int i = 2; i + 1 < argc; i += 2) {
        char *flag = argv[i], *val = argv[i + 1];
        if (flag[0] != '-' || flag[2] != '\0') usage(argv[0]);
        switch (flag[1]) {
            case 'z': tok_path = val; break;
            case 'i': prompt = val; break;
            case 'n': steps = atoi(val); break;
            case 't': temperature = atof(val); break;
            case 'p': topp = atof(val); break;
            case 's': seed = strtoull(val, NULL, 10); break;
            default: usage(argv[0]);
        }
    }
    if (temperature < 0.0f) temperature = 0.0f;

    Transformer transformer;
    transformer.fd = -1;
    transformer.mapped_data = NULL;
    model_load(&transformer, model_path);

    if (steps <= 0 || steps > transformer.config.seq_len)
        steps = transformer.config.seq_len;

    Tokenizer tokenizer;
    tokenizer_load(&tokenizer, tok_path, transformer.config.vocab_size);

    Sampler sampler;
    sampler_init(&sampler, transformer.config.vocab_size, temperature, topp, seed);

    fprintf(stderr,
        "model: dim=%d layers=%d heads=%d kv_heads=%d vocab=%d seq_len=%d\n",
        transformer.config.dim, transformer.config.n_layers,
        transformer.config.n_heads, transformer.config.n_kv_heads,
        transformer.config.vocab_size, transformer.config.seq_len);

    generate(&transformer, &tokenizer, &sampler, prompt, steps);

    sampler_free(&sampler);
    tokenizer_free(&tokenizer);
    model_free(&transformer);
    return 0;
}
