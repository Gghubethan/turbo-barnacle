#include "quant.h"
#include <math.h>

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
            int32_t ig = 0;
            for (int k = 0; k < GS; k++) {
                ig += (int32_t)wq[g + k] * (int32_t)xq[g + k];
            }
            val += (float)ig * ws[g / GS] * xs[g / GS];
        }
        out[i] = val;
    }
}
