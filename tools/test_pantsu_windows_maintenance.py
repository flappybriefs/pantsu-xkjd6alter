#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path


def load_module(source: Path):
    spec = importlib.util.spec_from_file_location(
        "pantsu_windows_maintenance",
        source / "tools/pantsu_windows_maintenance.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def state(root: Path, name: str) -> Path:
    path = root / "pantsu_userdata" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_minimal_state(root: Path, device: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    state(root, "pantsu_overrides.tsv").write_text("version\t2\n", encoding="utf-8")
    state(root, "pantsu_candidate_order.tsv").write_text(
        "version\t2\n", encoding="utf-8")
    state(root, "pantsu_self_words.tsv").write_text("version\t1\n", encoding="utf-8")
    state(root, "pantsu_self_words_ops.tsv").write_text(
        "version\t1\n", encoding="utf-8")
    state(root, "pantsu_usage.tsv").write_text(
        f"version\t1\nword\t测试词\t{device}\t1\t1\n", encoding="utf-8")
    state(root, "pantsu_usage_events.tsv").write_text(
        "version\t1\n", encoding="utf-8")
    state(root, "pantsu_history.tsv").write_text("", encoding="utf-8")
    (root / "pantsu.user.dict.yaml").write_text("", encoding="utf-8")
    (root / "pantsu.zzc.dict.yaml").write_text("", encoding="utf-8")
    (root / "user.yaml").write_text("last_build_time: 1\n", encoding="utf-8")


def main() -> None:
    source = Path(__file__).resolve().parents[1]
    maintenance = load_module(source)

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "rime"
        sync = Path(directory) / "sync"
        write_minimal_state(root, "local")
        write_minimal_state(sync, "sync")
        maintenance.ROOT = root
        maintenance.save_sync_directory(sync)
        state(sync, "pantsu_usage.tsv").write_text(
            "version\t1\nword\t同步词\tsync\t3\t3\n",
            encoding="utf-8",
        )
        (sync / "pantsu_usage.tsv").write_text(
            "version\t1\nword\t旧路径新词\tsync\t5\t5\n",
            encoding="utf-8",
        )
        os.utime(state(root, "pantsu_usage.tsv"), ns=(10, 10))
        os.utime(state(sync, "pantsu_usage.tsv"), ns=(20, 20))
        os.utime(sync / "pantsu_usage.tsv", ns=(30, 30))
        maintenance.sync_state_directory()
        assert "旧路径新词" in state(root, "pantsu_usage.tsv").read_text(
            encoding="utf-8")
        assert "旧路径新词" in state(sync, "pantsu_usage.tsv").read_text(
            encoding="utf-8")
        assert not (sync / "pantsu_usage.tsv").exists()
        assert state(root, "pantsu_dynamic_roots.tsv").exists()

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        maintenance.ROOT = root
        header = "---\nname: test\nversion: \"1\"\nsort: original\n...\n"
        (root / "pantsu.cizu.dict.yaml").write_text(
            header + "多发区\tdfqua\t0\n",
            encoding="utf-8",
        )
        for name in (
            "pantsu.core.dict.yaml",
            "pantsu.danzi.dict.yaml",
            "pantsu.user.dict.yaml",
            "pantsu.zzc.dict.yaml",
        ):
            (root / name).write_text(header, encoding="utf-8")
        line_number = len(header.splitlines()) + 1
        (root / "pantsu_overrides.tsv").write_text(
            "version\t2\n"
            f"entry\tweighted\tpantsu.cizu.dict.yaml\t{line_number}\t"
            "多发区\tdfqua\tdfquav\t1\t11\twindows\n",
            encoding="utf-8",
        )
        state(root, "pantsu_self_words.tsv").write_text(
            "version\t1\nword\t快照词\tkzcv\t1\t10\twindows\n",
            encoding="utf-8",
        )
        state(root, "pantsu_self_words_ops.tsv").write_text(
            "version\t1\nword\t增量词\tzlcv\t1\t11\twindows\n",
            encoding="utf-8",
        )
        state(root, "pantsu_usage.tsv").write_text(
            "version\t1\nword\t快照词\twindows\t2\t10\n",
            encoding="utf-8",
        )
        state(root, "pantsu_usage_events.tsv").write_text(
            "version\t1\ndelta\t增量词\twindows\t3\t11\n",
            encoding="utf-8",
        )
        maintenance.apply_overrides()
        assert "多发区\tdfquav\t0" in (
            root / "pantsu.cizu.dict.yaml"
        ).read_text(encoding="utf-8")
        assert maintenance.parse_overrides() == {}
        assert not (root / "pantsu_overrides.tsv").exists()
        assert state(root, "pantsu_overrides.tsv").exists()
        assert state(root, "pantsu_self_words_ops.tsv").read_text(
            encoding="utf-8"
        ) == "version\t1\n"
        assert state(root, "pantsu_usage_events.tsv").read_text(
            encoding="utf-8"
        ) == "version\t1\n"
        assert "增量词" in state(root, "pantsu_self_words.tsv").read_text(
            encoding="utf-8"
        )
        assert "增量词" in state(root, "pantsu_usage.tsv").read_text(
            encoding="utf-8"
        )
        assert state(root, "pantsu_dynamic_roots.tsv").exists()


if __name__ == "__main__":
    main()
