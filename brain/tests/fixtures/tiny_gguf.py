"""Writes a tiny, random-weight llama-architecture GGUF for integration tests.

The model is a few hundred KB, loads in milliseconds and produces gibberish, which
is exactly what the tests need: real llama.cpp loading, tokenising, sampling and
grammar enforcement, without a multi-GB download.
"""

from pathlib import Path

import gguf
import numpy as np

N_EMBD = 64
N_HEAD = 2
N_FF = 128
N_LAYER = 1
N_CTX = 512
CHATML = (
    "{% for m in messages %}<|im_start|>{{ m['role'] }}\n{{ m['content'] }}<|im_end|>\n"
    "{% endfor %}{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}"
)


def _vocab() -> tuple[list[bytes], list[float], list[int]]:
    tokens = [b"<unk>", b"<s>", b"</s>"]
    types = [
        gguf.TokenType.UNKNOWN,
        gguf.TokenType.CONTROL,
        gguf.TokenType.CONTROL,
    ]
    tokens += [f"<0x{i:02X}>".encode() for i in range(256)]
    types += [gguf.TokenType.BYTE] * 256
    # Printable ASCII as normal pieces so text tokenises compactly; SentencePiece
    # writes spaces as U+2581.
    for code in range(33, 127):
        tokens.append(chr(code).encode())
        types.append(gguf.TokenType.NORMAL)
    tokens.append("▁".encode())
    types.append(gguf.TokenType.NORMAL)
    scores = [0.0] * len(tokens)
    return tokens, scores, [int(t) for t in types]


def write_tiny_gguf(path: Path, seed: int = 0) -> Path:
    """Write the model to ``path`` and return it."""
    rng = np.random.default_rng(seed)
    tokens, scores, types = _vocab()
    n_vocab = len(tokens)

    writer = gguf.GGUFWriter(str(path), "llama")
    writer.add_name("zeno-tiny-test")
    writer.add_context_length(N_CTX)
    writer.add_embedding_length(N_EMBD)
    writer.add_block_count(N_LAYER)
    writer.add_feed_forward_length(N_FF)
    writer.add_head_count(N_HEAD)
    writer.add_head_count_kv(N_HEAD)
    writer.add_rope_dimension_count(N_EMBD // N_HEAD)
    writer.add_layer_norm_rms_eps(1e-5)
    writer.add_file_type(gguf.LlamaFileType.ALL_F32)
    writer.add_tokenizer_model("llama")
    writer.add_token_list(tokens)
    writer.add_token_scores(scores)
    writer.add_token_types(types)
    writer.add_bos_token_id(1)
    writer.add_eos_token_id(2)
    writer.add_unk_token_id(0)
    writer.add_add_bos_token(True)
    writer.add_chat_template(CHATML)

    def weight(*shape: int) -> np.ndarray:
        return (rng.standard_normal(shape) * 0.02).astype(np.float32)

    ones = np.ones(N_EMBD, dtype=np.float32)
    writer.add_tensor("token_embd.weight", weight(n_vocab, N_EMBD))
    writer.add_tensor("output_norm.weight", ones)
    writer.add_tensor("output.weight", weight(n_vocab, N_EMBD))
    for i in range(N_LAYER):
        writer.add_tensor(f"blk.{i}.attn_norm.weight", ones)
        for name in ("attn_q", "attn_k", "attn_v", "attn_output"):
            writer.add_tensor(f"blk.{i}.{name}.weight", weight(N_EMBD, N_EMBD))
        writer.add_tensor(f"blk.{i}.ffn_norm.weight", ones)
        writer.add_tensor(f"blk.{i}.ffn_gate.weight", weight(N_FF, N_EMBD))
        writer.add_tensor(f"blk.{i}.ffn_up.weight", weight(N_FF, N_EMBD))
        writer.add_tensor(f"blk.{i}.ffn_down.weight", weight(N_EMBD, N_FF))

    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()
    return path
