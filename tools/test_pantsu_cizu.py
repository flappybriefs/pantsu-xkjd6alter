#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from pantsu_dictionary import minimum_code_length


def entries(path: Path):
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        if raw.startswith("#") or "\t" not in raw:
            continue
        fields = raw.split("\t")
        if len(fields) >= 2:
            yield fields


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    assert not (root / "pantsu.waigua.dict.yaml").exists()
    cizu = list(entries(root / "pantsu.cizu.dict.yaml"))
    report = json.loads(
        (root / "pantsu_cizu_generation.json").read_text(encoding="utf-8")
    )
    assert len(cizu) == report["merged_rows"]
    assert report["remaining_repairable_gaps"] == 0
    assert report["refined_extra_rows"] > 0
    assert report["removed_person_names"] > 0

    lines = (root / "pantsu.core.dict.yaml").read_text(
        encoding="utf-8-sig"
    ).splitlines()
    start = lines.index("#region <630>#")
    end = lines.index("#endregion <630>#")
    codes_630 = {
        raw.split("\t", 1)[1]
        for raw in lines[start + 1 : end]
        if not raw.startswith("#") and "\t" in raw
    }
    words_630 = {
        raw.split("\t", 1)[0]
        for raw in lines[start + 1 : end]
        if not raw.startswith("#") and "\t" in raw
    }
    for fields in cizu:
        if fields[0] in words_630 or fields[1] in codes_630:
            assert len(fields) >= 3 and fields[2] == "0"

    self_codes = {}
    for raw in (root / "pantsu_self_words.tsv").read_text(
        encoding="utf-8-sig"
    ).splitlines():
        fields = raw.split("\t")
        if len(fields) >= 6 and fields[0] == "word" and fields[3] == "1":
            self_codes.setdefault(fields[2], set()).add(fields[1])
    assert not [
        (fields[0], fields[1])
        for fields in cizu
        if fields[1] in self_codes
        and fields[0] not in self_codes[fields[1]]
    ]

    occupied = Counter(fields[1] for fields in cizu)
    for name in (
        "pantsu.core.dict.yaml",
        "pantsu.danzi.dict.yaml",
        "pantsu.temp.dict.yaml",
        "pantsu.user.dict.yaml",
        "pantsu.zzc.dict.yaml",
    ):
        occupied.update(fields[1] for fields in entries(root / name))
    gaps = {
        fields[1][:length]
        for fields in cizu
        for length in range(
            minimum_code_length(fields[0]), len(fields[1])
        )
        if occupied[fields[1][:length]] == 0
    }
    assert not gaps

    exclusions = {
        raw.split("\t", 1)[0]
        for raw in (root / "pantsu_cizu_excluded_names.tsv").read_text(
            encoding="utf-8"
        ).splitlines()[1:]
    }
    assert not exclusions & {fields[0] for fields in cizu}
    print(
        "PASS merged cizu: "
        f"{len(cizu)} rows, {report['removed_person_names']} names removed, "
        "no gaps or self-word conflicts"
    )


if __name__ == "__main__":
    main()
