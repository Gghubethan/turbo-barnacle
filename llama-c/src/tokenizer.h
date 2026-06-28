/* tokenizer.h — LLaMA-2 SentencePiece BPE, byte-fallback aware.
 *
 * Loads the llama2.c `tokenizer.bin` format and provides encode (text -> token
 * ids, greedy byte-pair merges by score) and decode (token id -> bytes, with
 * SentencePiece's leading-space and raw-byte conventions handled). */
#ifndef LLAMA_TOKENIZER_H
#define LLAMA_TOKENIZER_H

typedef struct {
    char *str;
    int   id;
} TokenIndex;

typedef struct {
    char **vocab;            /* id -> token string                       */
    float *scores;           /* id -> merge score                        */
    TokenIndex *sorted;      /* vocab sorted by string for lookup        */
    int vocab_size;
    unsigned int max_token_length;
    unsigned char byte_pieces[512];  /* "<0xXX>" raw byte rendering       */
} Tokenizer;

void tokenizer_load(Tokenizer *t, const char *path, int vocab_size);
void tokenizer_free(Tokenizer *t);

/* Encode `text` into token ids. If bos/eos are set, prepend BOS(1)/append
 * EOS(2). `tokens` must hold at least strlen(text)+3 ids. Sets *n_tokens. */
void tokenizer_encode(Tokenizer *t, const char *text, int bos, int eos,
                      int *tokens, int *n_tokens);

/* Decode `token` given the previous token (`prev`, for the SentencePiece
 * leading-space rule) into a NUL-terminated, printable C string. */
const char *tokenizer_decode(Tokenizer *t, int prev, int token);

#endif /* LLAMA_TOKENIZER_H */
