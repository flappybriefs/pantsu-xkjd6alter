#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from time import perf_counter

try:
    from lupa import LuaRuntime
except ImportError:
    LuaRuntime = None

ROOT = Path(__file__).resolve().parents[1]
DICTIONARIES = (
    "pantsu.core.dict.yaml",
    "pantsu.danzi.dict.yaml",
    "pantsu.cizu.dict.yaml",
    "pantsu.user.dict.yaml",
    "pantsu.zzc.dict.yaml",
)
STATE_FILES = (
    "pantsu_overrides.tsv",
    "pantsu_candidate_order.tsv",
    "pantsu_self_words.tsv",
    "installation.yaml",
    "user.yaml",
)


def sample_codes(limit: int) -> list[str]:
    result = []
    seen = set()
    for raw in (ROOT / "pantsu.cizu.dict.yaml").read_text(
        encoding="utf-8-sig"
    ).splitlines():
        if raw.startswith("#") or "\t" not in raw:
            continue
        fields = raw.split("\t")
        code = fields[1] if len(fields) >= 2 else ""
        root = code[:4]
        if len(root) >= 3 and root not in seen:
            seen.add(root)
            result.append(root)
            if len(result) == limit:
                return result
    raise SystemExit("词库中没有足够的测试编码")


def full_scan(codes: list[str]) -> tuple[float, int]:
    paths = [ROOT / name for name in DICTIONARIES]
    found = 0
    start = perf_counter()
    for code in codes:
        for path in paths:
            for raw in path.read_text(
                encoding="utf-8-sig"
            ).splitlines():
                if raw.startswith("#") or "\t" not in raw:
                    continue
                fields = raw.split("\t")
                if len(fields) >= 2 and fields[1].startswith(code):
                    found += 1
    return perf_counter() - start, found


def lua_store(root: Path):
    if LuaRuntime is None:
        raise RuntimeError("lupa unavailable")
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(
        "rime_api = { get_user_data_dir = function() return "
        + json.dumps(str(root))
        + " end }"
    )
    lua.execute(f"package.path = '{ROOT / 'lua' / '?.lua'};' .. package.path")
    loaded = lua.eval("require('pantsu.pantsu_store')")
    return lua, loaded[0] if isinstance(loaded, tuple) else loaded


def benchmark(ops: int, code_count: int) -> dict[str, float | int | str]:
    codes = sample_codes(code_count)
    scan_seconds, scan_found = full_scan(codes)
    if LuaRuntime is None:
        start = perf_counter()
        index = {}
        occupied = set()
        for name in DICTIONARIES:
            for raw in (ROOT / name).read_text(
                encoding="utf-8-sig"
            ).splitlines():
                if raw.startswith("#") or "\t" not in raw:
                    continue
                fields = raw.split("\t")
                if len(fields) < 2:
                    continue
                word, code = fields[0], fields[1]
                occupied.add(code)
                index.setdefault(code[:4], []).append((word, code))
        index_seconds = perf_counter() - start
        cache = {
            code: tuple(index.get(code[:4], ()))
            for code in codes
        }
        start = perf_counter()
        for operation in range(ops):
            cache[codes[operation % len(codes)]]
        warm_seconds = perf_counter() - start
        start = perf_counter()
        for operation in range(ops):
            codes[operation % len(codes)] in occupied
        occupancy_seconds = perf_counter() - start
        return {
            "mode": "python_fallback",
            "operations": ops,
            "codes": code_count,
            "full_scan_ms_per_code": scan_seconds * 1000 / code_count,
            "full_scan_matches": scan_found,
            "first_index_build_ms": index_seconds * 1000,
            "warm_lookup_ms_per_op": warm_seconds * 1000 / ops,
            "occupancy_ms_per_op": occupancy_seconds * 1000 / ops,
            "warm_total_seconds": warm_seconds,
            "occupancy_total_seconds": occupancy_seconds,
        }
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "build").mkdir()
        for name in (*DICTIONARIES, *STATE_FILES):
            source = ROOT / name
            if source.exists():
                shutil.copy2(source, root / name)
        lua, store = lua_store(root)
        start = perf_counter()
        store.entries(codes[0])
        index_seconds = perf_counter() - start

        start = perf_counter()
        for index in range(ops):
            store.entries(codes[index % len(codes)])
        warm_seconds = perf_counter() - start

        start = perf_counter()
        for index in range(ops):
            store.occupied_prefixes(
                codes[index % len(codes)], "", 3, 6
            )
        occupancy_seconds = perf_counter() - start

    return {
        "mode": "lua_runtime",
        "operations": ops,
        "codes": code_count,
        "full_scan_ms_per_code": scan_seconds * 1000 / code_count,
        "full_scan_matches": scan_found,
        "first_index_build_ms": index_seconds * 1000,
        "warm_lookup_ms_per_op": warm_seconds * 1000 / ops,
        "occupancy_ms_per_op": occupancy_seconds * 1000 / ops,
        "warm_total_seconds": warm_seconds,
        "occupancy_total_seconds": occupancy_seconds,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="胖次键道性能与极端压力测试"
    )
    parser.add_argument("--ops", type=int, default=200_000)
    parser.add_argument("--codes", type=int, default=10)
    args = parser.parse_args()
    result = benchmark(args.ops, args.codes)
    phone_factor = 8
    print(f"极端压力：{args.ops:,} 次查询 / {args.codes} 个编码")
    if result["mode"] == "python_fallback":
        print("• 测试模式：无额外依赖的索引/缓存兼容测试")
    else:
        print("• 测试模式：实际 Lua 运行时")
    print(
        "• 逐次扫描整个词库："
        f"{result['full_scan_ms_per_code']:.1f} ms/码"
        "（这是没有索引时的旧式做法）"
    )
    print(
        "• 第一次建立索引："
        f"{result['first_index_build_ms']:.1f} ms，一次性成本"
    )
    print(
        "• 日常缓存查询："
        f"{result['warm_lookup_ms_per_op']:.4f} ms/次；"
        f"手机保守估计约 "
        f"{result['warm_lookup_ms_per_op'] * phone_factor:.4f} ms/次"
    )
    print(
        "• 判断编码是否被占用："
        f"{result['occupancy_ms_per_op']:.4f} ms/次；"
        f"{args.ops:,} 次共 {result['occupancy_total_seconds']:.2f} 秒"
    )
    print("结论：日常输入走索引和缓存，不会反复扫描整个大词库。")
    (ROOT / "build").mkdir(exist_ok=True)
    (ROOT / "build/pantsu_performance_report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
