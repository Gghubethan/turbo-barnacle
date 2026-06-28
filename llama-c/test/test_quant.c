/* test_quant.c — numerical unit tests for the int8 quantization path.
 *
 * The smoke test (make test) proves the engine *runs*; this proves the int8
 * math is *correct*: quantize/dequantize round-trips within the group-scale
 * error bound, and matmul_q8 tracks a plain fp32 matmul closely. Build & run
 * via `make check`. Exits non-zero on the first failed assertion. */
#include "../src/quant.h"

#include <stdio.h>
#include <stdlib.h>
#include <math.h>

static unsigned long long rng = 0x123456789abcdefULL;
static float frand(void) {            /* uniform in [-1, 1) */
    rng ^= rng >> 12; rng ^= rng << 25; rng ^= rng >> 27;
    return ((rng * 0x2545F4914F6CDD1DULL) >> 40) / (float)(1u << 23) - 1.0f;
}

static int failures = 0;
#define CHECK(cond, ...) do { \
    if (!(cond)) { printf("FAIL: " __VA_ARGS__); printf("\n"); failures++; } \
    else         { printf("ok:   " __VA_ARGS__); printf("\n"); } \
} while (0)

/* Round-trip: dequant(quant(x)) must stay within scale/2 per element, i.e.
 * absolute error <= max|group|/254. */
static void test_roundtrip(void) {
    const int n = 4 * GS;
    float *x = malloc(n * sizeof(float));
    float *y = malloc(n * sizeof(float));
    QuantizedTensor qt = { malloc(n), malloc((n / GS) * sizeof(float)) };

    for (int i = 0; i < n; i++) x[i] = frand() * 3.0f;
    quantize(&qt, x, n);
    dequantize(&qt, y, n);

    float max_err = 0.0f;
    for (int g = 0; g < n / GS; g++) {
        float gmax = 0.0f;
        for (int i = 0; i < GS; i++) {
            float a = fabsf(x[g * GS + i]);
            if (a > gmax) gmax = a;
        }
        float bound = gmax / 254.0f + 1e-6f;
        for (int i = 0; i < GS; i++) {
            float e = fabsf(x[g * GS + i] - y[g * GS + i]);
            if (e > max_err) max_err = e;
            if (e > bound) { printf("  elem %d err %.6f > bound %.6f\n",
                                    g * GS + i, e, bound); failures++; }
        }
    }
    CHECK(1, "roundtrip within per-group bound (max abs err %.6f)", max_err);
    free(x); free(y); free(qt.q); free(qt.s);
}

/* matmul_q8 vs an fp32 reference matmul on the same data. Relative error of
 * the whole output vector (L2) should be small — int8 keeps ~1% per operand. */
static void test_matmul(void) {
    const int n = 8 * GS;   /* inner dim */
    const int d = 64;       /* rows      */

    float *xf = malloc(n * sizeof(float));
    float *wf = malloc((size_t)d * n * sizeof(float));
    float *ref = malloc(d * sizeof(float));
    float *got = malloc(d * sizeof(float));

    QuantizedTensor xq = { malloc(n), malloc((n / GS) * sizeof(float)) };
    QuantizedTensor wq = { malloc((size_t)d * n),
                           malloc(((size_t)d * n / GS) * sizeof(float)) };

    for (int i = 0; i < n; i++) xf[i] = frand();
    for (int i = 0; i < d * n; i++) wf[i] = frand();

    /* fp32 reference */
    for (int i = 0; i < d; i++) {
        float acc = 0.0f;
        for (int j = 0; j < n; j++) acc += wf[i * n + j] * xf[j];
        ref[i] = acc;
    }

    /* quantized path */
    quantize(&xq, xf, n);
    quantize(&wq, wf, d * n);
    matmul_q8(got, &xq, &wq, n, d);

    double num = 0.0, den = 0.0, maxabs = 0.0;
    for (int i = 0; i < d; i++) {
        double e = got[i] - ref[i];
        num += e * e;
        den += (double)ref[i] * ref[i];
        if (fabs(e) > maxabs) maxabs = fabs(e);
    }
    double rel = sqrt(num / (den + 1e-12));
    CHECK(rel < 0.03, "matmul_q8 vs fp32: L2 rel err %.4f (< 0.03), max abs %.4f",
          rel, maxabs);

    free(xf); free(wf); free(ref); free(got);
    free(xq.q); free(xq.s); free(wq.q); free(wq.s);
}

/* A constant vector quantizes exactly (all elements equal the group max). */
static void test_exact_constant(void) {
    const int n = 2 * GS;
    float *x = malloc(n * sizeof(float));
    float *y = malloc(n * sizeof(float));
    QuantizedTensor qt = { malloc(n), malloc((n / GS) * sizeof(float)) };
    for (int i = 0; i < n; i++) x[i] = 0.5f;
    quantize(&qt, x, n);
    dequantize(&qt, y, n);
    float max_err = 0.0f;
    for (int i = 0; i < n; i++) {
        float e = fabsf(x[i] - y[i]);
        if (e > max_err) max_err = e;
    }
    CHECK(max_err < 1e-6f, "constant vector quantizes exactly (err %.2e)", max_err);
    free(x); free(y); free(qt.q); free(qt.s);
}

int main(void) {
    printf("== int8 quantization unit tests (GS=%d) ==\n", GS);
    test_roundtrip();
    test_exact_constant();
    test_matmul();
    if (failures) { printf("\n%d check(s) FAILED\n", failures); return 1; }
    printf("\nall checks passed\n");
    return 0;
}
