#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path


USERDATA_DIR_NAME = "pantsu_userdata"


def data_relative_path(name: str | Path) -> Path:
    path = Path(name)
    if path.parent == Path(".") and path.suffix.lower() == ".tsv":
        return Path(USERDATA_DIR_NAME) / path.name
    return path


def data_path(root: Path, name: str | Path) -> Path:
    return root / data_relative_path(name)


def legacy_data_path(root: Path, name: str | Path) -> Path:
    return root / Path(name)


def existing_data_path(root: Path, name: str | Path) -> Path:
    canonical = data_path(root, name)
    if canonical.exists():
        return canonical
    legacy = legacy_data_path(root, name)
    if legacy != canonical and legacy.exists():
        return legacy
    return canonical


def data_variants(root: Path, name: str | Path) -> list[Path]:
    """Return canonical and divergent legacy copies as independent sources."""
    canonical = data_path(root, name)
    legacy = legacy_data_path(root, name)
    paths = [path for path in (canonical, legacy) if path.exists()]
    if len(paths) == 2 and canonical.read_bytes() == legacy.read_bytes():
        return [canonical]
    return paths


def retire_legacy_state_files(root: Path, names: tuple[str, ...]) -> int:
    """Drop legacy copies only after their canonical replacements are written."""
    removed = 0
    for name in names:
        canonical = data_path(root, name)
        legacy = legacy_data_path(root, name)
        if legacy != canonical and canonical.exists() and legacy.exists():
            legacy.unlink()
            removed += 1
    return removed


def remove_legacy_duplicate(root: Path, canonical: Path) -> None:
    userdata_dir = root / USERDATA_DIR_NAME
    if canonical.parent != userdata_dir:
        return
    legacy = root / canonical.name
    if legacy.exists():
        legacy.unlink()


def validate_no_legacy_conflict(root: Path, canonical: Path) -> None:
    userdata_dir = root / USERDATA_DIR_NAME
    if canonical.parent != userdata_dir or not canonical.exists():
        return
    legacy = root / canonical.name
    if legacy.exists() and legacy.read_bytes() != canonical.read_bytes():
        raise RuntimeError(
            f"新旧 TSV 内容冲突，未写入：{legacy} -> {canonical}"
        )


def migrate_root_tsvs(root: Path) -> list[tuple[Path, Path]]:
    target_dir = root / USERDATA_DIR_NAME
    legacy_files = sorted(path for path in root.glob("*.tsv") if path.is_file())
    if not legacy_files:
        return []
    target_dir.mkdir(parents=True, exist_ok=True)
    moved: list[tuple[Path, Path]] = []
    for source in legacy_files:
        target = target_dir / source.name
        if target.exists():
            if target.read_bytes() != source.read_bytes():
                raise RuntimeError(
                    f"新旧 TSV 内容冲突，未自动覆盖：{source} -> {target}"
                )
            source.unlink()
        else:
            shutil.move(str(source), str(target))
        moved.append((source, target))
    return moved
