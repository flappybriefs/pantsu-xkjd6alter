#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from time import perf_counter

try:
    from lupa import LuaRuntime
except ImportError as exc:
    raise SystemExit("lupa is required") from exc


DICTIONARIES = [
    "pantsu.core.dict.yaml",
    "pantsu.danzi.dict.yaml",
    "pantsu.cizu.dict.yaml",
    "pantsu.temp.dict.yaml",
    "pantsu.user.dict.yaml",
    "pantsu.zzc.dict.yaml",
    "pantsu.waigua.dict.yaml",
]
HEADER = '---\nname: test\nversion: "1"\nsort: original\n...\n'


def code_for(index: int) -> str:
    letters = []
    value = index
    for _ in range(4):
        letters.append(chr(ord("a") + value % 26))
        value //= 26
    return "".join(reversed(letters)) + "v"


def build_store(source: Path, count: int):
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    (root / "build").mkdir()
    for name in DICTIONARIES:
        content = HEADER
        if name == "pantsu.zzc.dict.yaml":
            content += "#region <自造词>#\n#endregion <自造词>#\n"
        (root / name).write_text(content, encoding="utf-8")
    records = ["version\t1"]
    for index in range(count):
        records.append(
            f"word\t测试词{index}\t{code_for(index)}\t1\t{index + 1}\ttest"
        )
    (root / "pantsu_self_words.tsv").write_text(
        "\n".join(records) + "\n",
        encoding="utf-8",
    )
    (root / "installation.yaml").write_text(
        "installation_id: test\n",
        encoding="utf-8",
    )
    (root / "user.yaml").write_text(
        "last_build_time: 1\n",
        encoding="utf-8",
    )

    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.globals().test_root = str(root)
    lua.execute(
        "rime_api = { get_user_data_dir = function() return test_root end }"
    )
    lua.execute(
        f"package.path = '{source / 'lua' / '?.lua'};' .. package.path"
    )
    store = lua.eval("require('pantsu_store')")[0]
    return temporary, lua, store


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rime-dir",
        type=Path,
        default=Path.home() / "Library" / "Rime",
    )
    args = parser.parse_args()

    temporary, lua, store = build_store(args.rime_dir, 20000)
    try:
        target = code_for(12345)
        expected = {
            record["word"]
            for _, record in store.self_words().items()
            if record["active"] and record["code"].startswith(target[:4])
        }
        bucket = store.self_word_candidates(target[:4])
        actual = {
            bucket[index]["word"]
            for index in range(1, len(bucket) + 1)
        }
        assert actual == expected

        update = lua.table_from([
            lua.table_from({
                "word": "新增分桶词",
                "code": "zzzzv",
                "active": True,
            })
        ])
        changed = store.update_self_words(update)
        assert changed[0] if isinstance(changed, tuple) else changed
        added = store.self_word_candidates("zzzz")
        assert any(
            added[index]["word"] == "新增分桶词"
            for index in range(1, len(added) + 1)
        )
        update[1]["active"] = False
        changed = store.update_self_words(update)
        assert changed[0] if isinstance(changed, tuple) else changed
        removed = store.self_word_candidates("zzzz")
        assert not any(
            removed[index]["word"] == "新增分桶词"
            for index in range(1, len(removed) + 1)
        )

        lua.globals().bucket_store = store
        lua.globals().bucket_root = target[:4]
        lua.execute(
            """
            function bucket_benchmark(rounds)
              local total = 0
              for _ = 1, rounds do
                for _, record in pairs(
                    bucket_store.self_word_candidates(bucket_root)) do
                  if record.active
                    and string.sub(record.code, 1, #bucket_root)
                        == bucket_root then
                    total = total + 1
                  end
                end
              end
              return total
            end
            function full_scan_benchmark(rounds)
              local total = 0
              local records = bucket_store.self_word_candidates("")
              for _ = 1, rounds do
                for _, record in pairs(records) do
                  if record.active
                    and string.sub(record.code, 1, #bucket_root)
                        == bucket_root then
                    total = total + 1
                  end
                end
              end
              return total
            end
            """
        )
        rounds = 200
        start = perf_counter()
        bucket_total = lua.globals().bucket_benchmark(rounds)
        bucket_ms = (perf_counter() - start) * 1000 / rounds
        start = perf_counter()
        full_total = lua.globals().full_scan_benchmark(rounds)
        full_ms = (perf_counter() - start) * 1000 / rounds
        assert bucket_total == full_total
        assert bucket_ms < full_ms
        print(
            "PASS self-word buckets: "
            f"20000 words, bucket={bucket_ms:.6f} ms, "
            f"full_scan={full_ms:.6f} ms, "
            f"speedup={full_ms / bucket_ms:.1f}x"
        )
    finally:
        temporary.cleanup()


if __name__ == "__main__":
    main()
