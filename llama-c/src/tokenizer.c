#include "tokenizer.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void die(const char *msg) {
    fprintf(stderr, "tokenizer: %s\n", msg);
    exit(EXIT_FAILURE);
}

static int token_cmp(const void *a, const void *b) {
    return strcmp(((TokenIndex *)a)->str, ((TokenIndex *)b)->str);
}

void tokenizer_load(Tokenizer *t, const char *path, int vocab_size) {
    t->vocab_size = vocab_size;
    t->vocab  = malloc(vocab_size * sizeof(char *));
    t->scores = malloc(vocab_size * sizeof(float));
    t->sorted = NULL;
    if (!t->vocab || !t->scores) die("out of memory");

    /* byte_pieces[2*b] = byte b, so single raw bytes can be emitted directly */
    for (int i = 0; i < 256; i++) {
        t->byte_pieces[i * 2] = (unsigned char)i;
        t->byte_pieces[i * 2 + 1] = '\0';
    }

    FILE *f = fopen(path, "rb");
    if (!f) die("could not open tokenizer file");
    if (fread(&t->max_token_length, sizeof(int), 1, f) != 1) die("bad tokenizer header");

    for (int i = 0; i < vocab_size; i++) {
        if (fread(t->scores + i, sizeof(float), 1, f) != 1) die("truncated tokenizer");
        int len;
        if (fread(&len, sizeof(int), 1, f) != 1) die("truncated tokenizer");
        t->vocab[i] = malloc(len + 1);
        if (!t->vocab[i]) die("out of memory");
        if (fread(t->vocab[i], 1, len, f) != (size_t)len) die("truncated tokenizer");
        t->vocab[i][len] = '\0';
    }
    fclose(f);
}

void tokenizer_free(Tokenizer *t) {
    for (int i = 0; i < t->vocab_size; i++) free(t->vocab[i]);
    free(t->vocab);
    free(t->scores);
    free(t->sorted);
}

const char *tokenizer_decode(Tokenizer *t, int prev, int token) {
    const char *piece = t->vocab[token];
    /* SentencePiece prepends a space to the token following BOS; strip it. */
    if (prev == 1 && piece[0] == ' ') piece++;
    /* raw byte tokens look like "<0xXX>" — render the actual byte */
    unsigned char byte;
    if (sscanf(piece, "<0x%02hhX>", &byte) == 1) {
        return (const char *)t->byte_pieces + byte * 2;
    }
    return piece;
}

static int str_lookup(const char *str, const Tokenizer *t) {
    TokenIndex key = { (char *)str, 0 };
    TokenIndex *res = bsearch(&key, t->sorted, t->vocab_size,
                              sizeof(TokenIndex), token_cmp);
    return res ? res->id : -1;
}

void tokenizer_encode(Tokenizer *t, const char *text, int bos, int eos,
                      int *tokens, int *n_tokens) {
    if (!text) die("null encode text");

    /* lazily build the sorted lookup table on first use */
    if (!t->sorted) {
        t->sorted = malloc(t->vocab_size * sizeof(TokenIndex));
        if (!t->sorted) die("out of memory");
        for (int i = 0; i < t->vocab_size; i++) {
            t->sorted[i].str = t->vocab[i];
            t->sorted[i].id = i;
        }
        qsort(t->sorted, t->vocab_size, sizeof(TokenIndex), token_cmp);
    }

    /* scratch big enough for two pieces plus a NUL */
    char *buf = malloc(t->max_token_length * 2 + 3);
    if (!buf) die("out of memory");
    size_t blen = 0;
    *n_tokens = 0;

    if (bos) tokens[(*n_tokens)++] = 1;  /* BOS */

    /* SentencePiece encodes a leading "▁" (space) before the first real token
     * unless the text is empty. We approximate with a dummy-prefix space. */
    if (text[0] != '\0') {
        int dummy = str_lookup(" ", t);
        if (dummy != -1) tokens[(*n_tokens)++] = dummy;
    }

    /* first pass: map UTF-8 codepoints to tokens, byte-fallback otherwise */
    for (const char *c = text; *c != '\0'; c++) {
        if ((*c & 0xC0) != 0x80) blen = 0;        /* start of a codepoint */
        buf[blen++] = *c;
        buf[blen] = '\0';
        /* keep accumulating continuation bytes (and avoid overflow) */
        if ((*(c + 1) & 0xC0) == 0x80 && blen < 4) continue;

        int id = str_lookup(buf, t);
        if (id != -1) {
            tokens[(*n_tokens)++] = id;
        } else {
            /* byte fallback: emit each byte as token id (byte + 3) */
            for (size_t i = 0; i < blen; i++)
                tokens[(*n_tokens)++] = (unsigned char)buf[i] + 3;
        }
        blen = 0;
    }

    /* second pass: greedily merge the best-scoring adjacent pair until none */
    for (;;) {
        float best_score = -1e10f;
        int best_id = -1, best_idx = -1;
        for (int i = 0; i < *n_tokens - 1; i++) {
            snprintf(buf, t->max_token_length * 2 + 3, "%s%s",
                     t->vocab[tokens[i]], t->vocab[tokens[i + 1]]);
            int id = str_lookup(buf, t);
            if (id != -1 && t->scores[id] > best_score) {
                best_score = t->scores[id];
                best_id = id;
                best_idx = i;
            }
        }
        if (best_idx == -1) break;
        tokens[best_idx] = best_id;
        for (int i = best_idx + 1; i < *n_tokens - 1; i++) tokens[i] = tokens[i + 1];
        (*n_tokens)--;
    }

    if (eos) tokens[(*n_tokens)++] = 2;  /* EOS */
    free(buf);
}
