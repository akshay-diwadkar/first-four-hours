"""Offline, integrity-checked cl100k_base tokenization for validation."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

import tiktoken
from tiktoken.load import load_tiktoken_bpe

EXPECTED_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
BPE_PATH = Path(__file__).with_name("cl100k_base.tiktoken")
PAT_STR = (
    r"'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+|"
    r" ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s"
)
SPECIAL_TOKENS = {
    "<|endoftext|>": 100257,
    "<|fim_prefix|>": 100258,
    "<|fim_middle|>": 100259,
    "<|fim_suffix|>": 100260,
    "<|endofprompt|>": 100276,
}


def _load_cl100k_base_encoding(path: Path) -> tiktoken.Encoding:
    """Build cl100k_base from a verified local ranks file."""
    resolved_path = path.resolve()
    actual_hash = hashlib.sha256(resolved_path.read_bytes()).hexdigest()
    if actual_hash != EXPECTED_SHA256:
        raise RuntimeError(
            "Vendored cl100k_base ranks failed SHA-256 verification: "
            f"expected {EXPECTED_SHA256}, got {actual_hash} for {resolved_path}"
        )
    mergeable_ranks = load_tiktoken_bpe(
        str(resolved_path),
        expected_hash=EXPECTED_SHA256,
    )
    return tiktoken.Encoding(
        name="cl100k_base",
        pat_str=PAT_STR,
        mergeable_ranks=mergeable_ranks,
        special_tokens=SPECIAL_TOKENS,
    )


@lru_cache(maxsize=1)
def get_cl100k_base_encoding() -> tiktoken.Encoding:
    """Return the cached offline cl100k_base encoding."""
    return _load_cl100k_base_encoding(BPE_PATH)


def count_tokens(text: str) -> int:
    """Count text tokens using the offline cl100k_base encoding."""
    return len(get_cl100k_base_encoding().encode(text))
