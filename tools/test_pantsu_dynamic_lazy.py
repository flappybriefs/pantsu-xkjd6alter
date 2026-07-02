#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

try:
    from lupa import LuaRuntime
except ImportError as exc:
    raise SystemExit("lupa is required") from exc


def write_runtime(root: Path) -> None:
    (root / "build").mkdir(exist_ok=True)
    (root / "user.yaml").write_text("last_build_time: 1\n", encoding="utf-8")
    (root / "pantsu_dynamic_roots.tsv").write_text(
        "\n".join(
            [
                "format\t9",
                "build\t1",
                "signature\tsig",
                "root\taaa",
                "root\tbbb",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "build/pantsu_dynamic_candidates.tsv").write_text(
        "\n".join(
            [
                "format\t9",
                "build\t1",
                "signature\tsig",
                "root\taaa",
                "suppress\taaa\t甲词",
                "entry\taaa\t1\t甲词\taaav\taaa-id",
                "root\tbbb",
                "suppress\tbbb\t乙词",
                "entry\tbbb\t1\t乙词\tbbbv\tbbb-id",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rime-dir",
        type=Path,
        default=Path.home() / "Library" / "Rime",
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        write_runtime(root)

        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().test_root = str(root)
        lua.execute(
            "rime_api = { get_user_data_dir = function() return test_root end }"
        )
        lua.execute(
            """
            test_store_calls = { entries = 0, writes = 0 }
            package.loaded["pantsu_store"] = {
              signature = function() return "sig" end,
              ensure_runtime_files = function() return true end,
              entries = function()
                test_store_calls.entries = test_store_calls.entries + 1
                error("ordinary match must not rebuild dynamic roots")
              end,
              override_roots = function()
                test_store_calls.writes = test_store_calls.writes + 1
                return {}
              end,
              self_word_roots = function()
                test_store_calls.writes = test_store_calls.writes + 1
                return {}
              end,
              invalidate_signature = function() end
            }
            """
        )
        lua.execute(
            f"package.path = '{args.rime_dir / 'lua' / '?.lua'};' .. package.path"
        )
        dynamic = lua.eval("require('pantsu_dynamic')")[0]

        state, matched_root = dynamic.match("aaav")
        assert matched_root == "aaa"
        assert state["entries"][1]["word"] == "甲词"
        assert dynamic.roots["aaa"] is not None
        assert dynamic.roots["bbb"] is None

        (root / "user.yaml").write_text(
            "last_build_time: 2\n",
            encoding="utf-8",
        )
        dynamic.invalidate()
        write_runtime(root)
        (root / "user.yaml").write_text(
            "last_build_time: 2\n",
            encoding="utf-8",
        )
        state, matched_root = dynamic.match("aaav")
        assert matched_root == "aaa"
        assert state["entries"][1]["word"] == "甲词"

        missing = dynamic.match("ccc")
        assert missing is None
        calls = lua.globals().test_store_calls
        assert calls["entries"] == 0
        assert calls["writes"] == 0

        print("PASS pantsu_dynamic lazy root match: no rebuild on typing")


if __name__ == "__main__":
    main()
