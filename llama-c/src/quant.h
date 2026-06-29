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
 * rescaled by the product of the two group scales. This is the hot path; it
 * uses an AVX-512 or AVX2 int8 dot product when available, else a scalar loop
 * (all three are bit-for-bit identical — integer accumulation). */
void matmul_q8(float *out, const QuantizedTensor *x, const QuantizedTensor *w,
               int n, int d);

/* ---- 4-bit (Q4) weight quantization -------------------------------------
 * Same per-group symmetric scheme, but each weight is stored in 4 bits, so two
 * weights pack into one byte: low nibble = even element, high nibble = odd.
 * Values quantize to [-7, 7] (scale = max|group| / 7) and are kept as 4-bit
 * two's complement. This halves weight memory again vs Q8 (~8x vs fp32) at some
 * accuracy cost. Activations stay Q8; matmul_q4 multiplies Q4 weights by a Q8
 * activation vector. */
typedef struct {
    uint8_t *q;  /* packed nibbles, length = number of elements / 2 */
    float   *s;  /* scales,         length = number of elements / GS */
} Q4Tensor;

void dequantize_q4(const Q4Tensor *qt, float *out, int n);
void quantize_q4(Q4Tensor *qt, const float *x, int n);

/* Q4 weight W (d x n) times Q8 activation x (n) -> out (d, fp32). */
void matmul_q4(float *out, const QuantizedTensor *x, const Q4Tensor *w,
               int n, int d);

#endif /* LLAMA_QUANT_H */
