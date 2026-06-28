# Pure-C int8 LLaMA-2 inference engine.
#
# Targets:
#   make          optimized build -> build/llama
#   make omp      optimized + OpenMP multithreading
#   make debug    -O0 -g with sanitizers
#   make test     build and run the end-to-end smoke test
#   make clean

CC      ?= cc
CFLAGS  ?= -O3 -ffast-math -march=native -funroll-loops -Wall -Wextra -std=gnu11
LDFLAGS ?= -lm

# Group size for int8 quantization. Must match the value used by export.py.
GS ?= 64
CFLAGS += -DGS=$(GS)

SRC     := src/quant.c src/model.c src/tokenizer.c src/sampler.c src/main.c
HDR     := src/quant.h src/model.h src/tokenizer.h src/sampler.h
BIN     := build/llama

.PHONY: all omp debug test clean

all: $(BIN)

$(BIN): $(SRC) $(HDR)
	@mkdir -p build
	$(CC) $(CFLAGS) $(SRC) -o $@ $(LDFLAGS)

omp: CFLAGS += -fopenmp
omp: clean $(BIN)

debug: CFLAGS := -O0 -g -fsanitize=address,undefined -Wall -Wextra -std=gnu11 -DGS=$(GS)
debug: clean $(BIN)

# Builds a tiny synthetic model + tokenizer and runs the engine end to end.
test: $(BIN)
	python3 test/make_tiny_model.py test/tiny.bin test/tiny_tok.bin
	./$(BIN) test/tiny.bin -z test/tiny_tok.bin -n 16 -t 0 -i "hello"
	@echo "smoke test passed"

clean:
	rm -rf build test/tiny.bin test/tiny_tok.bin
