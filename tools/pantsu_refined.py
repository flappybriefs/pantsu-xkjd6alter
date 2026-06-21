#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import heapq
import json
import math
import re
import shutil
from collections import defaultdict
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET_SIZE = 200_000
VALID_WORD = re.compile(r"^[\u3400-\u9fff]{2,6}$")
DICTIONARIES = [
    "pantsu.core.dict.yaml",
    "pantsu.cizu.dict.yaml",
    "pantsu.user.dict.yaml",
    "pantsu.zzc.dict.yaml",
    "pantsu.waigua.dict.yaml",
]
SOURCE_LOCK = {
    "wordfreq": {
        "version": "3.1.1",
        "url": "https://pypi.org/project/wordfreq/3.1.1/",
        "artifact": "wordfreq-3.1.1-py3-none-any.whl",
        "sha256": (
            "4b1c6ecffc6198be3396d5cf871c4423"
            "ca71c907c231348d352dd54d62b97473"
        ),
        "license": "Apache-2.0 code; bundled data CC BY-SA 4.0 and source terms",
    },
    "rime_essay": {
        "commit": "48c7538f0b760fcc8c9d6bf08711f82cfbd2e9ed",
        "url": "https://github.com/rime/rime-essay.git",
        "artifact": "essay.txt",
        "sha256": (
            "09086a44204f469d2c16ad72784e1f567"
            "a6f016570dfc9aa79f868267a9c1385"
        ),
        "license": "LGPL-3.0",
    },
    "thuocl": {
        "commit": "a30ce79d895d01ab5132a5c74c29703ff7efb4cc",
        "url": "https://github.com/thunlp/THUOCL.git",
        "artifact": "data/*.txt",
        "sha256": (
            "6a11dc7fe1122057d83a3d303f55236f"
            "dd191e5f88c62d4c494ce271b520592c"
        ),
        "license": "MIT",
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


def read_entries(path: Path):
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


def load_char_codes() -> tuple[dict[str, str], dict[str, list[str]]]:
    result: dict[str, str] = {}
    code_lists: dict[str, list[str]] = defaultdict(list)
    for _, char, code in read_entries(ROOT / "pantsu.danzi.dict.yaml"):
        if len(char) == 1 and len(code) >= 3:
            if code not in code_lists[char]:
                code_lists[char].append(code)
            current = result.get(char)
            if current is None or len(code) > len(current):
                result[char] = code
    return result, code_lists


def encode_codes(word: str, codes: list[str]) -> str:
    if len(word) == 2:
        return codes[0][:2] + codes[1][:2] + codes[0][2] + codes[1][2]
    if len(word) == 3:
        return (
            codes[0][0]
            + codes[1][0]
            + codes[2][0]
            + codes[0][2]
            + codes[1][2]
            + codes[2][2]
        )
    return (
        codes[0][0]
        + codes[1][0]
        + codes[2][0]
        + codes[-1][0]
        + codes[0][2]
        + codes[1][2]
    )


def encode_word(word: str, chars: dict[str, str]) -> str | None:
    codes = [chars.get(char) for char in word]
    if any(code is None or len(code) < 3 for code in codes):
        return None
    return encode_codes(word, codes)


def full_code_for_word(
    word: str,
    existing: set[str],
    primary: dict[str, str],
    code_lists: dict[str, list[str]],
) -> str | None:
    standard = encode_word(word, primary)
    if standard is None:
        return None
    preferred = sorted(
        (
            code
            for code in existing
            if minimum_code_length(word) <= len(code) <= len(standard)
        ),
        key=lambda code: (len(code), code),
    )
    for code in preferred:
        if standard.startswith(code):
            return standard
    for code in preferred:
        if len(code) == len(standard):
            return code
    indexes = list(range(len(word))) if len(word) <= 3 else [
        0,
        1,
        2,
        len(word) - 1,
    ]
    options = [code_lists.get(word[index], []) for index in indexes]
    if any(not values for values in options):
        return standard
    base_codes = [primary[char] for char in word]
    for combination in product(*options):
        selected = base_codes.copy()
        for index, code in zip(indexes, combination):
            selected[index] = code
        full_code = encode_codes(word, selected)
        if any(full_code.startswith(code) for code in preferred):
            return full_code
    return standard


def load_essay(path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
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
    expected = SOURCE_LOCK["thuocl"]["sha256"]
    if combined_sha256(paths) != expected:
        raise SystemExit("THUOCL 文件校验失败；停止生成")
    result: dict[str, int] = {}
    for path in paths:
        for raw in path.read_text(
            encoding="utf-8-sig",
            errors="ignore",
        ).splitlines():
            fields = raw.split("\t")
            if (
                len(fields) >= 2
                and fields[-1].isdigit()
                and VALID_WORD.fullmatch(fields[0])
            ):
                result[fields[0]] = max(
                    result.get(fields[0], 0),
                    int(fields[-1]),
                )
    return result


def load_word_set(path: Path) -> set[str]:
    result = set()
    for raw in path.read_text(
        encoding="utf-8-sig",
        errors="ignore",
    ).splitlines():
        word = raw.split("\t", 1)[0]
        if VALID_WORD.fullmatch(word):
            result.add(word)
    return result


def load_630() -> list[tuple[str, str]]:
    lines = (ROOT / "pantsu.core.dict.yaml").read_text(
        encoding="utf-8-sig"
    ).splitlines()
    start = lines.index("#region <630>#")
    end = lines.index("#endregion <630>#")
    result = []
    for raw in lines[start + 1 : end]:
        if not raw.startswith("#") and "\t" in raw:
            word, code = raw.split("\t", 1)
            result.append((word, code.strip()))
    return result


def minimum_code_length(word: str) -> int:
    if len(word) == 3:
        return 3
    return 4


def load_existing_codes() -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    core = ROOT / "pantsu.core.dict.yaml"
    core_lines = core.read_text(encoding="utf-8-sig").splitlines()
    start = core_lines.index("#region <630>#") + 1
    end = core_lines.index("#endregion <630>#")
    for number, word, code in read_entries(core):
        if not start <= number - 1 < end:
            result[word].add(code)
    for name in [
        "pantsu.cizu.dict.yaml",
        "pantsu.user.dict.yaml",
        "pantsu.zzc.dict.yaml",
        "pantsu.waigua.dict.yaml",
    ]:
        for _, word, code in read_entries(ROOT / name):
            result[word].add(code)
    path = ROOT / "pantsu_overrides.tsv"
    if path.exists():
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            fields = raw.split("\t")
            if (
                len(fields) >= 10
                and fields[0] == "entry"
                and fields[7] == "1"
                and fields[6] != "-"
            ):
                result[fields[4]].add(fields[6])
    return result


def fixed_codes() -> set[str]:
    result = set()
    for name in [
        "pantsu.core.dict.yaml",
        "pantsu.temp.dict.yaml",
        "pantsu.user.dict.yaml",
    ]:
        result.update(
            code
            for _, _, code in read_entries(ROOT / name)
        )
    return result


def overlay_words() -> set[str]:
    result = set()
    for name in [
        "pantsu.temp.dict.yaml",
        "pantsu.user.dict.yaml",
    ]:
        result.update(
            word
            for _, word, _ in read_entries(ROOT / name)
        )
    return result


def overlay_codes() -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for name in [
        "pantsu.temp.dict.yaml",
        "pantsu.user.dict.yaml",
    ]:
        for _, word, code in read_entries(ROOT / name):
            result[code].add(word)
    return result


def usage_words() -> set[str]:
    result: set[str] = set()
    usage = ROOT / "pantsu_usage.tsv"
    if usage.exists():
        for raw in usage.read_text(encoding="utf-8-sig").splitlines():
            fields = raw.split("\t")
            if len(fields) == 5 and fields[0] == "word":
                result.add(fields[1])
    return result


def active_self_words() -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    journal = ROOT / "pantsu_self_words.tsv"
    if journal.exists():
        for raw in journal.read_text(encoding="utf-8-sig").splitlines():
            fields = raw.split("\t")
            if len(fields) >= 6 and fields[0] == "word" and fields[3] == "1":
                result[fields[1]].add(fields[2])
    return result


def write_dictionary(path: Path, name: str, entries) -> None:
    lines = [
        "# Rime dictionary",
        "# encoding: utf-8",
        "---",
        f"name: {name}",
        'version: "1.0"',
        "sort: original",
        "...",
    ]
    lines.extend(f"{word}\t{code}" for word, code in entries)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def migrate_refined_overrides(
    entries: list[tuple[str, str]],
    full_codes: dict[str, str],
) -> dict[str, int]:
    path = ROOT / "pantsu_overrides.tsv"
    if not path.exists():
        return {"relocated": 0, "removed": 0}
    by_word = {
        word: (index + 8, code, full_codes[word])
        for index, (word, code) in enumerate(entries)
    }
    source = path.read_text(encoding="utf-8-sig").splitlines()
    output = []
    relocated = 0
    removed = 0
    changed = False
    for raw in source:
        fields = raw.split("\t")
        if (
            len(fields) < 10
            or fields[0] != "entry"
            or fields[2] != "pantsu.refined.dict.yaml"
        ):
            output.append(raw)
            continue
        current = by_word.get(fields[4])
        if current is None:
            removed += 1
            changed = True
            continue
        line_number, base_code, full_code = current
        target = fields[6]
        active = fields[7] == "1"
        valid_target = (
            not active
            or target == "-"
            or (
                len(target) >= minimum_code_length(fields[4])
                and full_code.startswith(target)
            )
        )
        if not valid_target:
            removed += 1
            changed = True
            continue
        new_id = (
            f"pantsu.refined.dict.yaml:{line_number}:"
            f"{fields[4]}:{base_code}"
        )
        if (
            fields[1] != new_id
            or fields[3] != str(line_number)
            or fields[5] != base_code
        ):
            fields[1] = new_id
            fields[3] = str(line_number)
            fields[5] = base_code
            relocated += 1
            changed = True
        output.append("\t".join(fields))
    if changed:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = ROOT / "backups" / f"{stamp}-refined-regeneration"
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup / path.name)
        path.write_text("\n".join(output) + "\n", encoding="utf-8")
    return {"relocated": relocated, "removed": removed}


def source_paths(args):
    wheel = args.wordfreq_wheel.resolve()
    essay = args.essay.resolve()
    thuocl = args.thuocl.resolve()
    if sha256(wheel) != SOURCE_LOCK["wordfreq"]["sha256"]:
        raise SystemExit("wordfreq wheel 校验失败；停止生成")
    if sha256(essay) != SOURCE_LOCK["rime_essay"]["sha256"]:
        raise SystemExit("Rime Essay 校验失败；停止生成")
    return wheel, essay, thuocl


def generate(args) -> None:
    _, essay_path, thuocl_dir = source_paths(args)
    try:
        from wordfreq import top_n_list
    except ImportError as exc:
        raise SystemExit(
            "缺少 wordfreq 3.1.1；请使用锁定 wheel 安装到临时环境"
        ) from exc

    chars, char_code_lists = load_char_codes()
    existing_codes = load_existing_codes()
    essay = load_essay(essay_path)
    thuocl = load_thuocl(thuocl_dir)
    excluded_names = load_word_set(
        thuocl_dir / "THUOCL_lishimingren.txt"
    )
    wordfreq_words = top_n_list("zh", 500_000)
    wordfreq_rank = {
        word: rank
        for rank, word in enumerate(wordfreq_words, 1)
        if VALID_WORD.fullmatch(word)
    }

    pool: set[str] = set()
    for name in DICTIONARIES:
        pool.update(
            word
            for _, word, _ in read_entries(ROOT / name)
            if VALID_WORD.fullmatch(word)
        )
    pool.update(wordfreq_rank)
    old_630 = load_630()
    words_630 = {word for word, _ in old_630}
    self_words = active_self_words()
    self_only_words = set(self_words) - words_630
    overlays = overlay_words() - words_630 - set(self_words)
    mandatory = {word for word, _ in old_630} | usage_words()
    mandatory -= self_only_words
    excluded_names -= mandatory
    excluded_names_in_pool = pool & excluded_names
    pool -= excluded_names_in_pool
    unsupported = {
        word
        for word in pool
        if word not in wordfreq_rank
        and word not in essay
        and word not in mandatory
    }
    pool -= unsupported
    pool -= self_only_words
    pool -= overlays
    max_essay = math.log1p(max(essay.values()))
    max_rank = len(wordfreq_words)

    def score(word: str) -> float:
        essay_score = (
            math.log1p(essay[word]) / max_essay if word in essay else 0
        )
        rank_score = (
            1 - (wordfreq_rank[word] - 1) / max_rank
            if word in wordfreq_rank
            else 0
        )
        domain_score = (
            min(1, math.log1p(thuocl[word]) / 20)
            if word in thuocl
            else 0
        )
        return 0.52 * rank_score + 0.43 * essay_score + 0.05 * domain_score

    rows = []
    by_word = {}
    for word in pool:
        full_code = full_code_for_word(
            word,
            existing_codes.get(word, set()),
            chars,
            char_code_lists,
        )
        if full_code:
            item = {
                "word": word,
                "full_code": full_code,
                "score": score(word),
                "essay": essay.get(word, 0),
                "rank": wordfreq_rank.get(word, 0),
                "thuocl": thuocl.get(word, 0),
            }
            rows.append(item)
            by_word[word] = item

    selected = heapq.nlargest(
        TARGET_SIZE,
        rows,
        key=lambda item: (item["score"], item["word"]),
    )
    selected_words = {item["word"] for item in selected}
    missing_mandatory = [
        by_word[word]
        for word in mandatory - selected_words
        if word in by_word
    ]
    if missing_mandatory:
        removable = sorted(
            [
                item
                for item in selected
                if item["word"] not in mandatory
            ],
            key=lambda item: (item["score"], item["word"]),
        )
        remove_words = {
            item["word"]
            for item in removable[: len(missing_mandatory)]
        }
        selected = [
            item for item in selected if item["word"] not in remove_words
        ] + missing_mandatory

    selected.sort(
        key=lambda item: (-item["score"], item["word"])
    )
    occupied = fixed_codes()
    reserved_self_codes = {
        code
        for codes in self_words.values()
        for code in codes
    }
    self_core_conflicts = sorted(occupied & reserved_self_codes)
    if self_core_conflicts:
        raise SystemExit(
            "自造词编码与固定词库冲突："
            + "、".join(self_core_conflicts)
        )
    occupied.update(reserved_self_codes)
    for item in selected:
        if item["word"] in words_630:
            item["code"] = item["full_code"]
            item["tail_630"] = True
            continue
        minimum = minimum_code_length(item["word"])
        item["tail_630"] = False
        item["code"] = item["full_code"]
        for length in range(minimum, len(item["full_code"]) + 1):
            candidate = item["full_code"][:length]
            if candidate not in occupied:
                item["code"] = candidate
                occupied.add(candidate)
                break

    selected_by_code: dict[str, list[dict]] = defaultdict(list)
    for item in selected:
        selected_by_code[item["code"]].append(item)
    regular_entries = []
    tail_entries = []
    for code in sorted(selected_by_code):
        ordered = sorted(
            selected_by_code[code],
            key=lambda value: (
                value["tail_630"],
                -value["score"],
                value["word"],
            ),
        )
        for item in ordered:
            target = tail_entries if item["tail_630"] else regular_entries
            target.append((item["word"], code))
    refined_entries = regular_entries + tail_entries

    core_lines = (ROOT / "pantsu.core.dict.yaml").read_text(
        encoding="utf-8-sig"
    ).splitlines()
    overlay_by_code = overlay_codes()
    refined_core = []
    moved_core_collisions = []
    in_630 = False
    for line in core_lines:
        if line == "#region <630>#":
            in_630 = True
        elif line == "#endregion <630>#":
            in_630 = False
        replacement = (
            "name: pantsu.refined.core"
            if line == "name: pantsu.core"
            else line
        )
        fields = line.split("\t")
        if (
            not in_630
            and len(fields) >= 2
            and len(fields[0]) >= 2
            and re.fullmatch(r"[a-z]{3,5}", fields[1])
            and fields[1] in overlay_by_code
            and fields[0] not in overlay_by_code[fields[1]]
        ):
            moved_core_collisions.append(
                (fields[0], fields[1])
            )
            continue
        refined_core.append(replacement)
    (ROOT / "pantsu.refined.core.dict.yaml").write_text(
        "\n".join(refined_core) + "\n",
        encoding="utf-8",
    )
    write_dictionary(
        ROOT / "pantsu.refined.dict.yaml",
        "pantsu.refined",
        refined_entries,
    )
    migration = migrate_refined_overrides(
        refined_entries,
        {item["word"]: item["full_code"] for item in selected},
    )
    (ROOT / "pantsu.refined.extended.dict.yaml").write_text(
        "\n".join([
            "# Rime dictionary",
            "# encoding: utf-8",
            "---",
            "name: pantsu.refined.extended",
            'version: "1.0"',
            "sort: original",
            "use_preset_vocabulary: false",
            "import_tables:",
            "  - pantsu.refined.core",
            "  - pantsu.danzi",
            "  - pantsu.refined",
            "  - pantsu.temp",
            "  - pantsu.user",
            "  - pantsu.zzc",
            "",
        ]),
        encoding="utf-8",
    )
    schema = (ROOT / "pantsu.schema.yaml").read_text(encoding="utf-8")
    schema = schema.replace(
        "schema_id: pantsu\n",
        "schema_id: pantsu_refined\n",
        1,
    ).replace(
        "name: 胖次键道\n",
        "name: 胖次键道·精炼版\n",
        1,
    ).replace(
        'version: "2026-06-21.4"\n',
        'version: "1.0-experimental"\n',
        1,
    ).replace(
        "dictionary: pantsu.extended\n",
        "dictionary: pantsu.refined.extended\n",
        1,
    )
    schema = "\n".join(line.rstrip() for line in schema.splitlines()) + "\n"
    (ROOT / "pantsu_refined.schema.yaml").write_text(
        schema,
        encoding="utf-8",
    )

    displaced = [["短码", "630词", "普通全码", "同码候选位置"]]
    positions = {}
    for code, items in selected_by_code.items():
        ordered = sorted(
            items,
            key=lambda value: (
                value["tail_630"],
                -value["score"],
                value["word"],
            ),
        )
        for index, item in enumerate(ordered, 1):
            positions[(item["word"], code)] = index
    for word, short_code in old_630:
        item = by_word[word]
        displaced.append([
            short_code,
            word,
            item["full_code"],
            str(positions[(word, item["full_code"])]),
        ])
    (ROOT / "pantsu_refined_630_tail.tsv").write_text(
        "\n".join("\t".join(row) for row in displaced) + "\n",
        encoding="utf-8",
    )
    (ROOT / "pantsu_refined_core_moved.tsv").write_text(
        "词汇\t原核心码\t处理\n"
        + "".join(
            f"{word}\t{code}\t移入精炼主词库并后移\n"
            for word, code in moved_core_collisions
        ),
        encoding="utf-8",
    )
    (ROOT / "pantsu_refined_sources.lock.json").write_text(
        json.dumps(SOURCE_LOCK, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (ROOT / "pantsu_refined_exclusions.tsv").write_text(
        "类型\t词汇\n"
        + "".join(
            f"中文人名\t{word}\n"
            for word in sorted(excluded_names_in_pool)
        ),
        encoding="utf-8",
    )

    summary = {
        "target_size": TARGET_SIZE,
        "actual_size": len(refined_entries),
        "short_code_entries_preserved": len(old_630),
        "short_code_slots_preserved": len(
            {code for _, code in old_630}
        ),
        "tail_630_entries": len(displaced) - 1,
        "tail_630_unique_words": len(words_630),
        "shortened_non_630_words": sum(
            item["word"] not in words_630
            and len(item["code"]) < len(item["full_code"])
            for item in selected
        ),
        "repairable_empty_codes": sum(
            1
            for item in selected
            if item["word"] not in words_630
            for length in range(
                minimum_code_length(item["word"]),
                len(item["code"]),
            )
            if item["full_code"][:length] not in occupied
        ),
        "non_six_collision_codes": sum(
            len(items) > 1 and 3 <= len(code) < 6
            for code, items in selected_by_code.items()
        ),
        "wordfreq_matches": sum(item["rank"] > 0 for item in selected),
        "essay_matches": sum(item["essay"] > 0 for item in selected),
        "thuocl_matches": sum(item["thuocl"] > 0 for item in selected),
        "minimum_score": min(item["score"] for item in selected),
        "excluded_person_names": len(excluded_names_in_pool),
        "excluded_without_general_frequency": len(unsupported),
        "reserved_self_words": len(self_words),
        "reserved_self_word_codes": len(reserved_self_codes),
        "self_word_core_conflicts": self_core_conflicts,
        "excluded_existing_overlay_words": len(overlays),
        "moved_core_collision_words": len(moved_core_collisions),
        "relocated_refined_overrides": migration["relocated"],
        "removed_stale_refined_overrides": migration["removed"],
    }
    (ROOT / "pantsu_refined_generation.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="胖次键道精炼版生成器")
    parser.add_argument(
        "--wordfreq-wheel",
        type=Path,
        required=True,
    )
    parser.add_argument("--essay", type=Path, required=True)
    parser.add_argument("--thuocl", type=Path, required=True)
    args = parser.parse_args()
    generate(args)


if __name__ == "__main__":
    main()
