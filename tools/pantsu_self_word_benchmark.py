#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TXJX = Path.home() / "Downloads/txjx"
SIZES_KB = (50, 100, 250, 500)

for dependency in (
    Path("/tmp/audit-rime-jiandao-deps"),
    ROOT / "build/python",
):
    if dependency.is_dir():
        sys.path.insert(0, str(dependency))

try:
    from lupa import LuaRuntime
except ImportError:
    LuaRuntime = None


def lua_module(data: Path, lua_directory: Path, name: str):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(
        "rime_api = { get_user_data_dir = function() return "
        + json.dumps(str(data))
        + " end }"
    )
    lua.execute(
        f"package.path = '{lua_directory / '?.lua'};' .. package.path"
    )
    loaded = lua.eval(f"require('{name}')")
    return lua, loaded[0] if isinstance(loaded, tuple) else loaded


def rows_for_size(
    size_kb: int,
    *,
    pantsu: bool,
) -> list[tuple[str, str]]:
    target = size_kb * 1024
    rows: list[tuple[str, str]] = []
    total = 0
    index = 0
    while total < target:
        word = f"性能词{index:06d}"
        code = f"ab{index:05d}"
        rows.append((word, code))
        line = (
            f"word\t{word}\t{code}\t0\t1\tbenchmark\n"
            if pantsu
            else f"{word}\t{code}\n"
        )
        total += len(line.encode())
        index += 1
    return rows


def pantsu_measure(
    rows: list[tuple[str, str]],
    repeats: int,
) -> float:
    with tempfile.TemporaryDirectory() as directory:
        data = Path(directory)
        (data / "build").mkdir()
        (data / "installation.yaml").write_text(
            "installation_id: benchmark\n",
            encoding="utf-8",
        )
        lines = ["version\t1"]
        lines.extend(
            f"word\t{word}\t{code}\t0\t1\tbenchmark"
            for word, code in rows
        )
        (data / "pantsu_self_words.tsv").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        lua, store = lua_module(data, ROOT / "lua", "pantsu_store")
        store.self_words()
        values = []
        for index in range(repeats):
            word, code = rows[index % len(rows)]
            update = lua.table_from({
                "word": word,
                "code": code,
                "active": True,
            })
            start = perf_counter()
            result = store.update_self_words(lua.table_from([update]), False)
            values.append((perf_counter() - start) * 1000)
            if isinstance(result, tuple) and not result[0]:
                raise RuntimeError(f"pantsu update failed: {result}")
        return statistics.median(values)


def txjx_fixture(
    data: Path,
    rows: list[tuple[str, str]],
) -> None:
    (data / "zzc").mkdir()
    (data / "zzc/runtime_exact.tsv").write_text(
        "".join(f"{word}\t{code}\n" for word, code in rows),
        encoding="utf-8",
    )
    (data / "txjx.zzc.dict.yaml").write_text(
        "# Rime dictionary\n"
        "# encoding: utf-8\n"
        "---\n"
        "name: txjx.zzc\n"
        'version: "benchmark"\n'
        "sort: by_weight\n"
        "...\n",
        encoding="utf-8",
    )


def warm_txjx_cache(lua, core, runtime_file: Path) -> None:
    inject = lua.eval(
        """
        function(core, file_path)
            local loader
            for index = 1, 32 do
                local name, value = debug.getupvalue(
                    core.pending_candidates_for_input, index)
                if not name then break end
                if name == "load_runtime_exact_cache" then
                    loader = value
                    break
                end
            end
            if not loader then return false end
            local cache = {}
            for line in io.lines(file_path) do
                local word, code = line:match("^([^\\t]+)\\t([^\\t%s]+)$")
                if word and code then
                    local bucket = cache[code]
                    if not bucket then
                        bucket = {}
                        cache[code] = bucket
                    end
                    bucket[#bucket + 1] = {
                        word = word,
                        code = code,
                        source = "runtime",
                    }
                end
            end
            local cache_set, loaded_set = false, false
            for index = 1, 32 do
                local name = debug.getupvalue(loader, index)
                if not name then break end
                if name == "runtime_exact_cache" then
                    debug.setupvalue(loader, index, cache)
                    cache_set = true
                elseif name == "runtime_exact_loaded" then
                    debug.setupvalue(loader, index, true)
                    loaded_set = true
                end
            end
            return cache_set and loaded_set
        end
        """
    )
    if not inject(core, str(runtime_file)):
        raise RuntimeError("无法预热天行键 runtime cache")


def txjx_measure(
    rows: list[tuple[str, str]],
    txjx: Path,
    action: str,
    repeats: int,
) -> float:
    with tempfile.TemporaryDirectory() as directory:
        data = Path(directory)
        txjx_fixture(data, rows)
        lua, core = lua_module(data, txjx / "lua", "txjx_zzc_core")
        warm_txjx_cache(lua, core, data / "zzc/runtime_exact.tsv")
        values = []
        for index in range(repeats):
            word, code = rows[index % len(rows)]
            start = perf_counter()
            if action == "delete":
                result = core.delete_word_at_code(word, code)
            else:
                result = core.move_word_to_code(
                    word,
                    code,
                    code + "x",
                    False,
                    None,
                )
            values.append((perf_counter() - start) * 1000)
            first = result[0] if isinstance(result, tuple) else result
            if not first:
                raise RuntimeError(f"txjx {action} failed: {result}")
        return statistics.median(values)


def benchmark(txjx: Path, repeats: int) -> list[dict[str, float | int]]:
    results = []
    for size in SIZES_KB:
        pantsu_rows = rows_for_size(size, pantsu=True)
        txjx_rows = rows_for_size(size, pantsu=False)
        results.append({
            "size_kb": size,
            "pantsu_rows": len(pantsu_rows),
            "txjx_rows": len(txjx_rows),
            "pantsu_update_ms": pantsu_measure(
                pantsu_rows,
                repeats,
            ),
            "txjx_delete_ms": txjx_measure(
                txjx_rows,
                txjx,
                "delete",
                repeats,
            ),
            "txjx_snapshot_ms": txjx_measure(
                txjx_rows,
                txjx,
                "snapshot",
                repeats,
            ),
        })
    return results


def print_report(results: list[dict[str, float | int]]) -> None:
    print("自造词写入性能（真实 Lua、缓存已加载、中位数）")
    print("大小   胖次更新      天行键删除    天行键替换/前移")
    for row in results:
        print(
            f"{row['size_kb']:>3}KB  "
            f"{row['pantsu_update_ms']:>9.3f}ms  "
            f"{row['txjx_delete_ms']:>9.3f}ms  "
            f"{row['txjx_snapshot_ms']:>12.3f}ms"
        )
    largest = results[-1]
    delete_ratio = (
        float(largest["pantsu_update_ms"])
        / float(largest["txjx_delete_ms"])
    )
    snapshot_ratio = (
        float(largest["pantsu_update_ms"])
        / float(largest["txjx_snapshot_ms"])
    )
    print(
        f"500KB：胖次为天行键删除的 {delete_ratio:.2f} 倍，"
        f"为替换/前移 snapshot 的 {snapshot_ratio:.2f} 倍。"
    )
    print(
        "说明：不计首次读取缓存；胖次落盘完整权威快照并回读校验；"
        "天行键追加操作日志，并按需重写 runtime_exact。"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="自造词写入分档性能测试")
    parser.add_argument(
        "--txjx",
        type=Path,
        default=DEFAULT_TXJX,
        help="天行键目录",
    )
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if LuaRuntime is None:
        raise SystemExit(
            "缺少 lupa，无法执行真实 Lua 测试。"
            "可安装到 /tmp/audit-rime-jiandao-deps 后重试。"
        )
    if not (args.txjx / "lua/txjx_zzc_core.lua").exists():
        raise SystemExit(f"没有找到天行键：{args.txjx}")
    results = benchmark(args.txjx, max(1, args.repeats))
    print_report(results)
    (ROOT / "build").mkdir(exist_ok=True)
    (ROOT / "build/pantsu_self_word_benchmark.json").write_text(
        json.dumps(
            {
                "mode": "actual_lua",
                "repeats": max(1, args.repeats),
                "txjx": str(args.txjx.resolve()),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
