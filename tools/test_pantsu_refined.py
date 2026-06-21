#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import tempfile
from collections import defaultdict
from pathlib import Path

try:
    from lupa import LuaRuntime
except ImportError as exc:
    raise SystemExit("lupa is required") from exc


def entries(path: Path):
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        if raw.startswith("#") or "\t" not in raw:
            continue
        fields = raw.split("\t")
        if len(fields) >= 2:
            yield fields[0], fields[1].strip()


def region(path: Path, start: str, end: str):
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    left = lines.index(start)
    right = lines.index(end)
    for raw in lines[left + 1 : right]:
        if not raw.startswith("#") and "\t" in raw:
            yield tuple(raw.split("\t", 1))


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    refined = list(entries(root / "pantsu.refined.dict.yaml"))
    assert len(refined) == 200_000
    effective_overrides = {}
    refined_overrides = {}
    override_path = root / "pantsu_overrides.tsv"
    if override_path.exists():
        for raw in override_path.read_text(
            encoding="utf-8-sig"
        ).splitlines():
            fields = raw.split("\t")
            if (
                len(fields) >= 10
                and fields[0] == "entry"
            ):
                target = fields[6] if fields[7] == "1" else None
                effective_overrides[
                    (fields[2], fields[4], fields[5])
                ] = target
                if fields[2] == "pantsu.refined.dict.yaml":
                    refined_overrides[(fields[4], fields[5])] = target
    effective_refined = [
        (word, refined_overrides.get((word, code), code))
        for word, code in refined
        if refined_overrides.get((word, code), code) is not None
    ]

    old_630 = list(
        (code, word)
        for word, code in region(
            root / "pantsu.core.dict.yaml",
            "#region <630>#",
            "#endregion <630>#",
        )
    )
    refined_630 = list(
        (code, word)
        for word, code in region(
            root / "pantsu.refined.core.dict.yaml",
            "#region <630>#",
            "#endregion <630>#",
        )
    )
    assert old_630 == refined_630
    refined_words = {word for word, _ in refined}
    words_630 = {word for _, word in old_630}
    assert words_630.issubset(refined_words)
    tail_words = [word for word, _ in refined[-len(words_630):]]
    assert set(tail_words) == words_630
    refined_by_code = {}
    for word, code in refined:
        refined_by_code.setdefault(code, []).append(word)
    for _, word in refined_630:
        full_codes = [
            candidate
            for candidate, words in refined_by_code.items()
            if word in words and len(candidate) == 6
        ]
        assert len(full_codes) == 1
        candidates = refined_by_code[full_codes[0]]
        position = candidates.index(word)
        assert all(candidate in words_630 for candidate in candidates[position:])

    extended = (root / "pantsu.refined.extended.dict.yaml").read_text(
        encoding="utf-8"
    )
    assert "pantsu.refined" in extended
    assert "pantsu.cizu" not in extended
    assert "pantsu.waigua" not in extended

    evaluation = json.loads(
        (root / "pantsu_refined_evaluation.json").read_text(
            encoding="utf-8"
        )
    )
    assert evaluation["refined"]["unique_words"] < evaluation["current"][
        "unique_words"
    ]
    assert evaluation["refined"]["personal_history_coverage"] == 1

    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(f"package.path = '{root / 'lua' / '?.lua'};' .. package.path")
    store = lua.eval("require('pantsu_store')")[0]
    store.set_dictionary_profile("pantsu_refined")
    files = [store["dictionary_files"][index] for index in range(
        1, len(store["dictionary_files"]) + 1
    )]
    assert "pantsu.refined.dict.yaml" in files
    assert "pantsu.cizu.dict.yaml" not in files
    store.set_dictionary_profile("pantsu")
    files = [store["dictionary_files"][index] for index in range(
        1, len(store["dictionary_files"]) + 1
    )]
    assert "pantsu.cizu.dict.yaml" in files
    assert "pantsu.refined.dict.yaml" not in files

    with tempfile.TemporaryDirectory() as directory:
        data_root = Path(directory)
        (data_root / "pantsu_candidate_order.tsv").write_text(
            "version\t2\n"
            "meta\ttest\t1\tmac\t1\n"
            "item\ttest\t1\t测试\n",
            encoding="utf-8",
        )
        isolated = LuaRuntime(unpack_returned_tuples=True)
        isolated.execute(
            "rime_api = { get_user_data_dir = function() return "
            + json.dumps(str(data_root))
            + " end }"
        )
        isolated.execute(
            f"package.path = '{root / 'lua' / '?.lua'};' .. package.path"
        )
        isolated_store = isolated.eval("require('pantsu_store')")[0]
        assert isolated_store.ensure_runtime_files()
        assert isolated_store.set_dictionary_profile("pantsu_refined")
        assert isolated_store["order_file"] == (
            "pantsu_refined_candidate_order.tsv"
        )
        assert isolated_store["undo_dir"] == "build/pantsu_refined_undo"
        assert isolated_store.ensure_runtime_files()
        refined_order = data_root / "pantsu_refined_candidate_order.tsv"
        assert refined_order.read_text(encoding="utf-8").startswith(
            "version\t2\n"
        )

    generation = json.loads(
        (root / "pantsu_refined_generation.json").read_text(
            encoding="utf-8"
        )
    )
    assert generation["repairable_empty_codes"] == 0
    assert generation["non_six_collision_codes"] == 0
    assert generation["short_code_entries_preserved"] == len(old_630)
    assert generation["short_code_slots_preserved"] == len(
        {code for code, _ in old_630}
    )
    names = {
        raw.split("\t", 1)[1]
        for raw in (root / "pantsu_refined_exclusions.tsv").read_text(
            encoding="utf-8-sig"
        ).splitlines()
        if raw.startswith("中文人名\t")
    }
    assert not (refined_words & names)

    self_words = {}
    self_codes = set()
    journal = root / "pantsu_self_words.tsv"
    if journal.exists():
        for raw in journal.read_text(
            encoding="utf-8-sig"
        ).splitlines():
            fields = raw.split("\t")
            if (
                len(fields) >= 6
                and fields[0] == "word"
                and fields[3] == "1"
            ):
                self_words[fields[1]] = fields[2]
                self_codes.add(fields[2])
    assert not (refined_words & (set(self_words) - words_630))
    assert not {
        code
        for _, code in effective_refined
        if code in self_codes
    }
    assert generation["reserved_self_words"] <= len(self_words)
    assert generation["reserved_self_word_codes"] <= len(self_codes)
    assert generation["self_word_core_conflicts"] == []

    fixed_codes = set()
    for name in [
        "pantsu.refined.core.dict.yaml",
        "pantsu.temp.dict.yaml",
        "pantsu.user.dict.yaml",
    ]:
        for word, code in entries(root / name):
            if word not in self_words:
                fixed_codes.add(code)
    assert not {
        code
        for _, code in refined
        if code in fixed_codes
    }

    overrides = root / "pantsu_overrides.tsv"
    if overrides.exists():
        refined_lines = (
            root / "pantsu.refined.dict.yaml"
        ).read_text(encoding="utf-8-sig").splitlines()
        for raw in overrides.read_text(
            encoding="utf-8-sig"
        ).splitlines():
            fields = raw.split("\t")
            if (
                len(fields) >= 10
                and fields[0] == "entry"
                and fields[2] == "pantsu.refined.dict.yaml"
            ):
                line_number = int(fields[3])
                assert refined_lines[line_number - 1].startswith(
                    f"{fields[4]}\t{fields[5]}"
                )

    non_six = {}
    for word, code in refined:
        if 3 <= len(code) < 6:
            assert code not in non_six, (
                code,
                non_six.get(code),
                word,
            )
            non_six[code] = word

    core_non_630 = {}
    lines = (root / "pantsu.refined.core.dict.yaml").read_text(
        encoding="utf-8-sig"
    ).splitlines()
    in_630 = False
    for raw in lines:
        if raw == "#region <630>#":
            in_630 = True
            continue
        if raw == "#endregion <630>#":
            in_630 = False
            continue
        if in_630 or raw.startswith("#") or "\t" not in raw:
            continue
        word, code = raw.split("\t", 1)
        if len(word) >= 2 and 3 <= len(code) < 6:
            assert code not in core_non_630
            core_non_630[code] = word

    scheme_codes = defaultdict(list)
    for name in [
        "pantsu.refined.core.dict.yaml",
        "pantsu.refined.dict.yaml",
        "pantsu.temp.dict.yaml",
        "pantsu.user.dict.yaml",
        "pantsu.zzc.dict.yaml",
    ]:
        in_630 = False
        for raw in (root / name).read_text(
            encoding="utf-8-sig"
        ).splitlines():
            if raw == "#region <630>#":
                in_630 = True
                continue
            if raw == "#endregion <630>#":
                in_630 = False
                continue
            if raw.startswith("#") or "\t" not in raw:
                continue
            word, code = raw.split("\t", 1)
            code = effective_overrides.get((name, word, code), code)
            if (
                code is not None
                and not in_630
                and len(word) >= 2
                and re.fullmatch(r"[a-z]{3,5}", code)
            ):
                scheme_codes[code].append((word, name))
    assert not {
        code: values
        for code, values in scheme_codes.items()
        if len(values) > 1
    }

    print("PASS refined scheme: preserved 630, tail full codes, no gaps")


if __name__ == "__main__":
    main()
