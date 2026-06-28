#!/usr/bin/env python3
"""Convert a LLaMA SentencePiece `tokenizer.model` to the engine's tokenizer.bin.

    python3 tools/export_tokenizer.py tokenizer.model tokenizer.bin

Output format (consumed by src/tokenizer.c):
    int32  max_token_length
    repeat vocab_size times:
        float32 score
        int32   byte_length
        bytes   token   (SentencePiece's "_" word-boundary marker is rewritten
                         to a real space; raw-byte pieces are decoded to bytes)
"""
import struct
import sys

try:
    from sentencepiece import SentencePieceProcessor
except ImportError:
    sys.exit("needs sentencepiece: pip install sentencepiece")


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: export_tokenizer.py <tokenizer.model> <tokenizer.bin>")
    model_path, out_path = sys.argv[1], sys.argv[2]

    sp = SentencePieceProcessor(model_file=model_path)
    n = sp.vocab_size()

    tokens, scores = [], []
    for i in range(n):
        piece = sp.id_to_piece(i)
        score = sp.get_score(i)
        if i == sp.bos_id():
            piece = "\n<s>\n"
        elif i == sp.eos_id():
            piece = "\n</s>\n"
        piece = piece.replace("▁", " ")   # ▁ -> space
        tokens.append(piece.encode("utf-8"))
        scores.append(score)

    max_len = max(len(t) for t in tokens)
    with open(out_path, "wb") as f:
        f.write(struct.pack("<i", max_len))
        for b, s in zip(tokens, scores):
            f.write(struct.pack("<f", s))
            f.write(struct.pack("<i", len(b)))
            f.write(b)
    print(f"wrote {out_path}: {n} tokens, max_token_length={max_len}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
