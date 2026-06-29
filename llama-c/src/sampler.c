#include "sampler.h"

#include <stdlib.h>
#include <math.h>

static int argmax(const float *v, int n) {
    int best = 0;
    for (int i = 1; i < n; i++) if (v[i] > v[best]) best = i;
    return best;
}

static void softmax(float *x, int n) {
    float maxv = x[0];
    for (int i = 1; i < n; i++) if (x[i] > maxv) maxv = x[i];
    float sum = 0.0f;
    for (int i = 0; i < n; i++) { x[i] = expf(x[i] - maxv); sum += x[i]; }
    for (int i = 0; i < n; i++) x[i] /= sum;
}

/* xorshift64*, returns a float in [0,1) */
static float random_f32(unsigned long long *state) {
    unsigned long long x = *state;
    x ^= x >> 12; x ^= x << 25; x ^= x >> 27;
    *state = x;
    return ((x * 0x2545F4914F6CDD1Dull) >> 40) / (float)(1u << 24);
}

static int prob_cmp(const void *a, const void *b) {
    float pa = ((ProbIndex *)a)->prob, pb = ((ProbIndex *)b)->prob;
    return (pa < pb) - (pa > pb);     /* descending */
}

/* Sample from the smallest set of tokens whose cumulative prob exceeds topp. */
static int sample_topp(const float *prob, int n, float topp, ProbIndex *buf,
                       float coin) {
    int n0 = 0;
    /* prefilter: drop tokens that cannot be in the nucleus */
    const float cutoff = (1.0f - topp) / (n - 1);
    for (int i = 0; i < n; i++) {
        if (prob[i] >= cutoff) {
            buf[n0].index = i;
            buf[n0].prob = prob[i];
            n0++;
        }
    }
    qsort(buf, n0, sizeof(ProbIndex), prob_cmp);

    float cum = 0.0f;
    int last = n0 - 1;
    for (int i = 0; i < n0; i++) {
        cum += buf[i].prob;
        if (cum > topp) { last = i; break; }
    }

    float r = coin * cum;
    float c = 0.0f;
    for (int i = 0; i <= last; i++) {
        c += buf[i].prob;
        if (r < c) return buf[i].index;
    }
    return buf[last].index;
}

void sampler_init(Sampler *s, int vocab_size, float temperature, float topp,
                  unsigned long long seed) {
    s->vocab_size = vocab_size;
    s->temperature = temperature;
    s->topp = topp;
    s->rng_state = seed ? seed : 0x9E3779B97F4A7C15ull;
    s->probindex = malloc(vocab_size * sizeof(ProbIndex));
}

void sampler_free(Sampler *s) { free(s->probindex); }

int sampler_sample(Sampler *s, float *logits) {
    if (s->temperature == 0.0f) return argmax(logits, s->vocab_size);

    for (int i = 0; i < s->vocab_size; i++) logits[i] /= s->temperature;
    softmax(logits, s->vocab_size);

    float coin = random_f32(&s->rng_state);
    if (s->topp <= 0.0f || s->topp >= 1.0f) {
        /* plain multinomial sample over the full distribution */
        float r = coin, cdf = 0.0f;
        for (int i = 0; i < s->vocab_size; i++) {
            cdf += logits[i];
            if (r < cdf) return i;
        }
        return s->vocab_size - 1;
    }
    return sample_topp(logits, s->vocab_size, s->topp, s->probindex, coin);
}
