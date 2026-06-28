/* quant.h — group-wise symmetric int8 quantization (Q8 style).
 *
 * Weights and activations are stored as int8 values plus one fp32 scale per
 * group of GS contiguous elements. A value v is recovered as: v = q * scale.
 * The scale for a group is max(|x|) / 127, so the largest-magnitude element in
 * the group maps to ±127 and quantization error stays bounded per group.
 *
 * Using a per-group scale (rather than one scale per tensor) keeps accuracy
 * high for LLaMA-2 7B while cutting weight memory ~4x versus fp32. */
#ifndef LLAMA_QUANT_H
#define LLAMA_QUANT_H

#include <stdint.h>

/* Number of elements that share a single fp32 scale. Must divide every
 * quantized dimension in the model. 32 and 64 are common; 64 trades a touch
 * of accuracy for a smaller scale table. The value baked into a model file is
 * authoritative and is checked against this at load time. */
#ifndef GS
#define GS 64
#endif

/* A quantized tensor: int8 payload + one scale per group of GS elements. */
typedef struct {
    int8_t *q;   /* quantized values, length = number of elements          */
    float  *s;   /* scales,           length = number of elements / GS      */
} QuantizedTensor;

/* Dequantize all `n` elements of `qt` into `out` (caller-allocated, n floats). */
void dequantize(const QuantizedTensor *qt, float *out, int n);

/* Quantize `n` floats from `x` into `qt` (qt->q and qt->s pre-allocated).
 * `n` must be a multiple of GS. */
void quantize(QuantizedTensor *qt, const float *x, int n);

/* W (d rows x n cols, quantized) times x (n, quantized) -> out (d, fp32).
 * out[i] = sum_j W[i,j] * x[j], computed in the int8 domain group by group and
 * rescaled by the product of the two group scales. This is the hot path. */
void matmul_q8(float *out, const QuantizedTensor *x, const QuantizedTensor *w,
               int n, int d);

#endif /* LLAMA_QUANT_H */
