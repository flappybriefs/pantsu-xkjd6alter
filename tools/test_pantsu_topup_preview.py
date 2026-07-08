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
            quality = 0,
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
          return {
            engine = {
              context = { input = input },
              schema = {
                config = {
                  get_string = function(_, key)
                    if key == "topup/topup_with" then
                      return "avuio;/"
                    end
                    return ""
                  end,
                },
              },
            },
          }
        end
        """
    )
    lua.execute(
        """
        package.loaded["pantsu.pantsu_store"] = {
          entries = function(code)
            local rows = {
              hlbl = {
                { word = "活剥", code = "hlbl", active = true },
                { word = "哈拉布拉", code = "hlblo", active = true },
              },
              hlblv = {
                { word = "或泊", code = "hlblv", active = false },
              },
              v = {
                { word = "有了", code = "va", active = true },
                { word = "有", code = "v", active = true },
              },
              abcdv = {
                { word = "完整词", code = "abcdv", active = true },
              },
            }
            return rows[code] or {}
          end,
        }
        """
    )
    lua.execute(
        f"package.path = '{args.rime_dir / 'lua' / '?.lua'};' .. package.path"
    )
    lua.execute("preview = require('pantsu.pantsu_topup_preview')")

    lua.execute(
        """
        yielded = {}
        env = make_env("hlblv")
        preview.init(env)
        preview.func(make_input({}), env)
        assert(#yielded == 1)
        assert(yielded[1].text == "活剥有")
        assert(yielded[1].type == "pantsu_topup_preview")
        """
    )

    lua.execute(
        """
        yielded = {}
        env = make_env("abcdv")
        preview.init(env)
        preview.func(make_input({ Candidate("table", 0, 5, "完整词", "") }), env)
        assert(#yielded == 1)
        assert(yielded[1].text == "完整词")
        """
    )


if __name__ == "__main__":
    main()
