#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from itertools import product
from pathlib import Path


def read_entries(path: Path):
    if not path.exists():
        return
    for number, raw in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(),
        1,
    ):
        if raw.startswith("#") or "\t" not in raw:
            continue
        fields = raw.split("\t")
        word = fields[0]
        code = fields[1].strip() if len(fields) > 1 else ""
        if word and code:
            yield number, word, code


def load_char_codes(root: Path):
    primary = {}
    options: dict[str, list[str]] = defaultdict(list)
    for _, char, code in read_entries(root / "pantsu.danzi.dict.yaml"):
        if len(char) != 1 or len(code) < 3:
            continue
        if code not in options[char]:
            options[char].append(code)
        current = primary.get(char)
        if current is None or len(code) > len(current):
            primary[char] = code
    return primary, options


def encode_codes(word: str, codes: list[str]) -> str:
    if len(word) == 2:
        return codes[0][:2] + codes[1][:2] + codes[0][2] + codes[1][2]
    if len(word) == 3:
        return (
            codes[0][0] + codes[1][0] + codes[2][0]
            + codes[0][2] + codes[1][2] + codes[2][2]
        )
    return (
        codes[0][0] + codes[1][0] + codes[2][0] + codes[-1][0]
        + codes[0][2] + codes[1][2]
    )


def minimum_code_length(word: str) -> int:
    return 3 if len(word) == 3 else 4


def full_code_for_word(
    word: str,
    existing: set[str],
    primary: dict[str, str],
    options: dict[str, list[str]],
) -> str | None:
    base = [primary.get(char) for char in word]
    if any(code is None or len(code) < 3 for code in base):
        return None
    standard = encode_codes(word, base)
    preferred = sorted(
        (
            code for code in existing
            if minimum_code_length(word) <= len(code) <= len(standard)
        ),
        key=lambda code: (len(code), code),
    )
    for code in preferred:
        if standard.startswith(code):
            return standard
    indexes = list(range(len(word))) if len(word) <= 3 else [
        0, 1, 2, len(word) - 1
    ]
    choices = [options.get(word[index], []) for index in indexes]
    if any(not values for values in choices):
        return standard
    for combination in product(*choices):
        selected = base.copy()
        for index, code in zip(indexes, combination):
            selected[index] = code
        full = encode_codes(word, selected)
        if any(full.startswith(code) for code in preferred):
            return full
    return standard
