#!/usr/bin/env python3
"""Export a Hugging Face LLaMA-2 checkpoint to the engine's int8 model format.

    python3 tools/export.py meta-llama/Llama-2-7b-hf llama2_7b_q8.bin

Reads the model with `transformers` (so you need `torch` + `transformers`
installed and access to the weights), quantizes every matmul weight to int8
with group size GS, keeps RMSNorm weights in fp32, and writes the binary the C
loader in src/model.c expects (header version 2).

Run this once on a machine with enough RAM (~16 GB for 7B); the resulting file
is ~7 GB and runs on CPU via `build/llama`.
"""
import argparse
import struct
import sys

try:
    import torch
except ImportError:
    sys.exit("export.py needs PyTorch: pip install torch transformers")

GS = 64          # group size; must match the C build's -DGS
MAGIC = 0x616b3432
VERSION = 2


def quantize_group(w, qmax, group_size=GS):
    """Symmetric group quantization, identical math to quant.c."""
    assert w.numel() % group_size == 0
    w = w.float().reshape(-1, group_size)
    wmax = w.abs().max(dim=1, keepdim=True).values
    scale = wmax / qmax
    q = torch.where(scale > 0, w / scale, torch.zeros_like(w))
    q = q.round().clamp(-qmax, qmax)
    deq = q.float() * scale                 # for the error report
    err = (deq - w).abs().max().item()
    return q.reshape(-1).to(torch.int32), scale.reshape(-1), err


def serialize_q8(f, w):
    q, s, err = quantize_group(w, 127)
    f.write(q.to(torch.int8).numpy().tobytes())     # int8 payload
    f.write(s.numpy().astype("float32").tobytes())  # fp32 scales
    return err


def serialize_q4(f, w):
    """Pack two 4-bit weights per byte (low nibble even, high nibble odd)."""
    q, s, err = quantize_group(w, 7)
    qi = q.to(torch.int32) & 0x0F                    # 4-bit two's complement
    lo = qi[0::2]
    hi = qi[1::2]
    packed = (lo | (hi << 4)).to(torch.uint8)
    f.write(packed.numpy().tobytes())
    f.write(s.numpy().astype("float32").tobytes())
    return err


def serialize_fp32(f, w):
    f.write(w.float().contiguous().numpy().astype("float32").tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", help="HF model id or local path")
    ap.add_argument("out", help="output .bin path")
    ap.add_argument("--q4", action="store_true",
                    help="4-bit weights (~8x smaller than fp32) instead of int8")
    args = ap.parse_args()
    quant_type = 1 if args.q4 else 0
    serialize_weight = serialize_q4 if args.q4 else serialize_q8

    from transformers import AutoModelForCausalLM
    print(f"loading {args.model} ...", file=sys.stderr)
    model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=torch.float32)
    model.eval()
    cfg = model.config
    p = model.state_dict()

    dim = cfg.hidden_size
    hidden_dim = cfg.intermediate_size
    n_layers = cfg.num_hidden_layers
    n_heads = cfg.num_attention_heads
    n_kv_heads = getattr(cfg, "num_key_value_heads", n_heads)
    vocab_size = cfg.vocab_size
    seq_len = getattr(cfg, "max_position_embeddings", 4096)
    head_size = dim // n_heads

    # HF stores wq/wk with a permutation for its RoPE; undo it so the simple
    # interleaved RoPE in model.c is correct.
    def unpermute(w, n_h):
        return (w.view(n_h, 2, w.shape[0] // n_h // 2, w.shape[1])
                 .transpose(1, 2).reshape(w.shape[0], w.shape[1]))

    shared = torch.equal(p["model.embed_tokens.weight"], p["lm_head.weight"]) \
        if "lm_head.weight" in p else True

    print(f"dim={dim} layers={n_layers} heads={n_heads} kv_heads={n_kv_heads} "
          f"hidden={hidden_dim} vocab={vocab_size} shared_cls={shared}",
          file=sys.stderr)

    with open(args.out, "wb") as f:
        # header[9] packs shared_classifier (byte 0) and quant_type (byte 1)
        flags = (1 if shared else 0) | (quant_type << 8)
        header = struct.pack("<10i", MAGIC, VERSION, dim, hidden_dim, n_layers,
                             n_heads, n_kv_heads, vocab_size, seq_len, flags)
        header += struct.pack("<i", GS)
        f.write(header)
        f.write(b"\x00" * (256 - len(header)))

        # fp32 RMSNorm weights
        for l in range(n_layers):
            serialize_fp32(f, p[f"model.layers.{l}.input_layernorm.weight"])
        for l in range(n_layers):
            serialize_fp32(f, p[f"model.layers.{l}.post_attention_layernorm.weight"])
        serialize_fp32(f, p["model.norm.weight"])

        max_err = 0.0
        def q(w):
            nonlocal max_err
            max_err = max(max_err, serialize_weight(f, w))

        # quantized weights, in the loader's expected order
        q(p["model.embed_tokens.weight"])                                   # q_tokens
        for l in range(n_layers):
            q(unpermute(p[f"model.layers.{l}.self_attn.q_proj.weight"], n_heads))
        for l in range(n_layers):
            q(unpermute(p[f"model.layers.{l}.self_attn.k_proj.weight"], n_kv_heads))
        for l in range(n_layers):
            q(p[f"model.layers.{l}.self_attn.v_proj.weight"])
        for l in range(n_layers):
            q(p[f"model.layers.{l}.self_attn.o_proj.weight"])
        for l in range(n_layers):
            q(p[f"model.layers.{l}.mlp.gate_proj.weight"])                  # w1
        for l in range(n_layers):
            q(p[f"model.layers.{l}.mlp.down_proj.weight"])                  # w2
        for l in range(n_layers):
            q(p[f"model.layers.{l}.mlp.up_proj.weight"])                    # w3
        if not shared:
            q(p["lm_head.weight"])

    print(f"wrote {args.out}  ({'Q4' if args.q4 else 'Q8'}, "
          f"worst-case quant error {max_err:.4f})", file=sys.stderr)


if __name__ == "__main__":
    main()
