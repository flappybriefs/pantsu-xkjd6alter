#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_FILES = [
    "pantsu_overrides.tsv",
    "pantsu_candidate_order.tsv",
    "pantsu.user.dict.yaml",
    "pantsu_history.tsv",
]
DICTIONARIES = [
    "pantsu.core.dict.yaml",
    "pantsu.danzi.dict.yaml",
    "pantsu.cizu.dict.yaml",
    "pantsu.temp.dict.yaml",
    "pantsu.user.dict.yaml",
    "pantsu.waigua.dict.yaml",
]


def atomic_write(path: Path, text: str) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def backup() -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = ROOT / "backups" / stamp
    target.mkdir(parents=True, exist_ok=True)
    for name in STATE_FILES:
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, target / name)
    snapshots = sorted((ROOT / "backups").glob("*"))
    for old in snapshots[:-10]:
        shutil.rmtree(old)
    print(target)
    return target


def restore(name: str) -> None:
    source = ROOT / "backups" / name
    if not source.is_dir():
        raise SystemExit(f"备份不存在：{source}")
    backup()
    for path in source.iterdir():
        shutil.copy2(path, ROOT / path.name)
    print(f"已恢复 {source.name}")


def parse_overrides(path: Path) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    if not path.exists():
        return result
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        fields = raw.split("\t")
        if fields and fields[0] == "entry" and len(fields) >= 10:
            result[fields[1]] = fields
    return result


def write_overrides(entries: dict[str, list[str]]) -> None:
    lines = ["version\t1"]
    lines.extend("\t".join(entries[key]) for key in sorted(entries))
    atomic_write(ROOT / "pantsu_overrides.tsv", "\n".join(lines) + "\n")


def merge_sync(directories: list[str]) -> None:
    backup()
    merged = parse_overrides(ROOT / "pantsu_overrides.tsv")
    conflicts: list[str] = []
    for directory in directories:
        incoming = parse_overrides(Path(directory) / "pantsu_overrides.tsv")
        for key, record in incoming.items():
            current = merged.get(key)
            if current is None or int(record[8]) > int(current[8]):
                merged[key] = record
            elif int(record[8]) == int(current[8]) and record != current:
                conflicts.append("\t".join(["override", key, *current, *record]))
    write_overrides(merged)

    order_sources = [ROOT / "pantsu_candidate_order.tsv"]
    order_sources += [
        Path(directory) / "pantsu_candidate_order.tsv"
        for directory in directories
    ]
    order_sources = [path for path in order_sources if path.exists()]
    if order_sources:
        newest = max(order_sources, key=lambda path: path.stat().st_mtime_ns)
        shutil.copy2(newest, ROOT / "pantsu_candidate_order.tsv")

    merge_self_words(directories, conflicts)
    if conflicts:
        atomic_write(
            ROOT / "pantsu_sync_conflicts.tsv",
            "\n".join(conflicts) + "\n",
        )
    print(f"合并完成：{len(merged)} 条覆盖，{len(conflicts)} 条冲突")


def installation_id() -> str:
    path = ROOT / "installation.yaml"
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("installation_id:"):
            return raw.split(":", 1)[1].strip()
    return "unknown"


def sync_export() -> None:
    target = ROOT / "sync" / installation_id()
    target.mkdir(parents=True, exist_ok=True)
    for name in STATE_FILES:
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, target / name)
    print(f"已导出同步状态到 {target}")


def sync_merge() -> None:
    local_id = installation_id()
    directories = [
        str(path)
        for path in (ROOT / "sync").iterdir()
        if path.is_dir() and path.name != local_id
    ]
    if not directories:
        print("没有发现其他设备的同步状态")
        return
    merge_sync(directories)


def self_word_lines(path: Path) -> tuple[list[str], int, int]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    start = lines.index("#region <自造词>#")
    end = lines.index("#endregion <自造词>#")
    return lines, start, end


def merge_self_words(directories: list[str], conflicts: list[str]) -> None:
    target = ROOT / "pantsu.user.dict.yaml"
    lines, start, end = self_word_lines(target)
    by_word: dict[str, set[str]] = {}
    for raw in lines[start + 1 : end]:
        if "\t" in raw:
            word, code = raw.split("\t", 1)
            by_word.setdefault(word, set()).add(code)
    for directory in directories:
        source = Path(directory) / "pantsu.user.dict.yaml"
        if not source.exists():
            continue
        incoming, incoming_start, incoming_end = self_word_lines(source)
        for raw in incoming[incoming_start + 1 : incoming_end]:
            if "\t" not in raw:
                continue
            word, code = raw.split("\t", 1)
            by_word.setdefault(word, set()).add(code)
    merged: list[str] = []
    for word in sorted(by_word):
        codes = sorted(by_word[word])
        if len(codes) > 1:
            conflicts.append("\t".join(["self_word", word, *codes]))
        merged.extend(f"{word}\t{code}" for code in codes)
    output = lines[: start + 1] + merged + lines[end:]
    atomic_write(target, "\n".join(output) + "\n")


def health() -> None:
    issues: list[str] = []
    valid_chars = set("abcdefghijklmnopqrstuvwxyz;/`")
    seen: dict[tuple[str, str], tuple[str, int]] = {}
    active_words: set[tuple[str, str]] = set()
    for name in DICTIONARIES:
        path = ROOT / name
        if not path.exists():
            issues.append(f"missing\t{name}")
            continue
        for number, raw in enumerate(
            path.read_text(encoding="utf-8-sig").splitlines(), 1
        ):
            if raw.startswith("#") or "\t" not in raw:
                continue
            fields = raw.split("\t")
            word, code = fields[0], fields[1].strip()
            if not word or not code:
                issues.append(f"empty\t{name}:{number}")
                continue
            if any(char not in valid_chars for char in code):
                issues.append(f"invalid_code\t{name}:{number}\t{word}\t{code}")
            key = (word, code)
            if key in seen:
                old_name, old_number = seen[key]
                issues.append(
                    f"duplicate\t{word}\t{code}\t"
                    f"{old_name}:{old_number}\t{name}:{number}"
                )
            else:
                seen[key] = (name, number)
            active_words.add(key)

    orders = ROOT / "pantsu_candidate_order.tsv"
    if orders.exists():
        for number, raw in enumerate(orders.read_text(encoding="utf-8").splitlines(), 1):
            fields = raw.split("\t")
            if len(fields) < 3 or (fields[2], fields[0]) not in active_words:
                issues.append(f"orphan_order\t{number}\t{raw}")

    overrides = parse_overrides(ROOT / "pantsu_overrides.tsv")
    for record in overrides.values():
        path = ROOT / record[2]
        line_number = int(record[3])
        source = path.read_text(encoding="utf-8-sig").splitlines()
        if line_number > len(source):
            issues.append(f"orphan_override\t{record[1]}")
            continue
        raw = source[line_number - 1].rstrip("\r")
        if raw != f"{record[4]}\t{record[5]}":
            issues.append(f"changed_source\t{record[1]}\t{raw}")

    report = ROOT / "pantsu_health_report.tsv"
    atomic_write(report, "\n".join(issues) + ("\n" if issues else "ok\n"))
    print(f"检查完成：{len(issues)} 个问题，报告位于 {report}")


def show_history(limit: int) -> None:
    path = ROOT / "pantsu_history.tsv"
    if not path.exists():
        print("暂无操作历史")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines[-limit:]:
        print(line)


def apply_overrides() -> None:
    entries = parse_overrides(ROOT / "pantsu_overrides.tsv")
    if not entries:
        print("没有需要合并的覆盖")
        return
    backup()
    grouped: dict[str, dict[int, list[str]]] = {}
    for record in entries.values():
        grouped.setdefault(record[2], {})[int(record[3])] = record
    for name, changes in grouped.items():
        path = ROOT / name
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        output: list[str] = []
        for number, raw in enumerate(lines, 1):
            record = changes.get(number)
            if not record:
                output.append(raw)
                continue
            if raw.rstrip("\r") != f"{record[4]}\t{record[5]}":
                raise SystemExit(f"源词条已变化，停止合并：{name}:{number}")
            if record[7] == "1":
                output.append(f"{record[4]}\t{record[6]}")
        atomic_write(path, "\n".join(output) + "\n")
    write_overrides({})
    print(f"已将 {len(entries)} 条覆盖合并回基础词库")


def main() -> None:
    parser = argparse.ArgumentParser(description="胖次键道维护工具")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("backup")
    restore_parser = sub.add_parser("restore")
    restore_parser.add_argument("name")
    merge_parser = sub.add_parser("merge-sync")
    merge_parser.add_argument("directories", nargs="+")
    history_parser = sub.add_parser("history")
    history_parser.add_argument("-n", type=int, default=30)
    sub.add_parser("health")
    sub.add_parser("apply-overrides")
    sub.add_parser("sync-export")
    sub.add_parser("sync-merge")
    args = parser.parse_args()
    if args.command == "backup":
        backup()
    elif args.command == "restore":
        restore(args.name)
    elif args.command == "merge-sync":
        merge_sync(args.directories)
    elif args.command == "history":
        show_history(args.n)
    elif args.command == "health":
        health()
    elif args.command == "apply-overrides":
        apply_overrides()
    elif args.command == "sync-export":
        sync_export()
    elif args.command == "sync-merge":
        sync_merge()


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
