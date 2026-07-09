#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from lupa import LuaRuntime
except ImportError as exc:
    raise SystemExit("lupa is required") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rime-dir", type=Path, default=Path.cwd())
    args = parser.parse_args()

    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(
        """
        yielded = {}
        function yield(candidate)
          table.insert(yielded, candidate)
        end
        function Candidate(type, start, stop, text, comment)
          return {
            type = type,
            start = start,
            _end = stop,
            text = text,
            comment = comment or "",
          }
        end
        function ShadowCandidate(candidate, type, text, comment)
          return {
            shadow_of = candidate,
            type = type,
            start = candidate.start,
            _end = candidate._end,
            text = text,
            comment = comment or "",
            quality = candidate.quality,
          }
        end
        function make_input(candidates)
          return {
            iter = function()
              local index = 0
              return function()
                index = index + 1
                return candidates[index]
              end
            end,
          }
        end
        function make_env(input)
          return { engine = { context = { input = input } } }
        end
        """
    )
    lua.execute(
        """
        package.loaded["pantsu.pantsu_make_word_core"] = {
          mode = true,
          buffer = "测试词",
          preview_text = nil,
          last_error = nil,
          target_code = nil,
          start = function() end,
          prepare_preview = function() end,
        }
        """
    )
    lua.execute(
        f"package.path = '{args.rime_dir / 'lua' / '?.lua'};' .. package.path"
    )
    lua.execute("make_word_filter = require('pantsu.pantsu_make_word_filter')")
    lua.execute(
        """
        yielded = {}
        make_word_filter(make_input({ Candidate("table", 0, 1, "原候选", "") }),
            make_env("["))
        assert(#yielded == 1)
        assert(yielded[1].text == "测试词")
        assert(yielded[1].comment == "〔造词中〕〔空格保存〕")
        """
    )
    lua.execute(
        """
        package.loaded["pantsu.pantsu_make_word_core"].preview_text =
          "〔保存到 abc〕"
        yielded = {}
        make_word_filter(make_input({}), make_env("["))
        assert(yielded[1].comment == "〔造词中〕〔保存到 abc〕")
        """
    )
    lua.execute(
        """
        package.loaded["pantsu.pantsu_make_word_core"].buffer = ""
        yielded = {}
        make_word_filter(make_input({
            Candidate("table", 0, 4, "候选一", "~a"),
            Candidate("table", 0, 4, "候选二", "~b"),
        }), make_env("["))
        assert(#yielded == 2)
        assert(yielded[1].text == "候选一")
        assert(yielded[1].comment == "~a〔造词中〕")
        assert(yielded[2].comment == "~b")
        """
    )
    lua.execute(
        """
        yielded = {}
        make_word_filter(make_input({
            Candidate("table", 0, 4, "继续选词", ""),
        }), make_env("abcd"))
        assert(yielded[1].comment == "〔造词中〕")
        """
    )
    print("PASS pantsu_make_word_filter: active prompt")


if __name__ == "__main__":
    main()
