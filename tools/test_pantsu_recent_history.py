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
    parser.add_argument(
        "--rime-dir",
        type=Path,
        default=Path.home() / "Library" / "Rime",
    )
    args = parser.parse_args()

    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(
        f"package.path = '{args.rime_dir / 'lua' / '?.lua'};' .. package.path"
    )
    lua.execute(
        """
        yielded = {}
        yield = function(cand) yielded[#yielded + 1] = cand end
        Candidate = function(kind, start_pos, end_pos, text, comment)
          return {
            type = kind,
            start = start_pos,
            _end = end_pos,
            text = text,
            comment = comment,
          }
        end

        local function notifier()
          return {
            callback = nil,
            connect = function(self, callback)
              self.callback = callback
              return { disconnect = function() self.callback = nil end }
            end,
          }
        end

        test_context = {
          input = "",
          committed = "",
          update_notifier = notifier(),
          commit_notifier = notifier(),
          get_commit_text = function(self) return self.committed end,
        }
        test_config = {
          get_string = function(self, path)
            if path == "recent_history/input" then return ";;" end
          end,
          get_int = function(self, path)
            if path == "recent_history/size" then return 5 end
          end,
        }
        test_env = {
          engine = {
            context = test_context,
            schema = { config = test_config },
          },
        }
        test_segment = { start = 0, _end = 2 }
        """
    )
    module = lua.eval("require('pantsu.pantsu_recent_history')")[0]
    context = lua.globals().test_context
    env = lua.globals().test_env
    segment = lua.globals().test_segment
    module.init(env)

    def commit(source: str, text: str) -> None:
        context["input"] = source
        context["committed"] = text
        context["update_notifier"]["callback"](context)
        context["commit_notifier"]["callback"](context)

    for source, text in [
        ("aaa", "第一条"),
        ("bbb", "第二条，含标点"),
        ("ccc", "第一条"),
        ("ddd", "第三条"),
        ("eee", "第四条"),
        ("fff", "第五条"),
        ("ggg", "第六条"),
    ]:
        commit(source, text)

    lua.globals().yielded = lua.table()
    module.func(";;", segment, env)
    yielded = lua.globals().yielded
    assert [yielded[index]["text"] for index in range(1, 6)] == [
        "第六条",
        "第五条",
        "第四条",
        "第三条",
        "第一条",
    ]
    assert yielded[1]["comment"] == "〔历史1〕"

    context["input"] = ""
    context["committed"] = "第三条"
    context["update_notifier"]["callback"](context)
    context["commit_notifier"]["callback"](context)
    lua.globals().yielded = lua.table()
    module.func(";;", segment, env)
    yielded = lua.globals().yielded
    assert yielded[1]["text"] == "第六条"
    assert len([yielded[index] for index in range(1, 6)]) == 5

    lua.globals().yielded = lua.table()
    module.func(";h", segment, env)
    assert len(lua.globals().yielded) == 0
    module.fini(env)
    print("PASS recent history: exact trigger, newest first, dedupe, replay guard")


if __name__ == "__main__":
    main()
