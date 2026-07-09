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
        topup = require("pantsu.pantsu_for_topup")

        function make_key(ch)
          return {
            keycode = string.byte(ch),
            release = function() return false end,
            ctrl = function() return false end,
            alt = function() return false end,
          }
        end

        function make_context(input)
          local context = {
            input = input,
            committed = {},
          }
          function context:get_option(_) return false end
          function context:get_selected_candidate()
            if self.input == "hlbl" then
              return { text = "活剥" }
            end
            if self.input == "v" then
              return { text = "有" }
            end
            if self.input == "abcd" then
              return { text = "普通候选" }
            end
            return nil
          end
          function context:commit()
            table.insert(self.committed, self.input)
            self.input = ""
          end
          function context:clear()
            self.input = ""
          end
          function context:push_input(ch)
            self.input = self.input .. ch
          end
          function context:pop_input(n)
            self.input = self.input:sub(1, #self.input - n)
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
                    if key == "topup/topup_with" then
                      return "avuio;/"
                    end
                    if key == "speller/alphabet" then
                      return "abcdefghijklmnopqrstuvwxyz;/`"
                    end
                    return ""
                  end,
                  get_int = function(_, key)
                    if key == "topup/min_length" then return 4 end
                    if key == "topup/min_length_danzi" then return 2 end
                    if key == "topup/max_length" then return 6 end
                    return 0
                  end,
                  get_bool = function(_, key)
                    if key == "topup/auto_clear" then return true end
                    if key == "topup/topup_command" then return false end
                    return false
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
        ctx = make_context("abcd")
        env = make_env(ctx)
        topup.init(env)
        assert(topup.func(make_key("x"), env) == 2)
        assert(#ctx.committed == 1)
        assert(ctx.committed[1] == "abcd")
        assert(ctx.input == "")
        """
    )

    lua.execute(
        """
        ctx = make_context("sdfs")
        env = make_env(ctx)
        topup.init(env)
        assert(topup.func(make_key("x"), env) == 2)
        assert(#ctx.committed == 0)
        assert(ctx.input == "")
        """
    )


if __name__ == "__main__":
    main()
