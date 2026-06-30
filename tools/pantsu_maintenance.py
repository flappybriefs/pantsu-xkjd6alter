#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from pantsu_maintenance_profiles import (
    SCHEME_PROFILES,
    STATE_FILES,
    active_profile,
    profiles_for_dictionary,
    selected_profiles,
)
from pantsu_dictionary import (
    full_code_for_word,
    load_char_codes,
    minimum_code_length,
    read_entries,
)

ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG = ROOT / ".pantsu_maintenance.json"
MERGE_LOG_LIMIT = 5
HISTORY_LIMIT_BYTES = 1024 * 1024
MERGE_LOG_FILES = tuple(dict.fromkeys((
    *STATE_FILES,
    "pantsu.core.dict.yaml",
    "pantsu.cizu.dict.yaml",
)))


def atomic_write(path: Path, text: str) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def ensure_runtime_directories() -> None:
    (ROOT / "build").mkdir(exist_ok=True)
    (ROOT / "build/pantsu_undo").mkdir(parents=True, exist_ok=True)


def read_build_time() -> str:
    path = ROOT / "user.yaml"
    if not path.exists():
        return ""
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = raw.strip()
        if stripped.startswith("last_build_time:"):
            return stripped.split(":", 1)[1].strip()
    return ""


def dynamic_root_for_code(code: str, *, order: bool = False) -> str | None:
    code = "" if code == "-" else code
    if len(code) < 2:
        return None
    if order:
        return code[:4] if len(code) > 4 else code[:-1]
    return code[: min(4, len(code))]


def regenerate_dynamic_roots() -> int:
    roots: set[str] = set()
    state = ROOT / "build/pantsu_dynamic_candidates.tsv"
    if state.exists():
        for raw in state.read_text(encoding="utf-8-sig").splitlines():
            fields = raw.split("\t")
            if len(fields) >= 2 and fields[0] == "root" and fields[1]:
                roots.add(fields[1])
    for record in parse_overrides(ROOT / "pantsu_overrides.tsv").values():
        if len(record) >= 8:
            for code in (record[5], record[6]):
                root = dynamic_root_for_code(code)
                if root:
                    roots.add(root)
    for record in parse_self_word_state(ROOT).values():
        if len(record) >= 4 and record[3] == "1":
            root = dynamic_root_for_code(record[2])
            if root:
                roots.add(root)
    for profile in SCHEME_PROFILES.values():
        for code, state_record in parse_candidate_orders(
            ROOT / profile.candidate_order_file
        ).items():
            if state_record.get("active", True):
                root = dynamic_root_for_code(code, order=True)
                if root:
                    roots.add(root)
    lines = [
        "format\t9",
        f"build\t{read_build_time()}",
        "signature\t",
    ]
    lines.extend(f"root\t{root}" for root in sorted(roots))
    atomic_write(ROOT / "pantsu_dynamic_roots.tsv", "\n".join(lines) + "\n")
    return len(roots)


def file_modified_ns(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def merge_log_directory() -> Path:
    return ROOT / "pantsu_maintenance_logs"


def operation_version(
    record: list[str] | dict[str, object],
    path: Path,
    *,
    updated_index: int | None = None,
    device_index: int | None = None,
) -> tuple[int, int, str]:
    if isinstance(record, dict):
        updated = int(record.get("updated", 0))
        device = str(record.get("device", "unknown"))
    else:
        updated = (
            int(record[updated_index])
            if updated_index is not None
            and len(record) > updated_index
            and record[updated_index].isdigit()
            else 0
        )
        device = (
            record[device_index]
            if device_index is not None and len(record) > device_index
            else "unknown"
        )
    return updated, file_modified_ns(path), device


def create_merge_log(action: str, directories: list[str]) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    directory = merge_log_directory()
    target = directory / stamp
    target.mkdir(parents=True, exist_ok=False)
    existing: list[str] = []
    missing: list[str] = []
    for name in MERGE_LOG_FILES:
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, target / name)
            existing.append(name)
        else:
            missing.append(name)
    manifest = {
        "version": 1,
        "action": action,
        "created_at": dt.datetime.now().astimezone().isoformat(),
        "status": "started",
        "sources": directories,
        "snapshot_files": existing,
        "missing_files": missing,
    }
    atomic_write(
        target / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    logs = sorted(
        (path for path in directory.iterdir() if path.is_dir()),
        reverse=True,
    )
    for old in logs[MERGE_LOG_LIMIT:]:
        shutil.rmtree(old)
    return target


def finish_merge_log(
    target: Path,
    *,
    status: str,
    details: dict[str, object],
) -> None:
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({
        "status": status,
        "finished_at": dt.datetime.now().astimezone().isoformat(),
        "details": details,
    })
    atomic_write(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    lines = [
        f"时间：{manifest.get('finished_at', manifest.get('created_at', '-'))}",
        f"操作：{manifest.get('action', '-')}",
        f"结果：{status}",
        "来源：",
    ]
    lines.extend(f"- {source}" for source in manifest.get("sources", []))
    lines.append("统计：")
    lines.extend(
        f"- {key}: {value}" for key, value in sorted(details.items())
    )
    conflict_path = ROOT / "pantsu_sync_conflicts.tsv"
    if conflict_path.exists():
        lines.append("竞争记录（已按最新操作自动决胜）：")
        lines.extend(
            f"- {raw}"
            for raw in conflict_path.read_text(
                encoding="utf-8-sig"
            ).splitlines()
            if raw
        )
    atomic_write(target / "操作日志.txt", "\n".join(lines) + "\n")


def merge_logs() -> list[Path]:
    directory = merge_log_directory()
    if not directory.is_dir():
        return []
    return sorted(
        (path for path in directory.iterdir() if path.is_dir()),
        reverse=True,
    )[:MERGE_LOG_LIMIT]


def restore_merge_log(name: str) -> None:
    source = merge_log_directory() / name
    manifest_path = source / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"维护日志不存在：{source}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    backup(tuple(MERGE_LOG_FILES))
    snapshot_files = set(manifest.get("snapshot_files", []))
    missing_files = set(manifest.get("missing_files", []))
    for name in MERGE_LOG_FILES:
        snapshot = source / name
        target = ROOT / name
        if name in snapshot_files and snapshot.exists():
            shutil.copy2(snapshot, target)
        elif name in missing_files:
            target.unlink(missing_ok=True)
    shared = shared_directory()
    if shared is not None:
        destinations = state_directories(shared)
        if looks_like_rime_root(shared):
            destinations.extend([
                shared,
                shared / "sync" / installation_id(),
            ])
            copy_phone_scheme(shared)
        broadcast_state(destinations)
    reload_squirrel()
    print(f"已恢复维护日志：{source.name}")
    print("电脑和手机共享目录均已回到该次合并前的状态。")


def backup(extra_files: tuple[str, ...] = ()) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = ROOT / "backups" / stamp
    target.mkdir(parents=True, exist_ok=True)
    for name in dict.fromkeys((*STATE_FILES, *extra_files)):
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, target / name)
    snapshots = sorted(
        path for path in (ROOT / "backups").glob("*")
        if path.is_dir()
    )
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
    lines = ["version\t2"]
    current = ROOT / "pantsu_overrides.tsv"
    if current.exists():
        runtime_lines = [
            raw
            for raw in current.read_text(encoding="utf-8-sig").splitlines()
            if raw.startswith("runtime\t")
        ]
        if runtime_lines:
            lines.append(runtime_lines[-1])
    lines.extend("\t".join(entries[key]) for key in sorted(entries))
    atomic_write(ROOT / "pantsu_overrides.tsv", "\n".join(lines) + "\n")


def normalize_overrides(
    entries: dict[str, list[str]],
) -> tuple[dict[str, list[str]], int]:
    allowed = set(active_profile().dictionaries)
    files: dict[str, list[str]] = {}
    result = {}
    dropped = 0
    for key, record in entries.items():
        name = record[2]
        if name not in allowed or not record[3].isdigit():
            dropped += 1
            continue
        lines = files.get(name)
        if lines is None:
            path = ROOT / name
            if not path.exists():
                dropped += 1
                continue
            lines = path.read_text(encoding="utf-8-sig").splitlines()
            files[name] = lines
        number = int(record[3])
        if number < 1 or number > len(lines):
            dropped += 1
            continue
        fields = lines[number - 1].rstrip("\r").split("\t")
        if len(fields) < 2 or fields[0] != record[4] or fields[1] != record[5]:
            dropped += 1
            continue
        result[key] = record
    return result, dropped


def parse_self_word_records(path: Path) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    if not path.exists():
        return result
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        fields = raw.split("\t")
        if fields and fields[0] == "word" and len(fields) >= 6:
            result[f"{fields[1]}\t{fields[2]}"] = fields
    return result


def parse_self_word_state(directory: Path) -> dict[str, list[str]]:
    result = parse_self_word_records(directory / "pantsu_self_words.tsv")
    for key, record in parse_self_word_records(
        directory / "pantsu_self_words_ops.tsv"
    ).items():
        current = result.get(key)
        if current is None or operation_version(
            record,
            directory / "pantsu_self_words_ops.tsv",
            updated_index=4,
            device_index=5,
        ) >= operation_version(
            current,
            directory / "pantsu_self_words.tsv",
            updated_index=4,
            device_index=5,
        ):
            result[key] = record
    return result


def write_self_word_records(entries: dict[str, list[str]]) -> None:
    lines = ["version\t1"]
    lines.extend("\t".join(entries[key]) for key in sorted(entries))
    atomic_write(ROOT / "pantsu_self_words.tsv", "\n".join(lines) + "\n")
    atomic_write(ROOT / "pantsu_self_words_ops.tsv", "version\t1\n")


def parse_usage(directory: Path) -> dict[tuple[str, str], tuple[int, int]]:
    result: dict[tuple[str, str], tuple[int, int]] = {}
    for name, kind in [
        ("pantsu_usage.tsv", "word"),
        ("pantsu_usage_events.tsv", "event"),
    ]:
        path = directory / name
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            fields = raw.split("\t")
            if (
                len(fields) != 5
                or fields[0] not in {kind, "delta"}
                or (fields[0] == "delta" and kind != "event")
                or not fields[3].isdigit()
                or not fields[4].isdigit()
            ):
                continue
            key = (fields[1], fields[2])
            incoming = (int(fields[3]), int(fields[4]))
            current = result.get(key)
            if fields[0] == "delta":
                old_count, old_updated = current or (0, 0)
                result[key] = (
                    old_count + incoming[0],
                    max(old_updated, incoming[1]),
                )
            elif current is None or incoming > current:
                result[key] = incoming
    return result


def write_usage(entries: dict[tuple[str, str], tuple[int, int]]) -> None:
    lines = ["version\t1"]
    for (word, device), (count, updated) in sorted(entries.items()):
        lines.append(
            "\t".join([
                "word",
                word,
                device,
                str(count),
                str(updated),
            ])
        )
    atomic_write(ROOT / "pantsu_usage.tsv", "\n".join(lines) + "\n")
    atomic_write(ROOT / "pantsu_usage_events.tsv", "version\t1\n")


def parse_history(path: Path) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    if not path.exists():
        return result
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        fields = raw.split("\t")
        if len(fields) >= 6 and fields[0].isdigit():
            result[raw] = fields
    return result


def write_history(entries: dict[str, list[str]]) -> None:
    rows = sorted(
        entries,
        key=lambda raw: (
            int(entries[raw][0]),
            entries[raw][1],
            raw,
        ),
    )
    total = sum(len((raw + "\n").encode("utf-8")) for raw in rows)
    while rows and total > HISTORY_LIMIT_BYTES:
        total -= len((rows[0] + "\n").encode("utf-8"))
        rows.pop(0)
    atomic_write(
        ROOT / "pantsu_history.tsv",
        "".join(raw + "\n" for raw in rows),
    )


def parse_candidate_orders(path: Path) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    if not path.exists():
        return result
    legacy_time = path.stat().st_mtime_ns // 1_000_000_000
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        fields = raw.split("\t")
        if len(fields) >= 5 and fields[0] == "meta":
            updated = int(fields[2]) if fields[2].isdigit() else 0
            result[fields[1]] = {
                "updated": updated or legacy_time,
                "device": fields[3],
                "active": fields[4] == "1",
                "items": [],
            }
        elif len(fields) >= 4 and fields[0] == "item" and fields[2].isdigit():
            state = result.setdefault(fields[1], {
                "updated": legacy_time,
                "device": "legacy",
                "active": True,
                "items": [],
            })
            state["items"].append([fields[2], fields[3]])
        elif len(fields) >= 3 and fields[1].isdigit():
            state = result.setdefault(fields[0], {
                "updated": legacy_time,
                "device": "legacy",
                "active": True,
                "items": [],
            })
            state["items"].append([fields[1], fields[2]])
    for state in result.values():
        state["items"].sort(key=lambda item: (int(item[0]), item[1]))
    return result


def write_candidate_orders(
    entries: dict[str, dict[str, object]],
    path: Path | None = None,
) -> None:
    lines: list[str] = ["version\t2"]
    for code in sorted(entries):
        state = entries[code]
        lines.append("\t".join([
            "meta",
            code,
            str(state["updated"]),
            str(state["device"]),
            "1" if state["active"] else "0",
        ]))
        if state["active"]:
            lines.extend(
                "\t".join(["item", code, *record])
                for record in state["items"]
            )
    atomic_write(
        path or ROOT / "pantsu_candidate_order.tsv",
        "\n".join(lines) + "\n",
    )


def merge_sync(
    directories: list[str],
    *,
    create_backup: bool = True,
    write_back: bool = True,
    create_log: bool = True,
) -> dict[str, object]:
    directories = list(dict.fromkeys(
        str(Path(directory).resolve()) for directory in directories
    ))
    log = create_merge_log("merge-sync", directories) if create_log else None
    if create_backup:
        backup()
    try:
        conflicts: list[str] = []
        state_roots = [ROOT, *(Path(directory) for directory in directories)]

        merged: dict[str, list[str]] = {}
        override_versions: dict[str, tuple[int, int, str]] = {}
        for directory in state_roots:
            path = directory / "pantsu_overrides.tsv"
            for key, record in parse_overrides(path).items():
                version = operation_version(
                    record,
                    path,
                    updated_index=8,
                    device_index=9,
                )
                current = merged.get(key)
                current_version = override_versions.get(key)
                if current is not None and current != record:
                    winner = "incoming" if version > current_version else "current"
                    conflicts.append("\t".join([
                        "override",
                        key,
                        winner,
                        str(current_version),
                        str(version),
                    ]))
                if current is None or version > current_version:
                    merged[key] = record
                    override_versions[key] = version
        merged, dropped_overrides = normalize_overrides(merged)
        write_overrides(merged)

        for profile in SCHEME_PROFILES.values():
            order_sources = [
                directory / profile.candidate_order_file
                for directory in state_roots
            ]
            order_sources = [path for path in order_sources if path.exists()]
            merged_orders: dict[str, dict[str, object]] = {}
            order_versions: dict[str, tuple[int, int, str]] = {}
            for path in order_sources:
                for code, state in parse_candidate_orders(path).items():
                    version = operation_version(state, path)
                    current = merged_orders.get(code)
                    current_version = order_versions.get(code)
                    if current is not None and current != state:
                        winner = (
                            "incoming" if version > current_version else "current"
                        )
                        conflicts.append("\t".join([
                            "candidate_order",
                            profile.key,
                            code,
                            winner,
                            str(current_version),
                            str(version),
                        ]))
                    if current is None or version > current_version:
                        merged_orders[code] = state
                        order_versions[code] = version
            if order_sources:
                write_candidate_orders(
                    merged_orders,
                    ROOT / profile.candidate_order_file,
                )

        self_words: dict[str, list[str]] = {}
        self_versions: dict[str, tuple[int, int, str]] = {}
        for directory in state_roots:
            snapshot_path = directory / "pantsu_self_words.tsv"
            ops_path = directory / "pantsu_self_words_ops.tsv"
            ops_keys = set(parse_self_word_records(ops_path))
            for key, record in parse_self_word_state(directory).items():
                source_path = (
                    ops_path
                    if key in ops_keys
                    else snapshot_path
                )
                version = operation_version(
                    record,
                    source_path,
                    updated_index=4,
                    device_index=5,
                )
                current = self_words.get(key)
                current_version = self_versions.get(key)
                if current is not None and current != record:
                    winner = "incoming" if version > current_version else "current"
                    conflicts.append("\t".join([
                        "self_word",
                        key,
                        winner,
                        str(current_version),
                        str(version),
                    ]))
                if current is None or version > current_version:
                    self_words[key] = record
                    self_versions[key] = version
        write_self_word_records(self_words)

        usage = parse_usage(ROOT)
        for directory in directories:
            for key, incoming in parse_usage(Path(directory)).items():
                current = usage.get(key)
                if current is None or incoming > current:
                    usage[key] = incoming
        write_usage(usage)

        history: dict[str, list[str]] = {}
        for directory in state_roots:
            history.update(parse_history(directory / "pantsu_history.tsv"))
        write_history(history)
        ensure_runtime_directories()
        dynamic_roots = regenerate_dynamic_roots()
        if conflicts:
            atomic_write(
                ROOT / "pantsu_sync_conflicts.tsv",
                "\n".join(conflicts) + "\n",
            )
        else:
            (ROOT / "pantsu_sync_conflicts.tsv").unlink(missing_ok=True)
        if write_back:
            broadcast_state([Path(directory) for directory in directories])
        result: dict[str, object] = {
            "overrides": len(merged),
            "self_words": len(self_words),
            "usage_words": len({word for word, _ in usage}),
            "history_rows": len(history),
            "history_devices": len({
                fields[1] for fields in history.values()
            }),
            "conflicts": len(conflicts),
            "dropped_overrides": dropped_overrides,
            "dynamic_roots": dynamic_roots,
            "write_back_directories": len(directories) if write_back else 0,
        }
        print(
            f"合并完成：{result['overrides']} 条覆盖，"
            f"{result['self_words']} 个自造词状态，"
            f"{result['usage_words']} 个词频，"
            f"{result['history_rows']} 条操作历史，"
            f"{result['conflicts']} 条竞争记录，"
            f"清理 {result['dropped_overrides']} 条旧方案覆盖"
        )
        if write_back:
            print(f"已将合并状态双向写回 {len(directories)} 个设备目录")
        if log is not None:
            finish_merge_log(log, status="success", details=result)
            print(f"维护日志：{log.name}")
        return result
    except Exception as exc:
        if log is not None:
            finish_merge_log(
                log,
                status="failed",
                details={"error": f"{type(exc).__name__}: {exc}"},
            )
        raise


def installation_id() -> str:
    path = ROOT / "installation.yaml"
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("installation_id:"):
            return raw.split(":", 1)[1].strip().strip("\"'")
    return "unknown"


def copy_state(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name in STATE_FILES:
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, target / name)


def broadcast_state(directories: list[Path]) -> int:
    copied = 0
    seen: set[Path] = set()
    for directory in directories:
        resolved = directory.resolve()
        if resolved == ROOT.resolve() or resolved in seen:
            continue
        seen.add(resolved)
        copy_state(directory)
        copied += 1
    return copied


def copy_phone_scheme(target: Path) -> tuple[int, int]:
    if not looks_like_rime_root(target):
        return 0, 0
    profile = active_profile()
    obsolete = [
        target / name
        for name in profile.obsolete_phone_files
        if (target / name).exists()
    ]
    backup_target = None
    if obsolete:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_target = ROOT / "backups" / f"{stamp}-phone-scheme"
        backup_target.mkdir(parents=True, exist_ok=True)
        for path in obsolete:
            shutil.copy2(path, backup_target / path.name)
    copied = 0
    for name in profile.phone_files:
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, target / name)
            copied += 1
    source_lua = ROOT / "lua"
    target_lua = target / "lua"
    if source_lua.is_dir():
        shutil.copytree(source_lua, target_lua, dirs_exist_ok=True)
        copied += sum(path.is_file() for path in source_lua.iterdir())
    for path in obsolete:
        path.unlink()
    for directory in state_directories(target):
        stale = directory / "pantsu_refined_candidate_order.tsv"
        stale.unlink(missing_ok=True)
    return copied, len(obsolete)


def reconcile_dictionary_self_codes(
    path: Path,
    fixed_names: tuple[str, ...],
    editable_end: int | None = None,
) -> tuple[int, int]:
    journal = ROOT / "pantsu_self_words.tsv"
    if not path.exists() or not journal.exists():
        return 0, 0
    self_by_code: dict[str, set[str]] = {}
    for raw in journal.read_text(encoding="utf-8-sig").splitlines():
        fields = raw.split("\t")
        if len(fields) >= 6 and fields[0] == "word" and fields[3] == "1":
            self_by_code.setdefault(fields[2], set()).add(fields[1])
    self_codes = set(self_by_code)
    if not self_codes:
        return 0, 0

    lines = path.read_text(encoding="utf-8-sig").splitlines()
    entries = []
    for index, raw in enumerate(lines):
        if (
            (editable_end is not None and index >= editable_end)
            or raw.startswith("#")
            or "\t" not in raw
        ):
            continue
        fields = raw.split("\t")
        entries.append({
            "line": index,
            "word": fields[0],
            "code": fields[1],
            "fields": fields,
        })
    fixed_codes = set(self_codes)
    if editable_end is not None:
        fixed_codes.update(
            code for number, _, code in read_entries(path)
            if number > editable_end
        )
    for name in fixed_names:
        fixed_codes.update(
            code for _, _, code in read_entries(ROOT / name)
        )
    by_code: dict[str, list[dict[str, object]]] = {}
    for entry in entries:
        by_code.setdefault(str(entry["code"]), []).append(entry)
    primary, options = load_char_codes(ROOT)
    moved = 0
    removed = 0

    def relocate(entry, visiting: set[int]) -> bool:
        nonlocal moved, removed
        identity = int(entry["line"])
        if identity in visiting:
            return False
        visiting.add(identity)
        old_code = str(entry["code"])
        full = full_code_for_word(
            str(entry["word"]),
            {old_code},
            primary,
            options,
        )
        if full:
            for length in range(
                max(minimum_code_length(str(entry["word"])), len(old_code) + 1),
                len(full) + 1,
            ):
                target = full[:length]
                if target in fixed_codes:
                    continue
                blockers = [
                    item for item in by_code.get(target, [])
                    if item is not entry
                ]
                if len(target) < 6 and blockers:
                    if not all(relocate(item, visiting.copy()) for item in blockers):
                        continue
                    blockers = [
                        item for item in by_code.get(target, [])
                        if item is not entry
                    ]
                if len(target) < 6 and blockers:
                    continue
                by_code[old_code].remove(entry)
                by_code.setdefault(target, []).append(entry)
                entry["code"] = target
                fields = list(entry["fields"])
                fields[1] = target
                lines[identity] = "\t".join(fields)
                moved += 1
                return True
        by_code[old_code].remove(entry)
        lines[identity] = ""
        removed += 1
        return True

    conflicts = [
        entry for entry in entries
        if str(entry["code"]) in self_codes
    ]
    for entry in conflicts:
        if str(entry["word"]) in self_by_code[str(entry["code"])]:
            by_code[str(entry["code"])].remove(entry)
            lines[int(entry["line"])] = ""
            removed += 1
        else:
            relocate(entry, set())
    if moved or removed:
        atomic_write(
            path,
            "\n".join(line for line in lines if line != "") + "\n",
        )
    return moved, removed


def reconcile_core_self_codes() -> tuple[int, int]:
    core = ROOT / "pantsu.core.dict.yaml"
    lines = core.read_text(encoding="utf-8-sig").splitlines()
    start = (
        lines.index("#region <630>#")
        if "#region <630>#" in lines
        else None
    )
    moved_core, removed_core = reconcile_dictionary_self_codes(
        core,
        (
            "pantsu.danzi.dict.yaml",
            "pantsu.cizu.dict.yaml",
            "pantsu.user.dict.yaml",
            "pantsu.zzc.dict.yaml",
        ),
        start,
    )
    moved_cizu, removed_cizu = reconcile_dictionary_self_codes(
        ROOT / "pantsu.cizu.dict.yaml",
        (
            "pantsu.core.dict.yaml",
            "pantsu.danzi.dict.yaml",
            "pantsu.user.dict.yaml",
            "pantsu.zzc.dict.yaml",
        ),
    )
    return moved_core + moved_cizu, removed_core + removed_cizu


def sync_export(destination: Path | None = None) -> Path:
    write_usage(parse_usage(ROOT))
    target = (destination or ROOT / "sync") / installation_id()
    copy_state(target)
    print(f"已导出同步状态到 {target}")
    return target


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


def load_local_config() -> dict[str, str]:
    if not LOCAL_CONFIG.exists():
        return {}
    try:
        value = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def save_shared_directory(path: Path) -> None:
    atomic_write(
        LOCAL_CONFIG,
        json.dumps(
            {"shared_directory": str(path.expanduser().resolve())},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
    )


def looks_like_rime_root(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "installation.yaml").exists()
        and (
            (path / "hamster.yaml").exists()
            or (path / "pantsu.schema.yaml").exists()
            or (path / "pantsu_self_words.tsv").exists()
        )
    )


def automatic_shared_directories() -> list[Path]:
    home = Path.home()
    candidates = [
        home
        / "Library/Mobile Documents/"
        / "iCloud~dev~fuxiao~app~hamsterapp/Documents/RIME/Rime",
        home
        / "Library/Mobile Documents/"
        / "iCloud~com~ihsiao~apps~Hamster3/Documents/RimeUserData",
        home / "Library/Mobile Documents/com~apple~CloudDocs/rimesync",
    ]
    return [path for path in candidates if path.is_dir()]


def shared_directory(explicit: str | None = None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_dir() else None
    environment = os.environ.get("PANTSU_SYNC_DIR")
    if environment:
        path = Path(environment).expanduser()
        if path.is_dir():
            return path
    configured = load_local_config().get("shared_directory")
    if configured:
        path = Path(configured).expanduser()
        if path.is_dir():
            return path
    candidates = automatic_shared_directories()
    for path in candidates:
        if looks_like_rime_root(path):
            return path
    return candidates[0] if candidates else None


def state_directories(path: Path) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()

    def add(candidate: Path) -> None:
        resolved = candidate.resolve()
        if resolved == ROOT.resolve() or resolved in seen:
            return
        if any((candidate / name).exists() for name in STATE_FILES):
            seen.add(resolved)
            result.append(candidate)

    add(path)
    sync = path / "sync"
    if sync.is_dir():
        for child in sorted(sync.iterdir()):
            if child.is_dir() and child.name != installation_id():
                add(child)
    if not looks_like_rime_root(path):
        for child in sorted(path.iterdir()):
            if child.is_dir() and child.name != installation_id():
                add(child)
    return result


def reload_squirrel() -> bool:
    executable = Path(
        "/Library/Input Methods/Squirrel.app/Contents/MacOS/Squirrel"
    )
    if not executable.exists():
        return False
    result = subprocess.run(
        [str(executable), "--reload"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def sync_phone(
    directory: str | None = None,
    *,
    reload_desktop: bool = True,
) -> bool:
    target = shared_directory(directory)
    if target is None:
        print("没有找到仓输入法的 iCloud 目录")
        print("请在“更多功能”中设置一次手机目录")
        return False
    sources = state_directories(target)
    if not sources:
        print("手机还没有把状态写入 iCloud。")
        print("只需在仓输入法中执行一次“同步/重新部署”，然后重试。")
        return False

    print("正在读取手机状态并与电脑合并……")
    log = create_merge_log(
        "sync-phone",
        [str(path.resolve()) for path in sources],
    )
    backup(("pantsu.core.dict.yaml", "pantsu.cizu.dict.yaml"))
    try:
        result = merge_sync(
            [str(path) for path in sources],
            create_backup=False,
            write_back=False,
            create_log=False,
        )
        moved, removed_core = reconcile_core_self_codes()
        local_export = sync_export()

        destinations = [*sources, local_export]
        if looks_like_rime_root(target):
            destinations.extend([
                target,
                target / "sync" / installation_id(),
            ])
            copied, removed = copy_phone_scheme(target)
        else:
            destinations.append(target / installation_id())
            copied, removed = 0, 0
        written = broadcast_state(destinations)

        reloaded = reload_squirrel() if reload_desktop else False
        details = {
            **result,
            "self_code_moves": moved,
            "self_code_removals": removed_core,
            "write_back_directories": written,
            "scheme_files_copied": copied,
            "obsolete_files_removed": removed,
        }
        finish_merge_log(log, status="success", details=details)
        print(f"同步完成：已合并 {len(sources)} 份手机状态")
        print(f"双向写回：{written} 个电脑、iCloud 和手机设备目录")
        if moved or removed_core:
            print(
                f"自造词避码：后移 {moved} 个基础词，"
                f"移除 {removed_core} 个无法后移的低优先词。"
            )
        print("电脑和所有参与合并的手机状态目录现在使用同一份结果。")
        if copied:
            print(
                f"手机方案已更新：复制 {copied} 个文件，"
                f"清理 {removed} 个旧文件。"
            )
        if reload_desktop:
            print(
                "电脑输入法已重新加载"
                if reloaded
                else "未检测到鼠须管，已跳过重载"
            )
        print(f"维护日志：{log.name}（仅保留最近 {MERGE_LOG_LIMIT} 次）")
        print("手机上传新操作：保持“重新部署时覆盖词库文件”关闭后同步。")
        print("手机接收合并结果：临时开启该选项并重新部署，完成后再关闭。")
        return True
    except Exception as exc:
        finish_merge_log(
            log,
            status="failed",
            details={"error": f"{type(exc).__name__}: {exc}"},
        )
        raise


def choose_shared_directory() -> Path | None:
    current = shared_directory()
    print(f"当前目录：{current or '未设置'}")
    print("直接回车使用自动识别结果，或粘贴仓输入法/iCloud目录路径。")
    value = input("同步目录：").strip()
    path = Path(value).expanduser() if value else current
    if path is None or not path.is_dir():
        print("目录不存在，设置未保存")
        return None
    save_shared_directory(path)
    print(f"已保存：{path.resolve()}")
    return path


def pause() -> None:
    input("\n按回车键返回菜单……")


def restore_interactive() -> None:
    directory = ROOT / "backups"
    snapshots = sorted(
        [path for path in directory.glob("*") if path.is_dir()],
        reverse=True,
    )
    if not snapshots:
        print("目前没有备份")
        return
    for index, path in enumerate(snapshots[:10], 1):
        print(f"{index}. {path.name}")
    value = input("输入要恢复的序号，直接回车取消：").strip()
    if not value.isdigit() or not 1 <= int(value) <= min(10, len(snapshots)):
        print("已取消")
        return
    restore(snapshots[int(value) - 1].name)


def show_merge_logs() -> list[Path]:
    logs = merge_logs()
    if not logs:
        print("目前没有维护合并日志")
        return []
    for index, path in enumerate(logs, 1):
        try:
            manifest = json.loads(
                (path / "manifest.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            manifest = {}
        details = manifest.get("details", {})
        status = "成功" if manifest.get("status") == "success" else "未完成"
        action = (
            "手机与电脑合并"
            if manifest.get("action") == "sync-phone"
            else "状态合并"
        )
        conflicts = details.get("conflicts", 0)
        print(
            f"{index}. {path.name}  {action}  {status}  "
            f"竞争记录 {conflicts}"
        )
    return logs


def restore_merge_log_interactive() -> None:
    logs = show_merge_logs()
    if not logs:
        return
    value = input("输入要恢复的日志序号，直接回车取消：").strip()
    if not value.isdigit() or not 1 <= int(value) <= len(logs):
        print("已取消")
        return
    selected = logs[int(value) - 1]
    confirm = input(
        f"将恢复到 {selected.name} 合并前，输入 YES 确认："
    ).strip()
    if confirm != "YES":
        print("已取消")
        return
    restore_merge_log(selected.name)


def advanced_menu() -> None:
    while True:
        print("\n—— 更多功能 ——")
        print("1. 查看操作历史")
        print("2. 查看性能记录")
        print("3. 运行性能与极端压力测试")
        print("4. 对比自造词写入性能")
        print("5. 设置手机目录")
        print("6. 应用覆盖到基础词库")
        print("7. 修复失效覆盖记录")
        print("8. 恢复历史备份")
        print("9. 从维护合并日志恢复")
        print("0. 返回")
        choice = input("请选择：").strip()
        if choice == "1":
            show_history(30)
        elif choice == "2":
            show_performance(20)
        elif choice == "3":
            run_stress_test()
        elif choice == "4":
            run_self_word_benchmark()
        elif choice == "5":
            choose_shared_directory()
        elif choice == "6":
            apply_overrides()
        elif choice == "7":
            repair_overrides()
        elif choice == "8":
            restore_interactive()
        elif choice == "9":
            restore_merge_log_interactive()
        elif choice == "0":
            return
        else:
            print("请输入菜单中的数字")
        pause()


def interactive() -> None:
    while True:
        target = shared_directory()
        print("\n==============================")
        print("       胖次键道维护工具")
        print("==============================")
        print(f"电脑设备：{installation_id()}")
        print(f"手机目录：{target or '尚未识别'}")
        print("\n回车. 合并手机与电脑（推荐）")
        print("2. 检查方案健康")
        print("3. 备份当前状态")
        print("4. 更多功能")
        print("0. 退出")
        choice = input("请选择，直接回车开始同步：").strip()
        if choice in {"", "1"}:
            sync_phone()
        elif choice == "2":
            health()
        elif choice == "3":
            backup()
        elif choice == "4":
            advanced_menu()
        elif choice == "0":
            return
        else:
            print("请输入菜单中的数字")
        pause()


def migrate_candidate_orders() -> None:
    backup()
    local_id = installation_id()
    total = 0
    for profile in SCHEME_PROFILES.values():
        path = ROOT / profile.candidate_order_file
        if not path.exists():
            continue
        states = parse_candidate_orders(path)
        for state in states.values():
            if state["device"] == "legacy":
                state["device"] = local_id
        write_candidate_orders(states, path)
        total += len(states)
    print(f"已迁移 {total} 个同码排序状态")


def show_performance(limit: int) -> None:
    path = ROOT / "pantsu_performance.tsv"
    if not path.exists():
        print("尚无性能记录；先执行一次自造词、前移、后移或删除")
        return
    rows = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        fields = raw.split("\t")
        if len(fields) >= 9 and fields[0].isdigit():
            rows.append(fields)
    labels = {
        "promote": "前移",
        "demote": "后移",
        "delete": "删除",
        "make_word_preview": "造词预览",
        "make_word_save": "造词保存",
    }
    for fields in rows[-limit:]:
        stamp = dt.datetime.fromtimestamp(int(fields[0])).strftime(
            "%m-%d %H:%M:%S"
        )
        action = labels.get(fields[2], fields[2])
        print(
            f"{stamp}  {action:<8} {fields[4]:<12} "
            f"{fields[6]:>9} ms  {fields[5]}"
        )
        print(f"  {fields[7]}")


def run_stress_test() -> None:
    script = ROOT / "tools/pantsu_performance.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        print(f"压力测试未完成，退出码：{result.returncode}")


def run_self_word_benchmark() -> None:
    script = ROOT / "tools/pantsu_self_word_benchmark.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        print(f"自造词性能测试未完成，退出码：{result.returncode}")


def self_word_lines(path: Path) -> tuple[list[str], int, int]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    start = lines.index("#region <自造词>#")
    end = lines.index("#endregion <自造词>#")
    return lines, start, end


def merge_self_words(directories: list[str], conflicts: list[str]) -> None:
    target = ROOT / "pantsu.zzc.dict.yaml"
    lines, start, end = self_word_lines(target)
    by_word: dict[str, set[str]] = {}
    for raw in lines[start + 1 : end]:
        if "\t" in raw:
            word, code = raw.split("\t", 1)
            by_word.setdefault(word, set()).add(code)
    for directory in directories:
        source = Path(directory) / "pantsu.zzc.dict.yaml"
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


def health(scheme: str = "all") -> list[list[str]]:
    issues: list[list[str]] = []
    valid_chars = set("abcdefghijklmnopqrstuvwxyz;/`")
    profiles = selected_profiles(scheme)
    entries_by_file: dict[str, list[dict[str, object]]] = {}
    user_lines, user_start, user_end = self_word_lines(
        ROOT / "pantsu.zzc.dict.yaml"
    )

    def add_issue(
        level: str,
        kind: str,
        profile: str,
        location: str,
        word: str,
        code: str,
        reason: str,
        suggestion: str,
    ) -> None:
        issues.append([
            level,
            kind,
            profile,
            location,
            word,
            code,
            reason,
            suggestion,
        ])

    def is_self_word(name: str, number: int) -> bool:
        return (
            name == "pantsu.zzc.dict.yaml"
            and user_start + 2 <= number <= user_end
        )

    dictionary_names = tuple(dict.fromkeys(
        name for profile in profiles for name in profile.dictionaries
    ))
    for name in dictionary_names:
        path = ROOT / name
        file_profiles = "、".join(
            profile.label
            for profile in profiles
            if name in profile.dictionaries
        )
        if not path.exists():
            add_issue(
                "错误",
                "词库文件缺失",
                file_profiles,
                name,
                "",
                "",
                "方案引用的词库文件不存在",
                "恢复该文件后重新部署",
            )
            continue
        file_entries: list[dict[str, object]] = []
        for number, raw in enumerate(
            path.read_text(encoding="utf-8-sig").splitlines(), 1
        ):
            if raw.startswith("#") or "\t" not in raw:
                continue
            fields = raw.split("\t")
            word, code = fields[0], fields[1].strip()
            location = f"{name}:{number}"
            if not word or not code:
                add_issue(
                    "错误",
                    "空词条",
                    file_profiles,
                    location,
                    word,
                    code,
                    "词汇或编码为空",
                    "补全该行或删除无效行",
                )
                continue
            if any(char not in valid_chars for char in code):
                add_issue(
                    "错误",
                    "非法编码",
                    file_profiles,
                    location,
                    word,
                    code,
                    "编码包含方案不支持的字符",
                    "修改为合法的键道编码",
                )
            file_entries.append({
                "path": name,
                "line": number,
                "word": word,
                "code": code,
                "raw": raw,
            })
        entries_by_file[name] = file_entries

    for profile in profiles:
        seen: dict[tuple[str, str], tuple[str, int, str]] = {}
        for name in profile.dictionaries:
            for entry in entries_by_file.get(name, []):
                word = str(entry["word"])
                code = str(entry["code"])
                raw = str(entry["raw"])
                number = int(entry["line"])
                key = (word, code)
                if key in seen:
                    old_name, old_number, old_raw = seen[key]
                    expected_self_override = (
                        is_self_word(old_name, old_number)
                        or is_self_word(name, number)
                    )
                    if raw == old_raw and not expected_self_override:
                        add_issue(
                            "警告",
                            "重复词条",
                            profile.label,
                            f"{old_name}:{old_number}；{name}:{number}",
                            word,
                            code,
                            "该方案的两个基础词库中存在完全相同的词条",
                            "确认是否需要保留两份",
                        )
                else:
                    seen[key] = (name, number, raw)

    overrides = parse_overrides(ROOT / "pantsu_overrides.tsv")
    valid_overrides: dict[tuple[str, int], list[str]] = {}
    selected_keys = {profile.key for profile in profiles}
    for record in overrides.values():
        owners = profiles_for_dictionary(record[2])
        if not owners:
            if scheme == "all":
                add_issue(
                    "错误",
                    "覆盖来源未配置",
                    "公共状态",
                    record[2],
                    record[4],
                    record[6],
                    "覆盖记录指向的文件不属于任何已配置方案",
                    "修正方案配置或清理该覆盖记录",
                )
            continue
        owners = tuple(
            owner for owner in owners if owner.key in selected_keys
        )
        if not owners:
            continue
        owner_label = "、".join(owner.label for owner in owners)
        path = ROOT / record[2]
        location = f"{record[2]}:{record[3]}"
        try:
            line_number = int(record[3])
        except ValueError:
            add_issue(
                "错误",
                "覆盖记录损坏",
                owner_label,
                location,
                record[4],
                record[6],
                "覆盖记录中的行号不是数字",
                "运行高级维护中的“修复失效覆盖记录”",
            )
            continue
        if not path.exists():
            add_issue(
                "错误",
                "覆盖来源缺失",
                owner_label,
                location,
                record[4],
                record[6],
                "覆盖记录指向的基础词库不存在",
                "恢复词库或清理该覆盖记录",
            )
            continue
        source = path.read_text(encoding="utf-8-sig").splitlines()
        if line_number < 1 or line_number > len(source):
            add_issue(
                "错误",
                "覆盖位置失效",
                owner_label,
                location,
                record[4],
                record[6],
                "基础词库行号已经超出文件范围",
                "运行高级维护中的“修复失效覆盖记录”",
            )
            continue
        fields = source[line_number - 1].rstrip("\r").split("\t")
        if len(fields) < 2 or fields[0] != record[4] or fields[1] != record[5]:
            actual = "\t".join(fields[:2])
            add_issue(
                "错误",
                "覆盖来源已变化",
                owner_label,
                location,
                record[4],
                record[6],
                f"原记录是“{record[4]} {record[5]}”，"
                f"当前位置现在是“{actual}”",
                "运行高级维护中的“修复失效覆盖记录”",
            )
            continue
        valid_overrides[(record[2], line_number)] = record

    active_words_by_profile: dict[str, set[tuple[str, str]]] = {}
    for profile in profiles:
        active_words: set[tuple[str, str]] = set()
        for name in profile.dictionaries:
            for entry in entries_by_file.get(name, []):
                word = str(entry["word"])
                code = str(entry["code"])
                override = valid_overrides.get(
                    (name, int(entry["line"]))
                )
                if override:
                    if override[7] != "1":
                        continue
                    word = override[4]
                    code = override[6]
                active_words.add((word, code))
        active_words_by_profile[profile.key] = active_words

    for profile in profiles:
        orders = ROOT / profile.candidate_order_file
        if not orders.exists():
            continue
        for code, state in parse_candidate_orders(orders).items():
            if not state["active"]:
                continue
            for _, word in state["items"]:
                if (word, code) not in active_words_by_profile[profile.key]:
                    add_issue(
                        "警告",
                        "候选顺序失效",
                        profile.label,
                        profile.candidate_order_file,
                        word,
                        code,
                        "该方案的生效词库中找不到这个词与编码的组合",
                        "确认词条已删除后，可清理该候选顺序记录",
                    )

    report = ROOT / "pantsu_health_report.tsv"
    rows = [[
        "级别", "类型", "方案", "位置", "词汇", "编码", "原因", "建议"
    ]]
    if issues:
        rows.extend(issues)
    else:
        rows.append([
            "正常",
            "检查通过",
            "、".join(profile.label for profile in profiles),
            "",
            "",
            "",
            "所选方案的生效词库、覆盖层和候选顺序一致",
            "无需处理",
        ])
    atomic_write(
        report,
        "\n".join("\t".join(row) for row in rows) + "\n",
    )
    errors = sum(issue[0] == "错误" for issue in issues)
    warnings = sum(issue[0] == "警告" for issue in issues)
    print(
        f"检查完成：{errors} 个错误，{warnings} 个警告；"
        f"报告位于 {report}"
    )
    if issues:
        print("报告已列出每项问题的原因和处理建议")
    else:
        print("当前方案状态正常，无需处理")
    return issues


def show_history(limit: int) -> None:
    path = ROOT / "pantsu_history.tsv"
    if not path.exists():
        print("暂无操作历史")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines[-limit:]:
        print(line)


def apply_overrides(scheme: str = "all") -> None:
    entries = parse_overrides(ROOT / "pantsu_overrides.tsv")
    allowed = {
        name
        for profile in selected_profiles(scheme)
        for name in profile.dictionaries
    }
    selected = {
        key: record
        for key, record in entries.items()
        if record[2] in allowed
    }
    if not selected:
        print("没有需要合并的覆盖")
        return
    changed_files = tuple(sorted({record[2] for record in selected.values()}))
    backup(changed_files)
    grouped: dict[str, dict[int, tuple[str, list[str]]]] = {}
    unresolved: list[list[str]] = []
    for key, record in selected.items():
        if not record[3].isdigit():
            unresolved.append([key, record[2], record[3], "行号不是数字"])
            continue
        grouped.setdefault(record[2], {})[int(record[3])] = (key, record)
    applied: set[str] = set()
    for name, changes in grouped.items():
        path = ROOT / name
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        output: list[str] = []
        for number, raw in enumerate(lines, 1):
            item = changes.get(number)
            if not item:
                output.append(raw)
                continue
            key, record = item
            fields = raw.rstrip("\r").split("\t")
            if len(fields) < 2 or fields[0] != record[4] or fields[1] != record[5]:
                output.append(raw)
                unresolved.append([
                    key,
                    name,
                    str(number),
                    record[4],
                    record[5],
                    raw.rstrip("\r"),
                ])
                continue
            applied.add(key)
            if record[7] == "1":
                output.append("\t".join([record[4], record[6], *fields[2:]]))
        atomic_write(path, "\n".join(output) + "\n")
    remaining = {
        key: record for key, record in entries.items() if key not in applied
    }
    write_overrides(remaining)
    unresolved_path = ROOT / "pantsu_apply_overrides_unresolved.tsv"
    if unresolved:
        atomic_write(
            unresolved_path,
            "\n".join("\t".join(row) for row in unresolved) + "\n",
        )
    else:
        unresolved_path.unlink(missing_ok=True)
    labels = "、".join(profile.label for profile in selected_profiles(scheme))
    print(f"已将 {len(applied)} 条覆盖合并回{labels}基础词库")
    if unresolved:
        print(
            f"{len(unresolved)} 条覆盖因源词条变化暂未合并；"
            f"已写入 {unresolved_path.name}"
        )
        print("可先运行“修复失效覆盖记录”，再重新应用覆盖。")


def repair_overrides(scheme: str = "all") -> None:
    allowed = {
        name
        for profile in selected_profiles(scheme)
        for name in profile.dictionaries
    }
    backup()
    entries = parse_overrides(ROOT / "pantsu_overrides.tsv")
    selected = {
        key: record
        for key, record in entries.items()
        if record[2] in allowed
    }
    untouched = {
        key: record
        for key, record in entries.items()
        if record[2] not in allowed
    }
    by_source: dict[tuple[str, str, str], list[list[str]]] = {}
    for record in selected.values():
        by_source.setdefault(
            (record[2], record[4], record[5]), []
        ).append(record)

    repaired: dict[str, list[str]] = {}
    unresolved: list[str] = []
    file_lines: dict[str, list[str]] = {}
    for (name, word, code), records in by_source.items():
        lines = file_lines.setdefault(
            name,
            (ROOT / name).read_text(encoding="utf-8-sig").splitlines(),
        )
        candidates = [
            number
            for number, raw in enumerate(lines, 1)
            if raw.rstrip("\r") == f"{word}\t{code}"
        ]
        unused = set(candidates)
        records.sort(key=lambda item: int(item[3]))
        for record in records:
            old_line = int(record[3])
            if unused:
                line_number = min(
                    unused,
                    key=lambda number: (abs(number - old_line), number),
                )
                unused.remove(line_number)
                record[3] = str(line_number)
                record[1] = f"{name}:{line_number}:{word}:{code}"
            else:
                unresolved.append("\t".join(record))
            repaired[record[1]] = record

    write_overrides({**untouched, **repaired})
    if unresolved:
        atomic_write(
            ROOT / "pantsu_override_repair_unresolved.tsv",
            "\n".join(unresolved) + "\n",
        )
    else:
        (ROOT / "pantsu_override_repair_unresolved.tsv").unlink(
            missing_ok=True
        )
    print(
        f"已重定位 {len(repaired) - len(unresolved)} 条覆盖，"
        f"{len(unresolved)} 条无法定位"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="胖次键道维护工具")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("backup")
    restore_parser = sub.add_parser("restore")
    restore_parser.add_argument("name")
    restore_log_parser = sub.add_parser("restore-log")
    restore_log_parser.add_argument("name", nargs="?")
    sub.add_parser("logs")
    merge_parser = sub.add_parser("merge-sync")
    merge_parser.add_argument("directories", nargs="+")
    history_parser = sub.add_parser("history")
    history_parser.add_argument("-n", type=int, default=30)
    scheme_choices = ["all", *SCHEME_PROFILES]
    health_parser = sub.add_parser("health")
    health_parser.add_argument("--scheme", choices=scheme_choices, default="all")
    apply_parser = sub.add_parser("apply-overrides")
    apply_parser.add_argument("--scheme", choices=scheme_choices, default="all")
    repair_parser = sub.add_parser("repair-overrides")
    repair_parser.add_argument("--scheme", choices=scheme_choices, default="all")
    sub.add_parser("sync-export")
    sub.add_parser("sync-merge")
    phone_parser = sub.add_parser("sync-phone")
    phone_parser.add_argument("directory", nargs="?")
    configure_parser = sub.add_parser("configure-sync")
    configure_parser.add_argument("directory", nargs="?")
    sub.add_parser("interactive")
    sub.add_parser("migrate-orders")
    performance_parser = sub.add_parser("performance")
    performance_parser.add_argument("-n", type=int, default=20)
    sub.add_parser("stress")
    sub.add_parser("self-benchmark")
    sub.add_parser("rebuild-runtime")
    args = parser.parse_args()
    if args.command == "backup":
        backup()
    elif args.command == "restore":
        restore(args.name)
    elif args.command == "restore-log":
        if args.name:
            restore_merge_log(args.name)
        else:
            restore_merge_log_interactive()
    elif args.command == "logs":
        show_merge_logs()
    elif args.command == "merge-sync":
        merge_sync(args.directories)
    elif args.command == "history":
        show_history(args.n)
    elif args.command == "health":
        health(args.scheme)
    elif args.command == "apply-overrides":
        apply_overrides(args.scheme)
    elif args.command == "repair-overrides":
        repair_overrides(args.scheme)
    elif args.command == "sync-export":
        sync_export()
    elif args.command == "sync-merge":
        sync_merge()
    elif args.command == "sync-phone":
        if not sync_phone(args.directory):
            raise SystemExit(1)
    elif args.command == "configure-sync":
        if args.directory:
            path = Path(args.directory).expanduser()
            if not path.is_dir():
                raise SystemExit(f"目录不存在：{path}")
            save_shared_directory(path)
            print(f"已保存：{path.resolve()}")
        else:
            choose_shared_directory()
    elif args.command == "interactive":
        interactive()
    elif args.command == "migrate-orders":
        migrate_candidate_orders()
    elif args.command == "performance":
        show_performance(args.n)
    elif args.command == "stress":
        run_stress_test()
    elif args.command == "self-benchmark":
        run_self_word_benchmark()
    elif args.command == "rebuild-runtime":
        ensure_runtime_directories()
        roots = regenerate_dynamic_roots()
        print(f"已刷新运行缓存：{roots} 个动态前缀")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
