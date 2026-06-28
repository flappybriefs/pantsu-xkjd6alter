#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from pantsu_dictionary import (
    full_code_for_word,
    load_char_codes,
    minimum_code_length,
)

ROOT = Path(__file__).resolve().parents[1]
VALID_WORD = re.compile(r"^[\u3400-\u9fff]{2,6}$")
SOURCE_LOCK = {
    "wordfreq": {
        "version": "3.1.1",
        "sha256": (
            "4b1c6ecffc6198be3396d5cf871c4423"
            "ca71c907c231348d352dd54d62b97473"
        ),
    },
    "rime_essay": {
        "commit": "48c7538f0b760fcc8c9d6bf08711f82cfbd2e9ed",
        "sha256": (
            "09086a44204f469d2c16ad72784e1f567"
            "a6f016570dfc9aa79f868267a9c1385"
        ),
    },
    "thuocl": {
        "commit": "a30ce79d895d01ab5132a5c74c29703ff7efb4cc",
        "sha256": (
            "6a11dc7fe1122057d83a3d303f55236f"
            "dd191e5f88c62d4c494ce271b520592c"
        ),
    },
    "chinese_names": {
        "commit": "47d4af8d816f6212787ddfc49173cac3b994b58d",
        "sha256": (
            "a3893f8c1d3e9bfaa81ed81ec708f455"
            "0523e7697338a610745d90bece1f2de5"
        ),
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def combined_sha256(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(f"{sha256(path)}  {path.name}\n".encode())
    return digest.hexdigest()


def rows(path: Path, source: str, overrides=None):
    for number, raw in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(),
        1,
    ):
        if raw.startswith("#") or "\t" not in raw:
            continue
        fields = raw.split("\t")
        if len(fields) >= 2 and fields[0] and fields[1]:
            record = (overrides or {}).get((source, number))
            if record:
                if record[7] != "1" or record[6] == "-":
                    continue
                fields[0] = record[4]
                fields[1] = record[6]
            yield {
                "word": fields[0],
                "code": fields[1].strip(),
                "source": source,
            }


def load_words(path: Path) -> set[str]:
    return {
        raw.split("\t", 1)[0].strip()
        for raw in path.read_text(
            encoding="utf-8-sig", errors="ignore"
        ).splitlines()
        if VALID_WORD.fullmatch(raw.split("\t", 1)[0].strip())
    }


def load_overrides(path: Path | None):
    result = {}
    if path is None or not path.exists():
        return result
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        fields = raw.split("\t")
        if (
            len(fields) >= 10
            and fields[0] == "entry"
            and fields[3].isdigit()
        ):
            result[(fields[2], int(fields[3]))] = fields
    return result


def load_essay(path: Path) -> dict[str, int]:
    result = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        fields = raw.split("\t")
        if (
            len(fields) >= 2
            and fields[1].isdigit()
            and VALID_WORD.fullmatch(fields[0])
        ):
            result[fields[0]] = int(fields[1])
    return result


def load_thuocl(directory: Path) -> dict[str, int]:
    paths = sorted(directory.glob("*.txt"))
    if combined_sha256(paths) != SOURCE_LOCK["thuocl"]["sha256"]:
        raise SystemExit("THUOCL 校验失败")
    result = {}
    for path in paths:
        for raw in path.read_text(
            encoding="utf-8-sig", errors="ignore"
        ).splitlines():
            fields = raw.split("\t")
            if (
                len(fields) >= 2
                and fields[-1].isdigit()
                and VALID_WORD.fullmatch(fields[0])
            ):
                result[fields[0]] = max(
                    result.get(fields[0], 0), int(fields[-1])
                )
    return result


def dictionary_codes(path: Path) -> set[str]:
    return {
        row["code"] for row in rows(path, path.name)
    } if path.exists() else set()


def active_self_words() -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    path = ROOT / "pantsu_self_words.tsv"
    if path.exists():
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            fields = raw.split("\t")
            if len(fields) >= 6 and fields[0] == "word" and fields[3] == "1":
                result[fields[1]].add(fields[2])
    return result


def reserve_self_codes(items):
    self_words = active_self_words()
    self_codes = {
        code for codes in self_words.values() for code in codes
    }
    occupied = Counter(item["code"] for item in items)
    occupied.update(self_codes)
    primary, options = load_char_codes(ROOT)
    kept = []
    moved = 0
    removed = 0
    for item in items:
        if item["word"] in self_words:
            occupied[item["code"]] -= 1
            removed += 1
            continue
        if item["code"] not in self_codes:
            kept.append(item)
            continue
        full = full_code_for_word(
            item["word"], {item["code"]}, primary, options
        )
        target = None
        if full:
            for length in range(len(item["code"]) + 1, len(full) + 1):
                candidate = full[:length]
                if candidate not in self_codes and (
                    len(candidate) == 6 or occupied[candidate] == 0
                ):
                    target = candidate
                    break
        occupied[item["code"]] -= 1
        if target:
            item["code"] = target
            occupied[target] += 1
            kept.append(item)
            moved += 1
        else:
            removed += 1
    return kept, moved, removed, self_codes


def core_630() -> tuple[set[str], set[str]]:
    lines = (ROOT / "pantsu.core.dict.yaml").read_text(
        encoding="utf-8-sig"
    ).splitlines()
    start = lines.index("#region <630>#")
    end = lines.index("#endregion <630>#")
    words = set()
    codes = set()
    for raw in lines[start + 1 : end]:
        if not raw.startswith("#") and "\t" in raw:
            word, code = raw.split("\t", 1)
            words.add(word)
            codes.add(code.strip())
    return words, codes


def fill_gaps(items, protected: set[str], score):
    occupied = Counter(protected)
    for item in items:
        occupied[item["code"]] += 1
    moved = 0
    while True:
        best_by_gap = {}
        for index, item in enumerate(items):
            code = item["code"]
            minimum = minimum_code_length(item["word"])
            for length in range(minimum, len(code)):
                gap = code[:length]
                if occupied[gap]:
                    continue
                current = best_by_gap.get(gap)
                candidate = (score(item["word"]), -index, index)
                if current is None or candidate > current:
                    best_by_gap[gap] = candidate
        if not best_by_gap:
            break
        used = set()
        changed = False
        for gap in sorted(best_by_gap, key=lambda value: (len(value), value)):
            if occupied[gap]:
                continue
            index = best_by_gap[gap][2]
            if index in used:
                continue
            item = items[index]
            if not item["code"].startswith(gap) or len(item["code"]) <= len(gap):
                continue
            occupied[item["code"]] -= 1
            item["code"] = gap
            occupied[gap] += 1
            used.add(index)
            moved += 1
            changed = True
        if not changed:
            break
    return moved, occupied


def generate(args) -> None:
    wheel = args.wordfreq_wheel.resolve()
    essay_path = args.essay.resolve()
    thuocl_dir = args.thuocl.resolve()
    names_path = args.names.resolve()
    if sha256(wheel) != SOURCE_LOCK["wordfreq"]["sha256"]:
        raise SystemExit("wordfreq 校验失败")
    if sha256(essay_path) != SOURCE_LOCK["rime_essay"]["sha256"]:
        raise SystemExit("Rime Essay 校验失败")
    if sha256(names_path) != SOURCE_LOCK["chinese_names"]["sha256"]:
        raise SystemExit("中文人名语料校验失败")

    from wordfreq import top_n_list, zipf_frequency

    essay = load_essay(essay_path)
    thuocl = load_thuocl(thuocl_dir)
    historical_names = load_words(thuocl_dir / "THUOCL_lishimingren.txt")
    common_names = load_words(names_path)
    ranks = {
        word: index
        for index, word in enumerate(top_n_list("zh", 500_000), 1)
        if VALID_WORD.fullmatch(word)
    }
    max_essay = math.log1p(max(essay.values()))

    def score(word: str) -> float:
        rank_score = (
            1 - (ranks[word] - 1) / 500_000 if word in ranks else 0
        )
        essay_score = (
            math.log1p(essay[word]) / max_essay if word in essay else 0
        )
        domain_score = (
            min(1, math.log1p(thuocl[word]) / 20)
            if word in thuocl else 0
        )
        return 0.54 * rank_score + 0.43 * essay_score + 0.03 * domain_score

    overrides = load_overrides(args.overrides)
    merged = []
    seen = set()
    known_words = set()
    source_counts = Counter()
    for source, path in (
        ("cizu", ROOT / "pantsu.cizu.dict.yaml"),
        ("waigua", ROOT / "pantsu.waigua.dict.yaml"),
    ):
        source_name = path.name
        for item in rows(path, source_name, overrides):
            item["source"] = source
            key = (item["word"], item["code"])
            if key in seen:
                continue
            seen.add(key)
            known_words.add(item["word"])
            source_counts[source] += 1
            item["ordinal"] = len(merged)
            merged.append(item)

    refined_added = []
    if args.refined and args.refined.exists():
        primary, options = load_char_codes(ROOT)
        for item in rows(
            args.refined,
            "pantsu.refined.dict.yaml",
            overrides,
        ):
            item["source"] = "refined_extra"
            word = item["word"]
            if word in known_words:
                continue
            full = full_code_for_word(
                word, {item["code"]}, primary, options
            )
            if not full:
                continue
            full = full[:6]
            key = (word, full)
            if key in seen:
                continue
            seen.add(key)
            known_words.add(word)
            item["code"] = full
            item["low_weight"] = True
            source_counts["refined_extra"] += 1
            item["ordinal"] = len(merged)
            refined_added.append(item)
            merged.append(item)

    excluded_names = set()
    kept = []
    for item in merged:
        word = item["word"]
        is_name = word in historical_names or word in common_names
        weak_common_evidence = (
            zipf_frequency(word, "zh") < 4.0
            and essay.get(word, 0) < 1000
        )
        if is_name and weak_common_evidence:
            excluded_names.add(word)
            continue
        kept.append(item)

    kept, self_moves, self_removed, self_codes = reserve_self_codes(kept)
    words_630, codes_630 = core_630()
    protected = set(codes_630)
    for name in (
        "pantsu.core.dict.yaml",
        "pantsu.danzi.dict.yaml",
        "pantsu.user.dict.yaml",
        "pantsu.zzc.dict.yaml",
    ):
        protected.update(dictionary_codes(ROOT / name))
    moved, occupied = fill_gaps(kept, protected, score)

    gaps = {
        item["code"][:length]
        for item in kept
        for length in range(
            minimum_code_length(item["word"]), len(item["code"])
        )
        if occupied[item["code"][:length]] == 0
    }
    if gaps:
        raise SystemExit(f"仍有 {len(gaps)} 个可补空码")

    original_order = {
        (item["word"], item["code"], index): index
        for index, item in enumerate(kept)
    }
    kept.sort(key=lambda item: (
        item["code"],
        item.get("low_weight", False),
        item["ordinal"],
    ))
    header = [
        "# Rime dictionary",
        "# encoding: utf-8",
        "---",
        "name: pantsu.cizu",
        'version: "2026.06-merged"',
        "sort: original",
        "...",
        "# 已合并原 pantsu.waigua；与 630 同码的普通词使用最低权重",
    ]
    output = header + [
        (
            f"{item['word']}\t{item['code']}\t0"
            if (
                item.get("low_weight", False)
                or (
                    item["word"] in words_630
                    or item["code"] in codes_630
                )
            )
            else f"{item['word']}\t{item['code']}"
        )
        for item in kept
    ]

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = ROOT / "backups" / f"{stamp}-merge-waigua"
    backup.mkdir(parents=True, exist_ok=True)
    for name in ("pantsu.cizu.dict.yaml", "pantsu.waigua.dict.yaml"):
        shutil.copy2(ROOT / name, backup / name)
    (ROOT / "pantsu.cizu.dict.yaml").write_text(
        "\n".join(output) + "\n", encoding="utf-8"
    )
    (ROOT / "pantsu.waigua.dict.yaml").unlink()
    report = {
        "cizu_source_rows": source_counts["cizu"],
        "waigua_source_rows": source_counts["waigua"],
        "refined_extra_rows": source_counts["refined_extra"],
        "merged_rows": len(kept),
        "removed_person_names": len(excluded_names),
        "gap_fill_moves": moved,
        "self_code_moves": self_moves,
        "self_duplicates_or_unmovable_removed": self_removed,
        "reserved_self_codes": len(self_codes),
        "remaining_repairable_gaps": len(gaps),
        "lower_weight_630_collisions": sum(
            item["word"] in words_630 or item["code"] in codes_630
            for item in kept
        ),
        "backup": str(backup),
        "source_lock": SOURCE_LOCK,
        "source_overrides_loaded": len(overrides),
    }
    (ROOT / "pantsu_cizu_generation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (ROOT / "pantsu_cizu_excluded_names.tsv").write_text(
        "词汇\t原因\n"
        + "".join(f"{word}\t低频中文人名\n" for word in sorted(excluded_names)),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="合并并整理胖次键道词组词库")
    parser.add_argument("--wordfreq-wheel", type=Path, required=True)
    parser.add_argument("--essay", type=Path, required=True)
    parser.add_argument("--thuocl", type=Path, required=True)
    parser.add_argument("--names", type=Path, required=True)
    parser.add_argument("--refined", type=Path)
    parser.add_argument("--overrides", type=Path)
    generate(parser.parse_args())


if __name__ == "__main__":
    main()
