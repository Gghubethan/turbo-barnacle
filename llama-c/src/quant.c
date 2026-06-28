#include "quant.h"
#include <math.h>

#if defined(__AVX2__)
#include <immintrin.h>
_Static_assert(GS % 16 == 0, "AVX2 int8 path needs GS to be a multiple of 16");

/* Signed int8 dot product over `n` elements (n a multiple of 16) -> int32.
 * Widen bytes to int16, multiply-add adjacent pairs into int32 lanes, then
 * horizontally reduce. Matches the scalar accumulation exactly (no rounding). */
static inline int32_t dot_i8_avx2(const int8_t *a, const int8_t *b, int n) {
    __m256i acc = _mm256_setzero_si256();
    for (int k = 0; k < n; k += 16) {
        __m256i a16 = _mm256_cvtepi8_epi16(_mm_loadu_si128((const __m128i *)(a + k)));
        __m256i b16 = _mm256_cvtepi8_epi16(_mm_loadu_si128((const __m128i *)(b + k)));
        acc = _mm256_add_epi32(acc, _mm256_madd_epi16(a16, b16));
    }
    __m128i s = _mm_add_epi32(_mm256_castsi256_si128(acc),
                              _mm256_extracti128_si256(acc, 1));
    s = _mm_hadd_epi32(s, s);
    s = _mm_hadd_epi32(s, s);
    return _mm_cvtsi128_si32(s);
}
#endif

void dequantize(const QuantizedTensor *qt, float *out, int n) {
    for (int i = 0; i < n; i++) {
        out[i] = qt->q[i] * qt->s[i / GS];
    }
}

void quantize(QuantizedTensor *qt, const float *x, int n) {
    const int num_groups = n / GS;
    const float q_max = 127.0f;

    for (int g = 0; g < num_groups; g++) {
        const float *xg = x + g * GS;

        /* group scale from the largest magnitude in the group */
        float wmax = 0.0f;
        for (int i = 0; i < GS; i++) {
            float a = fabsf(xg[i]);
            if (a > wmax) wmax = a;
        }
        float scale = wmax / q_max;
        qt->s[g] = scale;

        /* round-to-nearest into [-127, 127]; guard against scale == 0 */
        int8_t *qg = qt->q + g * GS;
        for (int i = 0; i < GS; i++) {
            float v = (scale > 0.0f) ? (xg[i] / scale) : 0.0f;
            int q = (int)lroundf(v);
            if (q > 127) q = 127;
            if (q < -127) q = -127;
            qg[i] = (int8_t)q;
        }
    }
}

void matmul_q8(float *out, const QuantizedTensor *x, const QuantizedTensor *w,
               int n, int d) {
    /* Each output row i is the dot product of weight row i with x.
     * We accumulate int8*int8 products into a 32-bit integer within a group,
     * then fold in the two fp32 group scales once per group. This keeps the
     * inner loop in cheap integer arithmetic. */
#if defined(_OPENMP)
#pragma omp parallel for schedule(static)
#endif
    for (int i = 0; i < d; i++) {
        float val = 0.0f;
        const int row = i * n;             /* offset of weight row i */
        const int8_t *wq = w->q + row;
        const float  *ws = w->s + row / GS;
        const int8_t *xq = x->q;
        const float  *xs = x->s;

        for (int g = 0; g < n; g += GS) {
#if defined(__AVX2__)
            int32_t ig = dot_i8_avx2(wq + g, xq + g, GS);
#else
            int32_t ig = 0;
            for (int k = 0; k < GS; k++) {
                ig += (int32_t)wq[g + k] * (int32_t)xq[g + k];
            }
#endif
            val += (float)ig * ws[g / GS] * xs[g / GS];
        }
        out[i] = val;
    }
}
