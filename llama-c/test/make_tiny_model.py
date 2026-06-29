#!/usr/bin/env python3
"""Generate a tiny synthetic model + tokenizer in the engine's binary formats.

This produces a randomly-initialised, structurally-valid LLaMA-2 model so the
C engine can be exercised end to end (load -> encode -> KV-cached decode ->
stream -> decode tokens) without needing the real 13 GB of 7B weights. The
output is gibberish text by design; it only proves the plumbing works.

Pure standard library (no numpy/torch) so it runs anywhere CI does.
"""
import struct
import sys
import math
import random

GS = 64  # must match the C build's -DGS

# Tiny but structurally faithful config. Every quantized dimension is a
# multiple of GS, exactly as required by the loader.
DIM        = 64
HIDDEN_DIM = 128
N_LAYERS   = 2
N_HEADS    = 4
N_KV_HEADS = 4
SEQ_LEN    = 64
HEAD_SIZE  = DIM // N_HEADS
KV_DIM     = HEAD_SIZE * N_KV_HEADS

MAGIC   = 0x616b3432
VERSION = 2


def build_vocab():
    """A minimal SentencePiece-like vocab: specials, byte fallbacks, ASCII."""
    vocab = ["<unk>", "<s>", "</s>"]          # ids 0,1,2
    for b in range(256):                       # ids 3..258 byte fallback
        vocab.append("<0x%02X>" % b)
    for cp in range(32, 127):                  # ids 259..353 printable ASCII
        vocab.append(chr(cp))
    return vocab


def quantize_group(vals, qmax):
    """Symmetric group quantization matching quant.c (qmax=127 Q8, 7 Q4)."""
    wmax = max((abs(v) for v in vals), default=0.0)
    scale = wmax / qmax
    q = []
    for v in vals:
        x = (v / scale) if scale > 0 else 0.0
        qi = int(round(x))
        qi = max(-qmax, min(qmax, qi))
        q.append(qi)
    return q, scale


def write_quantized(f, vals, q4=False):
    """Write one quantized tensor: payload then fp32 scales.

    Q8: one signed byte per value. Q4: two nibbles packed per byte
    (low = even element, high = odd), values in [-7, 7] as 4-bit two's comp."""
    assert len(vals) % GS == 0, (len(vals), GS)
    qmax = 7 if q4 else 127
    qall, sall = [], []
    for g in range(0, len(vals), GS):
        q, s = quantize_group(vals[g:g + GS], qmax)
        qall.extend(q)
        sall.append(s)
    if q4:
        for i in range(0, len(qall), 2):
            byte = (qall[i] & 0x0F) | ((qall[i + 1] & 0x0F) << 4)
            f.write(struct.pack("B", byte))
    else:
        f.write(struct.pack("%db" % len(qall), *qall))
    f.write(struct.pack("%df" % len(sall), *sall))


def rand_vec(n, scale=0.04):
    return [random.gauss(0.0, scale) for _ in range(n)]


def write_model(path, vocab_size, q4=False):
    random.seed(1234)
    quant_type = 1 if q4 else 0
    with open(path, "wb") as f:
        # ---- 256-byte header ----
        # header[9] packs shared_classifier (byte 0) and quant_type (byte 1)
        flags = 1 | (quant_type << 8)
        header = struct.pack(
            "<10i", MAGIC, VERSION, DIM, HIDDEN_DIM, N_LAYERS,
            N_HEADS, N_KV_HEADS, vocab_size, SEQ_LEN, flags,
        )
        header += struct.pack("<i", GS)
        f.write(header)
        f.write(b"\x00" * (256 - len(header)))

        # ---- fp32 RMSNorm weights (initialise to ~1.0) ----
        def write_norm(n):
            f.write(struct.pack("%df" % n, *[1.0 + random.gauss(0, 0.01)
                                             for _ in range(n)]))
        write_norm(N_LAYERS * DIM)   # rms_att
        write_norm(N_LAYERS * DIM)   # rms_ffn
        write_norm(DIM)              # rms_final

        # ---- quantized weights, in loader order ----
        def wq(vals): write_quantized(f, vals, q4)
        wq(rand_vec(vocab_size * DIM))                         # q_tokens
        for _ in range(N_LAYERS): wq(rand_vec(DIM * DIM))      # wq
        for _ in range(N_LAYERS): wq(rand_vec(DIM * KV_DIM))   # wk
        for _ in range(N_LAYERS): wq(rand_vec(DIM * KV_DIM))   # wv
        for _ in range(N_LAYERS): wq(rand_vec(DIM * DIM))      # wo
        for _ in range(N_LAYERS): wq(rand_vec(DIM * HIDDEN_DIM))  # w1
        for _ in range(N_LAYERS): wq(rand_vec(HIDDEN_DIM * DIM))  # w2
        for _ in range(N_LAYERS): wq(rand_vec(DIM * HIDDEN_DIM))  # w3
        # wcls shared -> nothing more


def write_tokenizer(path, vocab):
    max_len = max(len(s.encode("utf-8")) for s in vocab)
    with open(path, "wb") as f:
        f.write(struct.pack("<i", max_len))
        for i, tok in enumerate(vocab):
            b = tok.encode("utf-8")
            score = -float(i) * 0.01      # arbitrary descending scores
            f.write(struct.pack("<f", score))
            f.write(struct.pack("<i", len(b)))
            f.write(b)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    q4 = "--q4" in sys.argv
    if len(args) != 2:
        print("usage: make_tiny_model.py [--q4] <model.bin> <tokenizer.bin>")
        sys.exit(1)
    vocab = build_vocab()
    write_model(args[0], len(vocab), q4=q4)
    write_tokenizer(args[1], vocab)
    print("wrote %s (%d-token vocab, %s) and %s" %
          (args[0], len(vocab), "Q4" if q4 else "Q8", args[1]))


if __name__ == "__main__":
    main()
