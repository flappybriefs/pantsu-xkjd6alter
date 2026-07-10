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
    schema = (args.rime_dir / "pantsu.schema.yaml").read_text(
        encoding="utf-8-sig"
    )
    assert (
        "#    - lua_filter@*pantsu/pantsu_single_char"
        in schema
    )
    assert (args.rime_dir / "lua/pantsu/pantsu_single_char.lua").exists()

    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(
        f"package.path = '{args.rime_dir / 'lua' / '?.lua'};' .. package.path"
    )
    lua.execute(
        """
        yielded = {}
        function yield(candidate) table.insert(yielded, candidate) end
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
    lua.execute("single_char = require('pantsu.pantsu_single_char')")
    lua.execute(
        """
        single_char(make_input({
          { text = "词组" }, { text = "单" }, { text = "短语" },
        }))
        assert(yielded[1].text == "单")
        assert(yielded[2].text == "词组")
        assert(yielded[3].text == "短语")
        """
    )
    print("PASS pantsu_single_char: retained but schema-disabled")


if __name__ == "__main__":
    main()
