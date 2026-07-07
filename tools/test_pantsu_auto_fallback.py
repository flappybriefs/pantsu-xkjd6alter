#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from lupa import LuaRuntime
except ImportError as exc:
    raise SystemExit("lupa is required") from exc


def run_case(lua: LuaRuntime, script: str) -> None:
    lua.execute(
        """
        function make_key(ch)
          return {
            keycode = string.byte(ch),
            release = function() return false end,
            ctrl = function() return false end,
            alt = function() return false end,
          }
        end

        function make_context(input, has_candidate_after_push)
          local context = {
            input = input,
            committed = nil,
            push_count = 0,
          }
          function context:get_selected_candidate()
            if self.input == input then
              return { text = "旧候选" }
            end
            if has_candidate_after_push then
              return { text = "新候选" }
            end
            return nil
          end
          function context:push_input(ch)
            self.input = self.input .. ch
            self.push_count = self.push_count + 1
          end
          function context:pop_input(n)
            self.input = self.input:sub(1, #self.input - n)
          end
          function context:commit()
            self.committed = self.input
            self.input = ""
          end
          return context
        end

        function make_env(context)
          return {
            engine = {
              context = context,
              schema = {
                config = {
                  get_string = function(_, key)
                    if key == "speller/alphabet" then
                      return "abcdefghijklmnopqrstuvwxyz;/`"
                    end
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
    lua.execute(script)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rime-dir", type=Path, default=Path.cwd())
    args = parser.parse_args()

    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(
        f"package.path = '{args.rime_dir / 'lua' / '?.lua'};' .. package.path"
    )
    lua.execute("auto_fallback = require('pantsu_auto_fallback')")

    run_case(
        lua,
        """
        ctx = make_context("abcd", false)
        env = make_env(ctx)
        auto_fallback.init(env)
        assert(auto_fallback.func(make_key("x"), env) == 1)
        assert(ctx.committed == "abcd")
        assert(ctx.input == "x")
        assert(ctx.push_count == 2)
        """,
    )

    run_case(
        lua,
        """
        ctx = make_context("abc", true)
        env = make_env(ctx)
        auto_fallback.init(env)
        assert(auto_fallback.func(make_key("d"), env) == 1)
        assert(ctx.committed == nil)
        assert(ctx.input == "abcd")
        assert(ctx.push_count == 1)
        """,
    )

    run_case(
        lua,
        """
        ctx = make_context("hlbl", false)
        env = make_env(ctx)
        auto_fallback.init(env)
        assert(auto_fallback.func(make_key("v"), env) == 2)
        assert(ctx.committed == nil)
        assert(ctx.input == "hlbl")
        assert(ctx.push_count == 0)
        """,
    )

    run_case(
        lua,
        """
        ctx = make_context("abca", false)
        env = make_env(ctx)
        auto_fallback.init(env)
        assert(auto_fallback.func(make_key("x"), env) == 2)
        assert(ctx.committed == nil)
        assert(ctx.input == "abca")
        assert(ctx.push_count == 0)
        """,
    )

    run_case(
        lua,
        """
        ctx = make_context("]word", false)
        env = make_env(ctx)
        auto_fallback.init(env)
        assert(auto_fallback.func(make_key("s"), env) == 2)
        assert(ctx.committed == nil)
        assert(ctx.input == "]word")
        assert(ctx.push_count == 0)
        """,
    )


if __name__ == "__main__":
    main()
