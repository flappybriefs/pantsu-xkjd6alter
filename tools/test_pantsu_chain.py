#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from lupa import LuaRuntime
except ImportError as exc:
    raise SystemExit(
        "lupa is required; install it into a temporary directory and "
        "set PYTHONPATH"
    ) from exc


def result(value, size=2):
    if isinstance(value, tuple):
        return (*value, *([None] * size))[:size]
    return (value, *([None] * (size - 1)))[:size]


def entry(lua, word, code):
    return lua.table_from(
        {
            "word": word,
            "code": code,
            "base_code": code,
            "original_code": code,
            "active": True,
            "initial_active": True,
        }
    )


def model(lua, chain, entries):
    store = lua.table_from(
        {
            "entries": lambda _input, _profile=None: lua.table_from(entries),
        }
    )
    return chain.load(store, "root")


def codes(lua, mapping):
    return lua.eval(
        "function(values) return function(word) return values[word] or {} end end"
    )(lua.table_from({word: lua.table_from(items) for word, items in mapping.items()}))


def main():
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
    chain = lua.eval("require('pantsu.pantsu_chain')")[0]

    first = entry(lua, "甲词", "abcd")
    second = entry(lua, "乙词", "abcde")
    make_model = model(lua, chain, [first, second])
    full_codes = codes(
        lua,
        {
            "甲词": ["abcdef"],
            "乙词": ["abcdef"],
        },
    )
    ok, error = result(
        chain.push_down(
            make_model, first, "make_word", full_codes, lua.table()
        )
    )
    assert ok and error is None
    assert first["code"] == "abcde"
    assert second["code"] == "abcdef"

    fallback = entry(lua, "回退词", "abcd")
    short_blocker = entry(lua, "短阻塞词", "abcde")
    long_blocker = entry(lua, "长阻塞词", "abcdef")
    fallback_model = model(
        lua, chain, [fallback, short_blocker, long_blocker])
    fallback_codes = codes(
        lua,
        {
            "回退词": ["abcdef"],
            "短阻塞词": ["abcde"],
            "长阻塞词": ["abcdef"],
        },
    )
    ok, error = result(
        chain.push_down(
            fallback_model,
            fallback,
            "make_word",
            fallback_codes,
            lua.table(),
        )
    )
    assert ok and error is None
    assert fallback["code"] == "abcde"
    assert short_blocker["code"] == "abcde"
    assert long_blocker["code"] == "abcdef"

    ambiguous = entry(lua, "多码词", "abcd")
    edit_model = model(lua, chain, [ambiguous])
    ambiguous_codes = codes(
        lua,
        {
            "多码词": ["abcdea", "abcdfa"],
        },
    )
    ok, error = result(
        chain.push_down(
            edit_model,
            ambiguous,
            "candidate_edit",
            ambiguous_codes,
            lua.table(),
        )
    )
    assert ok is None and error == "ambiguous_full_code:多码词"
    assert ambiguous["code"] == "abcd"

    moved_from_old_code = entry(lua, "旧码候选", "abcde")
    moved_from_old_code["base_code"] = "abcdef"
    moved_from_old_code["original_code"] = "abcdef"
    moved_from_old_code["id"] = "stale-id"
    stale_model = model(lua, chain, [moved_from_old_code])
    stale_entry, stale_error = result(
        chain.locate_entry(stale_model, "旧码候选", "abcdef", "")
    )
    assert stale_entry is None
    assert stale_error == "entry_not_found"
    stale_entry, stale_error = result(
        chain.locate_entry(stale_model, "旧码候选", "abcdef", "stale-id")
    )
    assert stale_entry["word"] == "旧码候选"
    assert stale_entry["code"] == "abcde"
    assert stale_error is None

    moving = entry(lua, "编辑词", "abcd")
    immovable = entry(lua, "无后码词", "abcde")
    edit_model = model(lua, chain, [moving, immovable])
    edit_codes = codes(
        lua,
        {
            "编辑词": ["abcdef"],
            "无后码词": ["abcde"],
        },
    )
    ok, error = result(
        chain.push_down(
            edit_model, moving, "candidate_edit", edit_codes, lua.table()
        )
    )
    assert ok and error is None
    assert moving["code"] == "abcde"
    assert immovable["code"] == "abcde"

    first_fill = entry(lua, "第一补位", "abcde")
    second_fill = entry(lua, "第二补位", "abcdef")
    compact_model = model(lua, chain, [first_fill, second_fill])
    allow = lua.eval("function(entry, target) return #target >= 4 end")
    moved = chain.compact_gap(compact_model, "abcd", allow)
    assert len(moved) == 2
    assert first_fill["code"] == "abcd"
    assert second_fill["code"] == "abcde"

    left = entry(lua, "左候选", "abcde")
    right = entry(lua, "右候选", "abcdf")
    ambiguous_model = model(lua, chain, [left, right])
    moved = chain.compact_gap(ambiguous_model, "abcd", allow)
    assert len(moved) == 0
    assert left["code"] == "abcde"
    assert right["code"] == "abcdf"

    preferred = entry(lua, "高频候选", "abcde")
    other = entry(lua, "低频候选", "abcdf")
    preferred_model = model(lua, chain, [preferred, other])
    chooser = lua.eval(
        "function(candidates) "
        "for _, item in ipairs(candidates) do "
        "if item.word == '高频候选' then return item end end end"
    )
    moved = chain.compact_gap(
        preferred_model, "abcd", allow, chooser)
    assert len(moved) == 1
    assert preferred["code"] == "abcd"
    assert other["code"] == "abcdf"

    remaining = entry(lua, "同码保留", "abcd")
    descendant = entry(lua, "后续候选", "abcde")
    occupied_model = model(lua, chain, [remaining, descendant])
    moved = chain.compact_gap(occupied_model, "abcd", allow)
    assert len(moved) == 0
    assert descendant["code"] == "abcde"

    alias_a = entry(lua, "同词", "abcde")
    alias_b = entry(lua, "同词", "abcdf")
    alias_model = model(lua, chain, [alias_a, alias_b])
    moved = chain.compact_gap(alias_model, "abcd", allow)
    assert len(moved) == 0

    too_short = entry(lua, "两字词", "abcde")
    deeper = entry(lua, "三字词", "abcdef")
    legal_model = model(lua, chain, [too_short, deeper])
    selective = lua.eval(
        "function(entry, target) return entry.word == '三字词' end"
    )
    moved = chain.compact_gap(legal_model, "abc", selective)
    assert len(moved) == 1
    assert deeper["code"] == "abc"
    assert too_short["code"] == "abcde"

    print("PASS pantsu_chain policies: 10")


if __name__ == "__main__":
    main()
