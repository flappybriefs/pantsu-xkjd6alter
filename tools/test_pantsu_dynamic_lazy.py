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

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        write_runtime(root)
        roots_path = root / "pantsu_dynamic_roots.tsv"
        roots_path.write_text(
            roots_path.read_text(encoding="utf-8").replace(
                "signature\tsig",
                "signature\t",
            ),
            encoding="utf-8",
        )

        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().test_root = str(root)
        lua.execute(
            "rime_api = { get_user_data_dir = function() return test_root end }"
        )
        lua.execute(
            """
            test_store_calls = { entries = 0 }
            package.loaded["pantsu_store"] = {
              signature = function() return "sig" end,
              ensure_runtime_files = function() return true end,
              entries = function()
                test_store_calls.entries = test_store_calls.entries + 1
                error("blank root signature must still reuse signed cache")
              end,
              override_roots = function() return {} end,
              self_word_roots = function() return {} end,
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
        assert lua.globals().test_store_calls["entries"] == 0

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "build").mkdir(exist_ok=True)
        (root / "user.yaml").write_text("last_build_time: 1\n", encoding="utf-8")
        (root / "pantsu_candidate_order.tsv").write_text(
            "\n".join(
                [
                    "version\t2",
                    "meta\tzzzz\t1\ttest-device\t1",
                    "item\tzzzz\t1\t乙词",
                    "item\tzzzz\t2\t甲词",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().test_root = str(root)
        lua.execute(
            "rime_api = { get_user_data_dir = function() return test_root end }"
        )
        lua.execute(
            """
            test_store_calls = { entries = 0 }
            package.loaded["pantsu_store"] = {
              signature = function() return "fallback-sig" end,
              ensure_runtime_files = function() return true end,
              entries = function(input)
                test_store_calls.entries = test_store_calls.entries + 1
                return {
                  {
                    word = "甲词",
                    code = "zzzz",
                    base_code = "zzzz",
                    original_code = "zzzz",
                    active = true,
                    path = "pantsu.cizu.dict.yaml",
                    id = "jia",
                  },
                  {
                    word = "乙词",
                    code = "zzzz",
                    base_code = "zzzz",
                    original_code = "zzzz",
                    active = true,
                    path = "pantsu.cizu.dict.yaml",
                    id = "yi",
                  },
                }
              end,
              override_roots = function() return {} end,
              self_word_roots = function() return {} end,
              invalidate_signature = function() end
            }
            """
        )
        lua.execute(
            f"package.path = '{args.rime_dir / 'lua' / '?.lua'};' .. package.path"
        )
        dynamic = lua.eval("require('pantsu_dynamic')")[0]

        state, matched_root = dynamic.match("zzzz")
        assert matched_root == "zzz"
        assert state["entries"][1]["word"] == "乙词"
        assert state["entries"][2]["word"] == "甲词"
        assert lua.globals().test_store_calls["entries"] == 1
        assert (root / "pantsu_dynamic_roots.tsv").exists()
        assert (root / "build/pantsu_dynamic_candidates.tsv").exists()

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "build").mkdir(exist_ok=True)
        (root / "user.yaml").write_text("last_build_time: 1\n", encoding="utf-8")
        (root / "pantsu_dynamic_roots.tsv").write_text(
            "\n".join(
                [
                    "format\t9",
                    "build\t1",
                    "signature\t",
                    "root\told",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().test_root = str(root)
        lua.execute(
            "rime_api = { get_user_data_dir = function() return test_root end }"
        )
        lua.execute(
            """
            test_store_calls = { entries = 0 }
            package.loaded["pantsu_store"] = {
              signature = function() return "runtime-sig" end,
              ensure_runtime_files = function() return true end,
              entries = function(input)
                test_store_calls.entries = test_store_calls.entries + 1
                return {
                  {
                    word = "调频词",
                    code = "miss",
                    base_code = "missu",
                    original_code = "miss",
                    active = true,
                    path = "pantsu.cizu.dict.yaml",
                    id = "miss-id",
                  },
                }
              end,
              override_roots = function() return { miss = true } end,
              self_word_roots = function() return {} end,
              invalidate_signature = function() end
            }
            """
        )
        lua.execute(
            f"package.path = '{args.rime_dir / 'lua' / '?.lua'};' .. package.path"
        )
        dynamic = lua.eval("require('pantsu_dynamic')")[0]

        state, matched_root = dynamic.match("missu")
        assert matched_root == "miss"
        assert state["entries"][1]["word"] == "调频词"
        assert lua.globals().test_store_calls["entries"] == 1

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
            test_store_calls = { refreshes = 0, entries = 0 }
            package.loaded["pantsu_store"] = {
              signature = function() return "sig" end,
              ensure_runtime_files = function() return true end,
              entries = function()
                test_store_calls.entries = test_store_calls.entries + 1
                error("external state refresh should reload disk cache")
              end,
              override_roots = function() return {} end,
              self_word_roots = function() return {} end,
              invalidate_signature = function() end,
              refresh_external_state = function()
                test_store_calls.refreshes = test_store_calls.refreshes + 1
                return test_store_calls.refreshes == 2
              end
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
        (root / "build/pantsu_dynamic_candidates.tsv").write_text(
            "\n".join(
                [
                    "format\t9",
                    "build\t1",
                    "signature\tsig",
                    "root\taaa",
                    "suppress\taaa\t新词",
                    "entry\taaa\t1\t新词\taaav\tnew-id",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        state, matched_root = dynamic.match("aaav")
        assert matched_root == "aaa"
        assert state["entries"][1]["word"] == "新词"
        assert lua.globals().test_store_calls["entries"] == 0

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "build").mkdir(exist_ok=True)
        (root / "installation.yaml").write_text(
            "installation_id: test-device\n",
            encoding="utf-8",
        )
        (root / "user.yaml").write_text("last_build_time: 1\n", encoding="utf-8")
        header = "---\nname: test\nversion: \"1\"\nsort: original\n...\n"
        for name in [
            "pantsu.core.dict.yaml",
            "pantsu.danzi.dict.yaml",
            "pantsu.user.dict.yaml",
            "pantsu.zzc.dict.yaml",
        ]:
            (root / name).write_text(header, encoding="utf-8")
        (root / "pantsu.cizu.dict.yaml").write_text(
            header + "浮现\tfjxm\n复现\tfjxmu\n",
            encoding="utf-8",
        )
        (root / "pantsu_overrides.tsv").write_text(
            "version\t3\nruntime\t2026-06-21.5\n",
            encoding="utf-8",
        )
        (root / "pantsu_candidate_order.tsv").write_text("", encoding="utf-8")
        (root / "pantsu_self_words.tsv").write_text(
            "version\t1\n",
            encoding="utf-8",
        )
        (root / "pantsu_self_words_ops.tsv").write_text(
            "version\t1\n",
            encoding="utf-8",
        )

        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().test_root = str(root)
        lua.execute(
            "rime_api = { get_user_data_dir = function() return test_root end }"
        )
        lua.execute(
            f"package.path = '{args.rime_dir / 'lua' / '?.lua'};' .. package.path"
        )
        store = lua.eval("require('pantsu_store')")[0]
        entries = store.entries("fjxm")
        assert entries[1]["word"] == "浮现"
        assert entries[1]["code"] == "fjxm"

        (root / "pantsu_overrides.tsv").write_text(
            "version\t3\nruntime\t2026-06-21.5\n"
            "entry\tpantsu.cizu.dict.yaml:6:浮现:fjxm\t"
            "pantsu.cizu.dict.yaml\t6\t浮现\tfjxm\tfjxma\t1\t10\tmac\n"
            "entry\tpantsu.cizu.dict.yaml:7:复现:fjxmu\t"
            "pantsu.cizu.dict.yaml\t7\t复现\tfjxmu\tfjxm\t1\t10\tmac\n",
            encoding="utf-8",
        )
        entries = store.entries("fjxm")
        by_word = {entries[index]["word"]: entries[index] for index in range(1, len(entries) + 1)}
        assert by_word["复现"]["code"] == "fjxm"
        assert by_word["浮现"]["code"] == "fjxma"

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "build").mkdir(exist_ok=True)
        (root / "user.yaml").write_text("last_build_time: 1\n", encoding="utf-8")
        (root / "pantsu_dynamic_roots.tsv").write_text(
            "\n".join(
                [
                    "format\t9",
                    "build\t1",
                    "signature\tfresh",
                    "root\tfjxm",
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
                    "signature\tfresh",
                    "root\tfjxm",
                    "suppress\tfjxm\t复现",
                    "entry\tfjxm\t1\t复现\tfjxm\tfuxian-id",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().test_root = str(root)
        lua.execute(
            "rime_api = { get_user_data_dir = function() return test_root end }"
        )
        lua.execute(
            """
            test_store_calls = { entries = 0, refreshed = false }
            package.loaded["pantsu_store"] = {
              signature = function() return "fresh" end,
              ensure_runtime_files = function() return true end,
              entries = function(input)
                test_store_calls.entries = test_store_calls.entries + 1
                return {
                  {
                    word = "跳弹",
                    code = "tcdf",
                    base_code = "tcdfoa",
                    original_code = "tcdf",
                    active = true,
                    path = "pantsu.cizu.dict.yaml",
                    id = "tiaodan-id",
                  },
                }
              end,
              override_roots = function() return { tcdf = true } end,
              self_word_roots = function() return {} end,
              invalidate_signature = function() end,
              refresh_external_state = function()
                if not test_store_calls.refreshed then
                  test_store_calls.refreshed = true
                  return true
                end
                return false
              end
            }
            """
        )
        lua.execute(
            f"package.path = '{args.rime_dir / 'lua' / '?.lua'};' .. package.path"
        )
        dynamic = lua.eval("require('pantsu_dynamic')")[0]

        state, matched_root = dynamic.match("tcdf")
        assert matched_root == "tcdf"
        assert state["entries"][1]["word"] == "跳弹"
        content = (root / "build/pantsu_dynamic_candidates.tsv").read_text(
            encoding="utf-8"
        )
        assert "root\tfjxm" in content
        assert "entry\tfjxm\t1\t复现\tfjxm\tfuxian-id" in content
        assert "root\ttcdf" in content
        assert "entry\ttcdf\t1\t跳弹\ttcdf\ttiaodan-id" in content

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "build").mkdir(exist_ok=True)
        (root / "user.yaml").write_text("last_build_time: 1\n", encoding="utf-8")
        (root / "pantsu_dynamic_roots.tsv").write_text(
            "\n".join(
                [
                    "format\t9",
                    "build\t1",
                    "signature\tsig1",
                    "root\taaa",
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
                    "signature\tsig1",
                    "root\taaa",
                    "suppress\taaa\t甲词",
                    "entry\taaa\t1\t甲词\taaav\told-id",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().test_root = str(root)
        lua.execute(
            "rime_api = { get_user_data_dir = function() return test_root end }"
        )
        lua.execute(
            """
            test_store_calls = { signature = "sig1", refresh = false }
            package.loaded["pantsu_store"] = {
              signature = function() return test_store_calls.signature end,
              ensure_runtime_files = function() return true end,
              entries = function(input)
                return {
                  {
                    word = input == "ddd" and "丁词" or "丙词",
                    code = input == "ddd" and "dddv" or "cccv",
                    base_code = input == "ddd" and "dddv" or "cccv",
                    original_code = input == "ddd" and "dddv" or "cccv",
                    active = true,
                    path = "pantsu.cizu.dict.yaml",
                    id = input .. "-id",
                  },
                }
              end,
              override_roots = function() return {} end,
              self_word_roots = function() return {} end,
              invalidate_signature = function() end,
              refresh_external_state = function()
                if test_store_calls.refresh then
                  test_store_calls.refresh = false
                  return true
                end
                return false
              end
            }
            """
        )
        lua.execute(
            f"package.path = '{args.rime_dir / 'lua' / '?.lua'};' .. package.path"
        )
        dynamic = lua.eval("require('pantsu_dynamic')")[0]

        assert dynamic.refresh_codes(
            lua.table_from(["cccv"]),
            lua.table_from(["丙词"]),
            3,
        )
        lua.globals().test_store_calls["signature"] = "sig2"
        lua.globals().test_store_calls["refresh"] = True
        (root / "pantsu_dynamic_roots.tsv").write_text(
            "\n".join(
                [
                    "format\t9",
                    "build\t1",
                    "signature\tsig2",
                    "root\taaa",
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
                    "signature\tsig2",
                    "root\taaa",
                    "suppress\taaa\t新词",
                    "entry\taaa\t1\t新词\taaav\tnew-id",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        assert dynamic.refresh_codes(
            lua.table_from(["dddv"]),
            lua.table_from(["丁词"]),
            3,
        )
        content = (root / "build/pantsu_dynamic_candidates.tsv").read_text(
            encoding="utf-8"
        )
        assert "entry\taaa\t1\t新词\taaav\tnew-id" in content
        assert "entry\taaa\t1\t甲词\taaav\told-id" not in content
        assert "entry\tddd\t1\t丁词\tdddv\tddd-id" in content

    print("PASS pantsu_dynamic lazy root match: no rebuild on typing")


if __name__ == "__main__":
    main()
