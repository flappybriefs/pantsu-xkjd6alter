#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

try:
    from lupa import LuaRuntime
except ImportError as exc:
    raise SystemExit("lupa is required") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rime-dir", type=Path, default=Path.cwd())
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "opencc").mkdir()
        (root / "opencc/pantsu_es.txt").write_text(
            "身份证\t身份证 🪪\n手机\t手机 📱 📲\n"
            "好\t好 👌 👍 OK\n",
            encoding="utf-8",
        )

        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().test_root = str(root)
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
            function make_env(enabled)
              return {
                engine = {
                  context = {
                    get_option = function(_, name)
                      return name == "show_es" and enabled or false
                    end,
                  },
                },
              }
            end
            rime_api = { get_user_data_dir = function() return test_root end }
            """
        )
        lua.execute(
            f"package.path = '{args.rime_dir / 'lua' / '?.lua'};' .. package.path"
        )
        lua.execute("emoji = require('pantsu.pantsu_lazy_emoji')")

        lua.execute(
            """
            yielded = {}
            emoji.func(make_input({ Candidate("table", 0, 2, "身份证", "id") }),
                make_env(false))
            assert(#yielded == 1)
            assert(yielded[1].text == "身份证")
            assert(emoji.map == nil)
            """
        )

        lua.execute(
            """
            yielded = {}
            emoji.func(make_input({
              Candidate("table", 0, 2, "身份证", "id"),
              Candidate("table", 0, 2, "未知词", ""),
            }), make_env(true))
            assert(#yielded == 3)
            assert(yielded[1].text == "身份证")
            assert(yielded[1].comment == "id")
            assert(yielded[2].text == "🪪")
            assert(yielded[2].comment == "身份证")
            assert(yielded[3].text == "未知词")
            assert(emoji.map ~= nil)
            """
        )

        lua.execute(
            """
            yielded = {}
            emoji.func(make_input({
              Candidate("table", 0, 2, "未知1", ""),
              Candidate("table", 0, 2, "未知2", ""),
              Candidate("table", 0, 2, "未知3", ""),
              Candidate("table", 0, 2, "未知4", ""),
              Candidate("table", 0, 2, "未知5", ""),
              Candidate("table", 0, 2, "未知6", ""),
              Candidate("table", 0, 2, "手机", ""),
              Candidate("table", 0, 2, "身份证", ""),
            }), make_env(true))
            assert(#yielded == 10)
            assert(yielded[7].text == "手机")
            assert(yielded[8].text == "📱")
            assert(yielded[8].comment == "手机")
            assert(yielded[9].text == "📲")
            assert(yielded[9].comment == "手机")
            assert(yielded[10].text == "身份证")
            assert(yielded[10].comment == "")
            """
        )

        lua.execute(
            """
            yielded = {}
            emoji.func(make_input({
              Candidate("table", 0, 2, "好", ""),
            }), make_env(true))
            assert(#yielded == 4)
            assert(yielded[1].text == "好")
            assert(yielded[2].text == "👌")
            assert(yielded[3].text == "👍")
            assert(yielded[4].text == "OK")
            assert(yielded[4].comment == "好")
            """
        )

    print("PASS pantsu_lazy_emoji: candidate-triggered lazy lookup")


if __name__ == "__main__":
    main()
