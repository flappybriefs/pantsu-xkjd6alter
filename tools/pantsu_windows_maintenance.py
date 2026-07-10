#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_NAME = "pantsu_windows_maintenance.json"
USERDATA_DIR_NAME = "pantsu_userdata"
STATE_FILES = (
    "pantsu_overrides.tsv",
    "pantsu_candidate_order.tsv",
    "pantsu_self_words.tsv",
    "pantsu_self_words_ops.tsv",
    "pantsu_usage.tsv",
    "pantsu_usage_events.tsv",
    "pantsu_history.tsv",
    "pantsu.user.dict.yaml",
    "pantsu.zzc.dict.yaml",
)
DICTIONARIES = (
    "pantsu.core.dict.yaml",
    "pantsu.danzi.dict.yaml",
    "pantsu.cizu.dict.yaml",
    "pantsu.user.dict.yaml",
    "pantsu.zzc.dict.yaml",
    "pantsu.en.dict.yaml",
    "english.dict.yaml",
    "pantsufc.dict.yaml",
    "pantsuef.dict.yaml",
)
CODE_DICTIONARIES = (
    "pantsu.core.dict.yaml",
    "pantsu.danzi.dict.yaml",
    "pantsu.cizu.dict.yaml",
    "pantsu.user.dict.yaml",
    "pantsu.zzc.dict.yaml",
)
REQUIRED_FILES = (
    "default.custom.yaml",
    "pantsu.schema.yaml",
    "pantsu.extended.dict.yaml",
    "pantsu.en.schema.yaml",
    "english.schema.yaml",
    "pantsufc.schema.yaml",
    "pantsuef.schema.yaml",
    "symbols.yaml",
    "opencc/pantsu_es.json",
    "opencc/pantsu_es.txt",
    "opencc/s2t.json",
    "opencc/EN2en.json",
    "opencc/pinyin.json",
    "opencc/pantsu_noop.txt",
    *DICTIONARIES,
    *STATE_FILES,
)


def data_relative_path(name: str | Path) -> Path:
    path = Path(name)
    if path.parent == Path(".") and path.suffix.lower() == ".tsv":
        return Path(USERDATA_DIR_NAME) / path.name
    return path


def data_path(root: Path, name: str | Path) -> Path:
    return root / data_relative_path(name)


def existing_data_path(root: Path, name: str | Path) -> Path:
    canonical = data_path(root, name)
    if canonical.exists():
        return canonical
    legacy = root / Path(name)
    if legacy != canonical and legacy.exists():
        return legacy
    return canonical


def migrate_root_tsvs(root: Path) -> int:
    sources = sorted(path for path in root.glob("*.tsv") if path.is_file())
    if not sources:
        return 0
    target_dir = root / USERDATA_DIR_NAME
    target_dir.mkdir(parents=True, exist_ok=True)
    for source in sources:
        target = target_dir / source.name
        if target.exists():
            if target.read_bytes() != source.read_bytes():
                raise RuntimeError(f"新旧 TSV 内容冲突：{source} -> {target}")
            source.unlink()
        else:
            shutil.move(str(source), str(target))
    return len(sources)


def reconcile_legacy_root_tsvs(root: Path) -> tuple[int, int]:
    """Promote old root TSVs after backup using Windows' mtime sync policy."""
    moved = 0
    replaced = 0
    for source in sorted(root.glob("*.tsv")):
        if not source.is_file():
            continue
        target = data_path(root, source.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != source.read_bytes():
            if source.stat().st_mtime_ns > target.stat().st_mtime_ns:
                shutil.copy2(source, target)
                replaced += 1
        elif not target.exists():
            shutil.move(str(source), str(target))
            moved += 1
            continue
        source.unlink()
        moved += 1
    return moved, replaced


def remove_legacy_duplicate(root: Path, canonical: Path) -> None:
    if canonical.parent != root / USERDATA_DIR_NAME:
        return
    legacy = root / canonical.name
    if legacy.exists():
        legacy.unlink()


def validate_no_legacy_conflict(root: Path, canonical: Path) -> None:
    if canonical.parent != root / USERDATA_DIR_NAME or not canonical.exists():
        return
    legacy = root / canonical.name
    if legacy.exists() and legacy.read_bytes() != canonical.read_bytes():
        raise RuntimeError(f"新旧 TSV 内容冲突：{legacy} -> {canonical}")


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    validate_no_legacy_conflict(ROOT, path)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)
    remove_legacy_duplicate(ROOT, path)


def config_path() -> Path:
    return ROOT / CONFIG_NAME


def load_config() -> dict[str, str]:
    path = config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(config: dict[str, str]) -> None:
    atomic_write(
        config_path(),
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
    )


def sync_directory() -> Path | None:
    value = load_config().get("sync_directory", "")
    if not value:
        return None
    return Path(value).expanduser()


def save_sync_directory(path: Path) -> None:
    config = load_config()
    config["sync_directory"] = str(path.resolve())
    save_config(config)


def pause() -> None:
    input("\n按回车继续……")


def timestamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def safe_rows(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8-sig").splitlines()


def backup() -> Path:
    target = ROOT / "backups" / f"windows-{timestamp()}"
    target.mkdir(parents=True, exist_ok=False)
    copied = 0
    for name in REQUIRED_FILES:
        source = existing_data_path(ROOT, name)
        if source.exists() and source.is_file():
            destination = target / data_relative_path(name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied += 1
        legacy = ROOT / name
        if (
            Path(name).suffix.lower() == ".tsv"
            and legacy.exists()
            and legacy.is_file()
            and legacy != source
        ):
            destination = target / "legacy_root" / Path(name).name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, destination)
            copied += 1
    print(f"已备份 {copied} 个文件到：{target}")
    return target


def backup_directory(directory: Path, label: str) -> Path | None:
    if not directory.exists():
        return None
    target = ROOT / "backups" / f"windows-{label}-{timestamp()}"
    target.mkdir(parents=True, exist_ok=False)
    copied = 0
    for name in STATE_FILES:
        source = existing_data_path(directory, name)
        if source.exists() and source.is_file():
            destination = target / data_relative_path(name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied += 1
        legacy = directory / name
        if legacy.exists() and legacy.is_file() and legacy != source:
            destination = target / "legacy_root" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, destination)
            copied += 1
    print(f"已备份 {label} 状态 {copied} 个文件到：{target}")
    return target


def parse_self_words(path: Path) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for raw in safe_rows(path):
        fields = raw.split("\t")
        if len(fields) >= 6 and fields[0] == "word":
            result[f"{fields[1]}\t{fields[2]}"] = fields
    return result


def record_version(record: list[str]) -> tuple[int, str]:
    updated = int(record[4]) if len(record) > 4 and record[4].isdigit() else 0
    device = record[5] if len(record) > 5 else "unknown"
    return updated, device


def effective_self_words() -> dict[str, list[str]]:
    result = parse_self_words(
        existing_data_path(ROOT, "pantsu_self_words.tsv")
    )
    for key, record in parse_self_words(
        existing_data_path(ROOT, "pantsu_self_words_ops.tsv")
    ).items():
        current = result.get(key)
        if current is None or record_version(record) >= record_version(current):
            result[key] = record
    return result


def write_self_words(records: dict[str, list[str]]) -> None:
    lines = ["version\t1"]
    lines.extend("\t".join(records[key]) for key in sorted(records))
    atomic_write(
        data_path(ROOT, "pantsu_self_words.tsv"), "\n".join(lines) + "\n"
    )
    atomic_write(
        data_path(ROOT, "pantsu_self_words_ops.tsv"), "version\t1\n"
    )


def parse_usage() -> dict[tuple[str, str], tuple[int, int]]:
    result: dict[tuple[str, str], tuple[int, int]] = {}
    for name, kind in (
        ("pantsu_usage.tsv", "word"),
        ("pantsu_usage_events.tsv", "event"),
    ):
        for raw in safe_rows(existing_data_path(ROOT, name)):
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


def write_usage(records: dict[tuple[str, str], tuple[int, int]]) -> None:
    lines = ["version\t1"]
    for (word, device), (count, updated) in sorted(records.items()):
        lines.append(f"word\t{word}\t{device}\t{count}\t{updated}")
    atomic_write(data_path(ROOT, "pantsu_usage.tsv"), "\n".join(lines) + "\n")
    atomic_write(
        data_path(ROOT, "pantsu_usage_events.tsv"), "version\t1\n"
    )


def parse_overrides() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for raw in safe_rows(existing_data_path(ROOT, "pantsu_overrides.tsv")):
        fields = raw.split("\t")
        if len(fields) >= 10 and fields[0] == "entry":
            result[fields[1]] = fields
    return result


def write_overrides(records: dict[str, list[str]]) -> None:
    lines = ["version\t1"]
    lines.extend("\t".join(records[key]) for key in sorted(records))
    atomic_write(data_path(ROOT, "pantsu_overrides.tsv"), "\n".join(lines) + "\n")


def parse_candidate_orders() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for raw in safe_rows(
        existing_data_path(ROOT, "pantsu_candidate_order.tsv")
    ):
        fields = raw.split("\t")
        if len(fields) >= 5 and fields[0] == "meta":
            result[fields[1]] = {
                "active": fields[4] == "1",
                "items": [],
            }
        elif len(fields) >= 4 and fields[0] == "item":
            state = result.setdefault(fields[1], {"active": True, "items": []})
            state["items"].append([fields[2], fields[3]])
    return result


def root_for_code(code: str, *, order: bool = False) -> str | None:
    if code == "-":
        code = ""
    if len(code) < 2:
        return None
    if order:
        return code[:4] if len(code) > 4 else code[:-1]
    return code[: min(4, len(code))]


def read_build_time() -> str:
    for raw in safe_rows(ROOT / "user.yaml"):
        stripped = raw.strip()
        if stripped.startswith("last_build_time:"):
            return stripped.split(":", 1)[1].strip()
    return ""


def rebuild_dynamic_roots() -> int:
    roots: set[str] = set()
    for raw in safe_rows(
        existing_data_path(ROOT, "pantsu_dynamic_roots.tsv")
    ):
        fields = raw.split("\t")
        if len(fields) >= 2 and fields[0] == "root" and fields[1]:
            roots.add(fields[1])
    for record in parse_overrides().values():
        for code in (record[5], record[6]):
            root = root_for_code(code)
            if root:
                roots.add(root)
    for record in effective_self_words().values():
        if len(record) >= 4 and record[3] == "1":
            root = root_for_code(record[2])
            if root:
                roots.add(root)
    for code, state in parse_candidate_orders().items():
        if state.get("active", True):
            root = root_for_code(code, order=True)
            if root:
                roots.add(root)
    lines = [
        "format\t9",
        f"build\t{read_build_time()}",
        "signature\t",
    ]
    lines.extend(f"root\t{root}" for root in sorted(roots))
    atomic_write(
        data_path(ROOT, "pantsu_dynamic_roots.tsv"),
        "\n".join(lines) + "\n",
    )
    return len(roots)


def compact_runtime(*, create_backup: bool = True, announce: bool = True) -> dict[str, int]:
    if create_backup:
        backup()
    reconcile_legacy_root_tsvs(ROOT)
    self_words = effective_self_words()
    usage = parse_usage()
    write_self_words(self_words)
    write_usage(usage)
    root_count = rebuild_dynamic_roots()
    (ROOT / "build").mkdir(exist_ok=True)
    (ROOT / "build" / "pantsu_undo").mkdir(parents=True, exist_ok=True)
    result = {
        "self_words": len(self_words),
        "usage_words": len({word for word, _ in usage}),
        "dynamic_roots": root_count,
    }
    if announce:
        print(f"自造词快照：{result['self_words']} 条")
        print(f"词频统计：{result['usage_words']} 个词")
        print(f"动态前缀缓存：{result['dynamic_roots']} 个")
        print("已压缩运行态日志。建议随后重新部署小狼毫。")
    return result


def choose_sync_directory() -> Path | None:
    current = sync_directory()
    print(f"当前同步目录：{current or '未设置'}")
    value = input("请输入 Windows/网盘/移动盘上的 Rime 同步目录：").strip()
    if not value:
        print("已取消")
        return None
    path = Path(value).expanduser()
    if not path.exists():
        create = input("目录不存在，是否创建？输入 YES 确认：").strip()
        if create != "YES":
            print("设置未保存")
            return None
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        print("路径不是目录，设置未保存")
        return None
    save_sync_directory(path)
    print(f"已保存同步目录：{path.resolve()}")
    return path


def sync_state_directory() -> None:
    target = sync_directory()
    if target is None or not target.is_dir():
        print("尚未设置有效同步目录，请先设置同步目录。")
        return
    backup()
    backup_directory(target, "sync")
    local_moved, local_replaced = reconcile_legacy_root_tsvs(ROOT)
    remote_moved, remote_replaced = reconcile_legacy_root_tsvs(target)
    pulled = 0
    pushed = 0
    for name in STATE_FILES:
        local = existing_data_path(ROOT, name)
        remote = existing_data_path(target, name)
        if not local.exists() and not remote.exists():
            continue
        if remote.exists() and (
            not local.exists()
            or remote.stat().st_mtime_ns > local.stat().st_mtime_ns
        ):
            local = data_path(ROOT, name)
            local.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(remote, local)
            pulled += 1
        if local.exists() and (
            not remote.exists()
            or local.stat().st_mtime_ns > remote.stat().st_mtime_ns
        ):
            remote = data_path(target, name)
            remote.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local, remote)
            pushed += 1
    root_count = rebuild_dynamic_roots()
    print(f"同步完成：从同步目录接收 {pulled} 个文件，写回 {pushed} 个文件。")
    if local_moved or remote_moved:
        print(
            "已迁移旧根目录 TSV："
            f"本机 {local_moved} 个、同步目录 {remote_moved} 个；"
            f"按修改时间采用旧路径新版本 {local_replaced + remote_replaced} 个。"
        )
    print(f"动态前缀缓存：{root_count} 个")
    print("如果电脑和同步目录同时改过同一个状态文件，本工具会保留较新的文件。")


def health() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    for name in REQUIRED_FILES:
        path = existing_data_path(ROOT, name)
        if not path.exists():
            errors.append(f"缺少文件：{name}")
    valid_code_chars = set("abcdefghijklmnopqrstuvwxyz;/`")
    for name in CODE_DICTIONARIES:
        path = ROOT / name
        if not path.exists():
            continue
        for number, raw in enumerate(safe_rows(path), 1):
            if raw.startswith("#") or "\t" not in raw:
                continue
            fields = raw.split("\t")
            if len(fields) < 2 or not fields[0] or not fields[1]:
                errors.append(f"{name}:{number} 词条或编码为空")
                continue
            code = fields[1].strip()
            if any(char not in valid_code_chars for char in code):
                warnings.append(f"{name}:{number} 编码含非常规字符：{code}")
    self_ops = max(0, len(safe_rows(
        existing_data_path(ROOT, "pantsu_self_words_ops.tsv")
    )) - 1)
    usage_events = max(0, len(safe_rows(
        existing_data_path(ROOT, "pantsu_usage_events.tsv")
    )) - 1)
    if self_ops > 1000:
        warnings.append(f"自造词操作日志 {self_ops} 条，建议压缩")
    if usage_events > 512:
        warnings.append(f"调频事件 {usage_events} 条，建议压缩")
    print(f"健康检查：{len(errors)} 个错误，{len(warnings)} 个提醒")
    for item in errors[:30]:
        print("错误：", item)
    for item in warnings[:30]:
        print("提醒：", item)
    if len(errors) > 30 or len(warnings) > 30:
        print("输出已截断，只显示前 30 条。")
    if not errors and not warnings:
        print("当前离线部署文件状态正常。")
    return len(errors)


def apply_overrides() -> None:
    entries = parse_overrides()
    if not entries:
        print("没有需要合并的覆盖")
        return
    selected = {
        key: record
        for key, record in entries.items()
        if len(record) >= 10 and record[2] in CODE_DICTIONARIES
    }
    if not selected:
        print("没有指向胖次键道基础词库的覆盖")
        return
    backup()
    reconcile_legacy_root_tsvs(ROOT)
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
        if not path.exists():
            unresolved.extend(
                [key, name, str(number), "基础词库不存在"]
                for number, (key, _) in changes.items()
            )
            continue
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        output: list[str] = []
        for number, raw in enumerate(lines, 1):
            item = changes.get(number)
            if not item:
                output.append(raw)
                continue
            key, record = item
            fields = raw.rstrip("\r").split("\t")
            if (
                len(fields) < 2
                or fields[0] != record[4]
                or fields[1] != record[5]
            ):
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
    write_overrides({
        key: record
        for key, record in entries.items()
        if key not in applied
    })
    unresolved_path = data_path(
        ROOT, "pantsu_apply_overrides_unresolved.tsv"
    )
    if unresolved:
        atomic_write(
            unresolved_path,
            "\n".join("\t".join(row) for row in unresolved) + "\n",
        )
    else:
        unresolved_path.unlink(missing_ok=True)
    print(f"已将 {len(applied)} 条覆盖合并回胖次键道基础词库")
    if applied:
        compacted = compact_runtime(create_backup=False, announce=False)
        print(
            "已压缩关联运行态："
            f"自造词 {compacted['self_words']} 条；"
            f"词频 {compacted['usage_words']} 个；"
            f"动态前缀 {compacted['dynamic_roots']} 个"
        )
    if unresolved:
        print(f"{len(unresolved)} 条覆盖暂未合并，已写入：{unresolved_path.name}")


def run_performance() -> None:
    script = ROOT / "tools" / "pantsu_performance.py"
    if not script.exists():
        print("缺少性能测试脚本：tools/pantsu_performance.py")
        return
    subprocess.run([sys.executable, str(script)], cwd=ROOT, check=False)


def export_state_package() -> Path:
    target = ROOT / "backups" / f"pantsu-state-{timestamp()}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in STATE_FILES:
            path = existing_data_path(ROOT, name)
            if path.exists():
                archive.write(path, data_relative_path(name).as_posix())
    print(f"已生成状态同步包：{target}")
    print("把这个 zip 带回 Mac 后，解压覆盖同名状态文件，再运行 Mac 维护工具合并。")
    return target


def deploy_weasel() -> bool:
    candidates: list[Path] = []
    env = os.environ.get("WEASEL_DEPLOYER")
    if env:
        candidates.append(Path(env))
    for base in (
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
    ):
        if not base:
            continue
        root = Path(base)
        candidates.extend(root.glob("Rime/weasel*/WeaselDeployer.exe"))
        candidates.extend(root.glob("Rime/weasel*/WeaselServer.exe"))
        candidates.extend(root.glob("Programs/Rime/weasel*/WeaselDeployer.exe"))
        candidates.extend(root.glob("Programs/Rime/weasel*/WeaselServer.exe"))
    seen: set[Path] = set()
    for exe in candidates:
        if not exe.exists() or exe in seen:
            continue
        seen.add(exe)
        for arg in ("/deploy", "--deploy"):
            try:
                result = subprocess.run(
                    [str(exe), arg],
                    cwd=ROOT,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError:
                continue
            if result.returncode == 0:
                print(f"已调用小狼毫部署：{exe} {arg}")
                return True
    print("没有自动找到小狼毫部署程序。请右键小狼毫图标手动选择“重新部署”。")
    print("如果想让脚本自动部署，可设置环境变量 WEASEL_DEPLOYER 指向 WeaselDeployer.exe。")
    return False


def menu() -> None:
    while True:
        print("\n==============================")
        print("  胖次键道 Windows 离线维护")
        print("==============================")
        print(f"目录：{ROOT}")
        print(f"同步目录：{sync_directory() or '未设置'}")
        print("1. 备份当前文件")
        print("2. 健康检查")
        print("3. 同步状态目录")
        print("4. 设置同步目录")
        print("5. 应用覆盖到基础词库")
        print("6. 压缩自造词/调频日志并刷新缓存")
        print("7. 生成状态同步包")
        print("8. 尝试调用小狼毫重新部署")
        print("0. 退出")
        choice = input("请选择：").strip()
        if choice == "1":
            backup()
        elif choice == "2":
            health()
        elif choice == "3":
            sync_state_directory()
        elif choice == "4":
            choose_sync_directory()
        elif choice == "5":
            apply_overrides()
        elif choice == "6":
            compact_runtime()
        elif choice == "7":
            export_state_package()
        elif choice == "8":
            deploy_weasel()
        elif choice == "0":
            return
        else:
            print("请输入菜单中的数字。")
        pause()


def main() -> None:
    commands = {
        "backup": backup,
        "health": health,
        "compact": compact_runtime,
        "performance": run_performance,
        "export-state": export_state_package,
        "deploy": deploy_weasel,
        "set-sync-dir": choose_sync_directory,
        "sync-state": sync_state_directory,
        "apply-overrides": apply_overrides,
    }
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command not in commands:
            print("可用命令：" + ", ".join(sorted(commands)))
            raise SystemExit(2)
        commands[command]()
        return
    menu()


if __name__ == "__main__":
    main()
