#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path


def load_module(source: Path):
    sys.path.insert(0, str(source / "tools"))
    spec = importlib.util.spec_from_file_location(
        "pantsu_maintenance",
        source / "tools/pantsu_maintenance.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_state(root: Path, device: str, count: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "installation.yaml").write_text(
        f"installation_id: {device}\n",
        encoding="utf-8",
    )
    (root / "pantsu_usage.tsv").write_text(
        f"version\t1\nword\t测试词\t{device}\t{count}\t{count}\n",
        encoding="utf-8",
    )
    (root / "pantsu_usage_events.tsv").write_text(
        "version\t1\n",
        encoding="utf-8",
    )
    (root / "pantsu_overrides.tsv").write_text(
        "version\t2\n",
        encoding="utf-8",
    )
    (root / "pantsu_candidate_order.tsv").write_text(
        "version\t2\n",
        encoding="utf-8",
    )
    (root / "pantsu_refined_candidate_order.tsv").write_text(
        "version\t2\n",
        encoding="utf-8",
    )
    (root / "pantsu_self_words.tsv").write_text(
        "version\t1\n",
        encoding="utf-8",
    )


def write_health_fixture(root: Path) -> None:
    dictionary_header = (
        "---\n"
        "name: test\n"
        'version: "1"\n'
        "sort: original\n"
        "...\n"
    )
    for name in [
        "pantsu.core.dict.yaml",
        "pantsu.refined.core.dict.yaml",
        "pantsu.danzi.dict.yaml",
        "pantsu.cizu.dict.yaml",
        "pantsu.refined.dict.yaml",
        "pantsu.temp.dict.yaml",
        "pantsu.user.dict.yaml",
        "pantsu.waigua.dict.yaml",
    ]:
        body = "大脚板\tdjbvu\n" if name == "pantsu.cizu.dict.yaml" else ""
        (root / name).write_text(
            dictionary_header + body,
            encoding="utf-8",
        )
    (root / "pantsu.zzc.dict.yaml").write_text(
        dictionary_header
        + "#region <自造词>#\n"
        + "#endregion <自造词>#\n",
        encoding="utf-8",
    )
    source_line = len(dictionary_header.splitlines()) + 1
    (root / "pantsu_overrides.tsv").write_text(
        "version\t2\n"
        f"entry\tfixture\tpantsu.cizu.dict.yaml\t{source_line}\t"
        "大脚板\tdjbvu\tdjbvuv\t1\t10\tmac\n",
        encoding="utf-8",
    )
    (root / "pantsu_candidate_order.tsv").write_text(
        "version\t2\n"
        "meta\tdjbvuv\t10\tmac\t1\n"
        "item\tdjbvuv\t1\t大脚板\n",
        encoding="utf-8",
    )


def main() -> None:
    source = Path(__file__).resolve().parents[1]
    maintenance = load_module(source)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "computer"
        phone = Path(directory) / "phone"
        write_state(root, "mac", 3)
        write_state(phone, "iphone", 7)
        (phone / "hamster.yaml").write_text("rime: {}\n", encoding="utf-8")

        maintenance.ROOT = root
        maintenance.LOCAL_CONFIG = root / ".pantsu_maintenance.json"
        assert maintenance.looks_like_rime_root(phone)
        assert maintenance.state_directories(phone) == [phone]
        assert maintenance.sync_phone(
            str(phone),
            reload_desktop=False,
        )

        usage = maintenance.parse_usage(root)
        assert usage[("测试词", "mac")] == (3, 3)
        assert usage[("测试词", "iphone")] == (7, 7)
        assert (
            phone
            / "sync"
            / "mac"
            / "pantsu_usage.tsv"
        ).exists()
        assert (
            phone
            / "sync"
            / "mac"
            / "pantsu_refined_candidate_order.tsv"
        ).exists()
        assert list((root / "backups").iterdir())

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        write_health_fixture(root)
        maintenance.ROOT = root
        issues = maintenance.health()
        assert issues == []
        report = (root / "pantsu_health_report.tsv").read_text(
            encoding="utf-8"
        )
        assert "正常\t检查通过" in report
        assert "胖次键道、胖次键道·精炼版" in report
        assert "orphan_order" not in report

        orders = root / "pantsu_candidate_order.tsv"
        orders.write_text(
            orders.read_text(encoding="utf-8").replace(
                "大脚板",
                "不存在的词",
            ),
            encoding="utf-8",
        )
        issues = maintenance.health()
        assert len(issues) == 1
        assert issues[0][0:2] == ["警告", "候选顺序失效"]
        report = (root / "pantsu_health_report.tsv").read_text(
            encoding="utf-8"
        )
        assert "该方案的生效词库中找不到" in report
        assert "确认词条已删除后" in report

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        write_health_fixture(root)
        maintenance.ROOT = root
        refined = root / "pantsu.refined.dict.yaml"
        refined.write_text(
            refined.read_text(encoding="utf-8")
            + "精炼测试\tjlce\n",
            encoding="utf-8",
        )
        line_number = len(refined.read_text(encoding="utf-8").splitlines())
        (root / "pantsu_overrides.tsv").write_text(
            "version\t2\n"
            f"entry\trefined\tpantsu.refined.dict.yaml\t{line_number}\t"
            "精炼测试\tjlce\tjlcev\t1\t10\tmac\n"
            "entry\tclassic\tpantsu.cizu.dict.yaml\t6\t"
            "大脚板\tdjbvu\tdjbvuv\t1\t10\tmac\n",
            encoding="utf-8",
        )
        (root / "pantsu_candidate_order.tsv").write_text(
            "version\t2\n",
            encoding="utf-8",
        )
        assert maintenance.health("pantsu_refined") == []
        maintenance.apply_overrides("pantsu_refined")
        assert "精炼测试\tjlcev" in refined.read_text(encoding="utf-8")
        remaining = maintenance.parse_overrides(
            root / "pantsu_overrides.tsv"
        )
        assert set(remaining) == {"classic"}
        snapshots = sorted((root / "backups").iterdir())
        assert (snapshots[-1] / "pantsu.refined.dict.yaml").exists()

    print("PASS maintenance interactive sync workflow")


if __name__ == "__main__":
    main()
