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
        f"package.path = '{args.rime_dir / 'lua' / '?.lua'};' .. package.path"
    )
    lua.execute(
        """
        yielded = {}
        function yield(candidate) table.insert(yielded, candidate) end
        function Candidate(type, start, stop, text, comment)
          return { type = type, start = start, _end = stop, text = text,
            comment = comment or "", quality = 0 }
        end
        function ShadowCandidate(candidate, type, text, comment)
          return { shadow_of = candidate, type = type, start = candidate.start,
            _end = candidate._end, text = text, comment = comment or "",
            quality = candidate.quality }
        end
        function make_input(candidates)
          return { iter = function()
            local index = 0
            return function()
              index = index + 1
              return candidates[index]
            end
          end }
        end
        """
    )
    lua.execute("escape = require('pantsu.pantsu_text_escape')")
    assert lua.eval("escape.decode('第一\\\\n第二\\\\t缩进')") == "第一\n第二\t缩进"
    assert lua.eval("escape.decode('C:\\\\\\\\new')") == "C:\\new"
    assert lua.eval("escape.decode('保留\\\\q')") == r"保留\q"
    lua.execute(
        """
        yielded = {}
        escape.func(make_input({
          Candidate("table", 0, 4, "甲\\\\n乙\\\\t丙", "提示"),
          Candidate("table", 0, 4, "普通候选", ""),
        }), {})
        assert(#yielded == 2)
        assert(yielded[1].text == "甲\\n乙\\t丙")
        assert(yielded[1].comment == "提示")
        assert(yielded[2].text == "普通候选")
        """
    )
    print("PASS pantsu_text_escape: controlled candidate escapes")


if __name__ == "__main__":
    main()
