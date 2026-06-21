#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

try:
    from lupa import LuaRuntime
except ImportError as exc:
    raise SystemExit("lupa is required") from exc


def entry(lua, word):
    return lua.table_from({"word": word, "code": "abcde", "active": True})


def key_event(lua, keycode):
    return lua.eval(
        "function(code) return {"
        "keycode=code,"
        "ctrl=function() return false end,"
        "alt=function() return false end,"
        "super=function() return false end"
        "} end"
    )(keycode)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rime-dir",
        type=Path,
        default=Path.home() / "Library" / "Rime",
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "installation.yaml").write_text(
            "installation_id: test-device\n",
            encoding="utf-8",
        )
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().test_data_dir = str(root)
        lua.execute(
            "rime_api = { get_user_data_dir = "
            "function() return test_data_dir end }"
        )
        lua.execute(
            f"package.path = '{args.rime_dir / 'lua' / '?.lua'};' "
            ".. package.path"
        )
        usage = lua.eval("require('pantsu_usage')")[0]
        usage["compact_threshold"] = 3
        high = entry(lua, "高频词")
        low = entry(lua, "低频词")
        candidates = lua.table_from([high, low])

        for _ in range(4):
            assert usage.record_selection("高频词", "abcd")
        assert usage.choose_candidate(candidates) is None
        assert usage.record_selection("高频词", "abcd")
        assert usage.choose_candidate(candidates)["word"] == "高频词"

        for _ in range(5):
            assert usage.record_selection("低频词", "abcd")
        assert usage.choose_candidate(candidates) is None

        usage.reset_for_test()
        assert usage.count("高频词")[0] == 5
        assert usage.count("低频词")[0] == 5

        lua.execute(
            "pantsu_original_open = io.open; "
            "io.open = function(path, mode) "
            "if mode == 'ab' then return nil end "
            "return pantsu_original_open(path, mode) end"
        )
        assert usage.record_selection("手机回退", "abcd")
        usage.reset_for_test()
        assert usage.count("手机回退")[0] == 1

        context = lua.eval(
            """function()
              local candidates = {
                { text = '第一候选' },
                { text = '第二候选' },
              }
              local segment = {
                selected_index = 0,
                get_candidate_at = function(self, index)
                  return candidates[index + 1]
                end,
              }
              return {
                input = 'abcd',
                has_menu = function() return true end,
                get_selected_candidate = function() return candidates[1] end,
                composition = {
                  empty = function() return false end,
                  back = function() return segment end,
                },
                get_commit_text = function() return '第二候选' end,
              }
            end"""
        )()
        pending = usage.capture_selection(context, key_event(lua, 0x32), 7)
        assert pending["word"] == "第二候选"
        assert usage.commit_matches(context, pending)

        assert (root / "pantsu_usage.tsv").exists()
        assert (root / "pantsu_usage_events.tsv").exists()

    print("PASS pantsu_usage: thresholds, persistence, phone fallback")


if __name__ == "__main__":
    main()
