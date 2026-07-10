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
    assert "lua_translator@*pantsu/pantsu_english_fallback" in schema
    assert "enable_sentence: false # 不把未知输入拆成多个英文词" in schema
    assert "enable_completion: true # 有同前缀词时正常补全" in schema

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
            comment = comment or "" }
        end
        memory_calls = 0
        function Schema(name) return { schema_id = name } end
        function Memory(_, schema)
          assert(schema.schema_id == "pantsu.en")
          memory_calls = memory_calls + 1
          return {
            dict_lookup = function(_, code, predictive, limit)
              assert(predictive == true and limit == 1)
              return code == "insta" or code == "instagram"
            end,
            disconnect = function(self) self.disconnected = true end,
          }
        end
        test_context = { input = "]instagramg" }
        test_env = { engine = { context = test_context } }
        pantsuen_segment = {
          start = 0, _end = 11,
          has_tag = function(_, tag) return tag == "pantsuen" end,
        }
        normal_segment = {
          start = 0, _end = 10,
          has_tag = function() return false end,
        }
        """
    )
    lua.execute("module = require('pantsu.pantsu_english_fallback')")
    lua.execute(
        """
        yielded = {}
        module.func("instagramg", pantsuen_segment, test_env)
        assert(#yielded == 2)
        assert(yielded[1].text == "instagramg")
        assert(yielded[2].text == "Instagramg")
        assert(memory_calls == 1)
        """
    )
    lua.execute(
        """
        test_context.input = "]insta"
        yielded = {}
        module.func("insta", pantsuen_segment, test_env)
        assert(#yielded == 0)
        assert(memory_calls == 1)
        """
    )
    lua.execute(
        """
        test_context.input = "instagramg"
        yielded = {}
        module.func("instagramg", normal_segment, test_env)
        assert(#yielded == 0)
        assert(memory_calls == 1)
        module.fini(test_env)
        assert(test_env.prefix_memory == nil)
        """
    )
    print("PASS pantsu_english_fallback: lazy ]English prefix lookup or raw fallback")


if __name__ == "__main__":
    main()
