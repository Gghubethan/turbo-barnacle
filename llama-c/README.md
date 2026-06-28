# llama-c · 纯 C 实现的 LLaMA-2 推理引擎

零依赖（除 libc + libm）的 LLaMA-2 推理引擎，纯 C 实现 7B 模型的 CPU 推理，支持
**int8 分组量化**、**KV 缓存**、**流式输出**。可加载从 Hugging Face 导出的
LLaMA-2 7B 权重，在普通 CPU 上逐 token 生成文本。

> 不依赖任何深度学习框架（无 PyTorch / GGML / BLAS）。前向传播、量化矩阵乘、
> 注意力、RoPE、SwiGLU、采样全部手写。

## 特性

| 能力 | 实现 |
| --- | --- |
| **int8 量化** | 对称分组量化（group size `GS=64`），每组一个 fp32 scale，权重 ~4× 压缩。矩阵乘在 int8 域累加成 int32 再回乘 scale。见 `src/quant.c`。 |
| **KV 缓存** | key/value 投影直接写入 `(n_layers, seq_len, kv_dim)` 缓存；每步只对当前位置算 q/k/v，注意力扫描历史缓存。见 `src/model.c`。 |
| **流式输出** | 解码出一个 token 立即 `fputs`+`fflush`，无需等整段生成完。见 `src/main.c` 的 `generate()`。 |
| **GQA** | `n_kv_heads <= n_heads` 时启用分组查询注意力（7B 为 MHA，两者相等）。 |
| **采样** | 温度为 0 走贪心 argmax；否则温度缩放 + top-p（nucleus）采样，自带可复现 xorshift RNG。见 `src/sampler.c`。 |
| **SIMD 加速** | `matmul_q8` 热点自动选择最宽 ISA：AVX-512BW（`_mm512_madd_epi16`）> AVX2（`_mm256_madd_epi16`）> 标量回退。三条路径整数累加、**逐位一致**；实测单线程对标量约 1.9×（4096² 矩阵乘受内存带宽限制，AVX-512 较 AVX2 再小幅领先）。 |
| **多线程** | `make omp` 用 OpenMP 并行矩阵乘与多头注意力，与 SIMD 叠加。 |

## 目录结构

```
llama-c/
├── src/
│   ├── quant.{h,c}      int8 分组量化 + 量化矩阵乘（热点）
│   ├── model.{h,c}      Config / 权重加载(mmap) / KV 缓存前向传播
│   ├── tokenizer.{h,c}  SentencePiece BPE 编码/解码（含字节回退）
│   ├── sampler.{h,c}    贪心 / 温度 / top-p 采样
│   └── main.c           CLI + 流式生成循环
├── tools/
│   ├── export.py            HF LLaMA-2 权重 → int8 .bin
│   └── export_tokenizer.py  tokenizer.model → tokenizer.bin
├── test/
│   ├── make_tiny_model.py   生成微型合成模型，端到端冒烟测试
│   └── test_quant.c         int8 量化数值单元测试（对比 fp32）
└── Makefile
```

## 快速开始

### 1. 编译

```bash
cd llama-c
make            # 优化构建 -> build/llama
make omp        # 额外开启 OpenMP 多线程（推荐 7B）
make debug      # -O0 + AddressSanitizer/UBSan，用于排错
make check      # int8 量化数值单元测试（matmul_q8 对比 fp32 参考）
```

> `make check` 用随机数据验证 int8 路径的**数值正确性**：分组量化往返误差在
> `scale/2` 界内，量化矩阵乘相对 fp32 参考的 L2 相对误差 < 3%（实测约 0.5%）。
> GitHub Actions（`.github/workflows/llama-c.yml`）在每次改动 `llama-c/` 时自动跑
> 构建 + 单元测试 + 端到端冒烟测试 + ASan/UBSan。

### 2. 不下载真模型，先跑通流程

无需 numpy/torch，纯标准库即可生成一个结构合法的微型随机模型并端到端运行：

```bash
make test
# 生成 test/tiny.bin + tokenizer，加载 → 编码 → KV 缓存解码 → 流式输出
# 输出是随机权重产生的乱码，仅用于验证管线（加载/量化/注意力/采样）正确
```

### 3. 跑真正的 LLaMA-2 7B

在一台内存充足（7B 约需 ~16 GB）的机器上导出一次权重：

```bash
pip install torch transformers sentencepiece

# 权重：HF 格式 -> int8 .bin（约 7 GB）
python3 tools/export.py meta-llama/Llama-2-7b-hf llama2_7b_q8.bin

# 分词器：SentencePiece -> tokenizer.bin
python3 tools/export_tokenizer.py /path/to/tokenizer.model tokenizer.bin
```

然后在 CPU 上生成文本（流式输出）：

```bash
./build/llama llama2_7b_q8.bin -z tokenizer.bin \
    -i "The meaning of life is" -n 256 -t 0.8 -p 0.9
```

### CLI 参数

```
./build/llama <model.bin> [options]
  -z <path>   分词器文件（默认 tokenizer.bin）
  -i <text>   prompt 文本
  -n <int>    最大生成步数（默认 256，上限为模型 seq_len）
  -t <float>  温度，0 = 贪心（默认 1.0）
  -p <float>  top-p nucleus 采样（默认 0.9）
  -s <int>    随机种子（默认按时间）
  -m <mode>   generate（默认）或 chat
  -y <text>   chat 模式的 system prompt
```

### 交互式对话（chat 模式）

用 LLaMA-2 chat 模板（`[INST] <<SYS>>...<</SYS>> ... [/INST]`）多轮对话。
**KV 缓存跨轮保留**——历史对话不重复计算，新一轮用户输入直接追加到当前位置：

```bash
./build/llama llama2_7b_chat_q8.bin -z tokenizer.bin -m chat \
    -y "You are a helpful assistant." -t 0.7

you> 用一句话解释什么是量化
bot> ...
you> 那 int8 和 int4 有什么区别
bot> ...
```

> chat 模式建议使用 LLaMA-2 **chat** 权重（`Llama-2-7b-chat-hf`）。

## 模型文件格式（version 2）

`export.py` 写、`src/model.c` 读。256 字节头部 + 主体：

```
头部 (256B, 0 填充):
  int32  magic   = 0x616b3432
  int32  version = 2
  int32  dim, hidden_dim, n_layers, n_heads, n_kv_heads, vocab_size, seq_len
  uint8  shared_classifier        // 1 = 分类头复用 token embedding
  int32  group_size               // 必须等于编译时的 GS
主体:
  fp32   rms_att   (n_layers*dim)
  fp32   rms_ffn   (n_layers*dim)
  fp32   rms_final (dim)
  量化张量（顺序: q_tokens, wq, wk, wv, wo, w1, w2, w3, [wcls 若不共享]）:
    int8  q[n]
    fp32  s[n/GS]
```

RMSNorm 权重保留 fp32（量小且对精度敏感），其余 matmul 权重全部 int8 量化。

> **注意**：`export.py` 会对 HF 的 q/k 投影做反置换（`unpermute`），以匹配本引擎
> 使用的交错式 RoPE。直接拿别的工具导出的权重需确认 RoPE 约定一致。

## 工作原理（前向一步）

```
token ──► 查 embedding ──► 残差流 x
  └─ 每层:
       RMSNorm → 量化 x → matmul_q8 得 q,k,v(写入 KV 缓存)
       RoPE 旋转 q,k → 多头注意力(扫描缓存) → wo 投影 → 残差相加
       RMSNorm → SwiGLU: w2( SiLU(w1·x) ⊙ (w3·x) ) → 残差相加
  └─ 最终 RMSNorm → 分类头 matmul_q8 → logits ──► 采样 ──► 下一个 token
```

量化矩阵乘 `matmul_q8` 是热点：按 `GS` 分组，组内 int8×int8 累加进 int32，
再乘上权重和激活两个 fp32 scale。

## 限制

- 面向 LLaMA-2 7B 校准；其它尺寸只要 config 与张量维度都能被 `GS` 整除即可。
- x86 AVX-512BW / AVX2 int8 SIMD + 可选 OpenMP；未用 VNNI `dpbusd`（需符号偏移处理）或 ARM NEON，亦无手写 GEMM 分块，单线程 7B 速度仍有限（适合学习/小规模生成，不追求极致吞吐）。
- 仅 CPU、fp32 激活 + int8 权重；无 batch、无 GPU。
