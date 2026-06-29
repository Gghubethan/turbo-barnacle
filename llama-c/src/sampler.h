/* sampler.h — turn logits into the next token id.
 *
 * Supports greedy (argmax) when temperature == 0, otherwise temperature
 * scaling followed by nucleus (top-p) sampling. A small xorshift RNG keeps
 * generation reproducible from a seed without pulling in libc rand state. */
#ifndef LLAMA_SAMPLER_H
#define LLAMA_SAMPLER_H

typedef struct {
    float prob;
    int   index;
} ProbIndex;

typedef struct {
    int vocab_size;
    ProbIndex *probindex;   /* scratch for top-p sorting */
    float temperature;
    float topp;
    unsigned long long rng_state;
} Sampler;

void sampler_init(Sampler *s, int vocab_size, float temperature, float topp,
                  unsigned long long seed);
void sampler_free(Sampler *s);

/* Sample the next token id from `logits` (length vocab_size, modified in place
 * when temperature > 0). */
int sampler_sample(Sampler *s, float *logits);

#endif /* LLAMA_SAMPLER_H */
