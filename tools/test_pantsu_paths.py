#!/usr/bin/env python3
from __future__ import annotations

import tempfile
from pathlib import Path

try:
    from lupa import LuaRuntime
except ImportError as exc:
    raise SystemExit("lupa is required") from exc

from pantsu_paths import (
    data_path,
    migrate_root_tsvs,
    validate_no_legacy_conflict,
)


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        legacy = root / "pantsu_overrides.tsv"
        legacy.write_text("legacy\n", encoding="utf-8")
        moved = migrate_root_tsvs(root)
        canonical = data_path(root, "pantsu_overrides.tsv")
        assert len(moved) == 1
        assert canonical.read_text(encoding="utf-8") == "legacy\n"
        assert not legacy.exists()

        legacy.write_text("legacy\n", encoding="utf-8")
        migrate_root_tsvs(root)
        assert not legacy.exists()

        legacy.write_text("conflict\n", encoding="utf-8")
        try:
            migrate_root_tsvs(root)
        except RuntimeError:
            pass
        else:
            raise AssertionError("divergent legacy TSV must stop migration")
        assert legacy.read_text(encoding="utf-8") == "conflict\n"
        assert canonical.read_text(encoding="utf-8") == "legacy\n"
        try:
            validate_no_legacy_conflict(root, canonical)
        except RuntimeError:
            pass
        else:
            raise AssertionError("writes must reject divergent legacy TSV")

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        canonical = data_path(root, "pantsu_overrides.tsv")
        canonical.parent.mkdir(parents=True)
        canonical.write_text("canonical\n", encoding="utf-8")
        legacy = root / "pantsu_overrides.tsv"
        legacy.write_text("legacy\n", encoding="utf-8")
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().test_root = str(root)
        lua.execute(
            "rime_api = { get_user_data_dir = function() return test_root end }"
        )
        source = Path(__file__).resolve().parents[1]
        lua.execute(
            f"package.path = '{source / 'lua' / '?.lua'};' .. package.path"
        )
        store = lua.eval("require('pantsu.pantsu_store')")[0]
        assert not store.ensure_runtime_files()
        assert canonical.read_text(encoding="utf-8") == "canonical\n"
        assert legacy.read_text(encoding="utf-8") == "legacy\n"

    print("PASS userdata paths: move, dedupe, conflict preservation")


if __name__ == "__main__":
    main()
