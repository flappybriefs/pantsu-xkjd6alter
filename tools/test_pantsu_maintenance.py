#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
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
    (root / "pantsu_self_words.tsv").write_text(
        "version\t1\n",
        encoding="utf-8",
    )
    (root / "pantsu_history.tsv").write_text(
        f"{count}\t{device}\tpromote\tcode-{device}\t"
        f"历史-{device}\t1\n",
        encoding="utf-8",
    )
    for name in [
        "default.custom.yaml",
        "hamster.yaml",
        "pantsu.schema.yaml",
        "pantsu.extended.dict.yaml",
        "pantsu.core.dict.yaml",
        "pantsu.danzi.dict.yaml",
        "pantsu.cizu.dict.yaml",
    ]:
        (root / name).write_text(
            f"source: {device}\n",
            encoding="utf-8",
        )
    (root / "lua").mkdir(exist_ok=True)
    (root / "lua/pantsu_test.lua").write_text(
        f"return '{device}'\n",
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
        "pantsu.danzi.dict.yaml",
        "pantsu.cizu.dict.yaml",
        "pantsu.user.dict.yaml",
    ]:
        body = "大脚板\tdjbvu\n" if name == "pantsu.core.dict.yaml" else ""
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
        f"entry\tfixture\tpantsu.core.dict.yaml\t{source_line}\t"
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
        (root / "backups").mkdir()
        (root / "backups/.DS_Store").write_text("", encoding="utf-8")
        (phone / "hamster.yaml").write_text("rime: {}\n", encoding="utf-8")
        (phone / "pantsu_refined.schema.yaml").write_text(
            "old: true\n",
            encoding="utf-8",
        )
        (phone / "pantsu.waigua.dict.yaml").write_text(
            "old: true\n",
            encoding="utf-8",
        )
        (phone / "pantsu_overrides.tsv").write_text(
            "version\t2\n"
            "entry\told\tpantsu.waigua.dict.yaml\t1\t"
            "旧词\told\tnew\t1\t10\tiphone\n",
            encoding="utf-8",
        )
        (phone / "pantsu_history.tsv").write_text(
            (phone / "pantsu_history.tsv").read_text(encoding="utf-8")
            + "8\tiphone\tmake_word\tszf\t苏姿丰\t1_codes\n"
            + "9\tiphone\tmake_word\tmnea\t马尿水\t1_codes\n",
            encoding="utf-8",
        )

        maintenance.ROOT = root
        maintenance.LOCAL_CONFIG = root / ".pantsu_maintenance.json"
        maintenance.save_shared_directory(phone)
        (root / "pantsu_candidate_order.tsv").write_text(
            "version\t2\n"
            "meta\ttest\t20\tmac\t1\n"
            "item\ttest\t1\t电脑最新\n"
            "meta\ttie\t30\tmac\t1\n"
            "item\ttie\t1\t电脑同秒旧值\n",
            encoding="utf-8",
        )
        (phone / "pantsu_candidate_order.tsv").write_text(
            "version\t2\n"
            "meta\ttest\t10\tiphone\t1\n"
            "item\ttest\t1\t手机旧值\n"
            "meta\ttie\t30\tiphone\t1\n"
            "item\ttie\t1\t手机同秒新值\n",
            encoding="utf-8",
        )
        os.utime(root / "pantsu_candidate_order.tsv", ns=(10, 10))
        os.utime(phone / "pantsu_candidate_order.tsv", ns=(20, 20))
        assert maintenance.looks_like_rime_root(phone)
        assert maintenance.state_directories(phone) == [phone]
        assert maintenance.sync_phone(
            str(phone),
            reload_desktop=False,
        )

        usage = maintenance.parse_usage(root)
        assert usage[("测试词", "mac")] == (3, 3)
        assert usage[("测试词", "iphone")] == (7, 7)
        assert maintenance.parse_overrides(
            root / "pantsu_overrides.tsv"
        ) == {}
        history = maintenance.parse_history(root / "pantsu_history.tsv")
        assert {fields[1] for fields in history.values()} == {
            "mac",
            "iphone",
        }
        self_words = maintenance.parse_self_word_state(root)
        assert self_words["苏姿丰\tszf"][3] == "1"
        assert self_words["马尿水\tmnea"][3] == "1"
        zzc = (root / "pantsu.zzc.dict.yaml").read_text(encoding="utf-8")
        assert "苏姿丰\tszf" in zzc
        assert "马尿水\tmnea" in zzc
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
            / "pantsu_self_words_ops.tsv"
        ).exists()
        assert not (phone / "pantsu_refined.schema.yaml").exists()
        assert not (phone / "pantsu.waigua.dict.yaml").exists()
        assert (phone / "pantsu.core.dict.yaml").read_text(
            encoding="utf-8"
        ) == "source: mac\n"
        assert (phone / "lua/pantsu_test.lua").read_text(
            encoding="utf-8"
        ) == "return 'mac'\n"
        for directory in [
            root,
            phone,
            phone / "sync" / "mac",
            root / "sync" / "mac",
        ]:
            orders = maintenance.parse_candidate_orders(
                directory / "pantsu_candidate_order.tsv"
            )
            assert orders["test"]["items"] == [["1", "电脑最新"]]
            assert orders["tie"]["items"] == [["1", "手机同秒新值"]]
            history = maintenance.parse_history(
                directory / "pantsu_history.tsv"
            )
            assert {fields[1] for fields in history.values()} == {
                "mac",
                "iphone",
            }
        logs = maintenance.merge_logs()
        assert len(logs) == 1
        manifest = json.loads(
            (logs[0] / "manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["status"] == "success"
        assert manifest["details"]["write_back_directories"] >= 3
        assert manifest["details"]["recovered_self_words"] == 2
        operation_log = (logs[0] / "操作日志.txt").read_text(
            encoding="utf-8"
        )
        assert "竞争记录（已按最新操作自动决胜）" in operation_log
        assert "candidate_order" in operation_log
        (root / "pantsu_candidate_order.tsv").write_text(
            "version\t2\n",
            encoding="utf-8",
        )
        maintenance.restore_merge_log(logs[0].name)
        restored = maintenance.parse_candidate_orders(
            root / "pantsu_candidate_order.tsv"
        )
        assert restored["test"]["items"] == [["1", "电脑最新"]]
        for index in range(6):
            log = maintenance.create_merge_log(f"rotation-{index}", [])
            maintenance.finish_merge_log(
                log,
                status="success",
                details={"index": index},
            )
        assert len(maintenance.merge_logs()) == 5
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
        assert "胖次键道" in report
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

        write_health_fixture(root)
        maintenance.ROOT = root
        cizu = root / "pantsu.cizu.dict.yaml"
        cizu_lines = cizu.read_text(encoding="utf-8").splitlines()
        cizu_lines.append("多发区\tdfqua\t0")
        cizu.write_text("\n".join(cizu_lines) + "\n", encoding="utf-8")
        cizu_line = len(cizu_lines)
        overrides = root / "pantsu_overrides.tsv"
        overrides.write_text(
            overrides.read_text(encoding="utf-8")
            + f"entry\tweighted\tpantsu.cizu.dict.yaml\t{cizu_line}\t"
            "多发区\tdfqua\tdfquav\t1\t11\tmac\n",
            encoding="utf-8",
        )
        maintenance.apply_overrides("pantsu")
        core = root / "pantsu.core.dict.yaml"
        assert "大脚板\tdjbvuv" in core.read_text(encoding="utf-8")
        assert "多发区\tdfquav\t0" in cizu.read_text(encoding="utf-8")
        assert maintenance.parse_overrides(
            root / "pantsu_overrides.tsv"
        ) == {}
        snapshots = sorted((root / "backups").iterdir())
        assert (snapshots[-1] / "pantsu.core.dict.yaml").exists()

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        write_health_fixture(root)
        maintenance.ROOT = root
        header = (
            "---\nname: test\nversion: \"1\"\nsort: original\n...\n"
        )
        (root / "pantsu.core.dict.yaml").write_text(
            header
            + "甲乙\tqajb\n"
            + "#region <630>#\n"
            + "#endregion <630>#\n",
            encoding="utf-8",
        )
        (root / "pantsu.danzi.dict.yaml").write_text(
            header + "甲\tqaa\n乙\tjbb\n",
            encoding="utf-8",
        )
        (root / "pantsu_self_words.tsv").write_text(
            "version\t1\n"
            "word\t自造词\tqajb\t1\t10\tiphone\n",
            encoding="utf-8",
        )
        moved, removed = maintenance.reconcile_core_self_codes()
        assert (moved, removed) == (1, 0)
        assert "甲乙\tqajba" in (
            root / "pantsu.core.dict.yaml"
        ).read_text(encoding="utf-8")

        (root / "pantsu.core.dict.yaml").write_text(
            header
            + "#region <630>#\n"
            + "#endregion <630>#\n",
            encoding="utf-8",
        )
        (root / "pantsu.cizu.dict.yaml").write_text(
            header + "甲乙\tqajb\t0\n",
            encoding="utf-8",
        )
        moved, removed = maintenance.reconcile_core_self_codes()
        assert (moved, removed) == (1, 0)
        assert "甲乙\tqajba\t0" in (
            root / "pantsu.cizu.dict.yaml"
        ).read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        write_state(root, "mac", 3)
        maintenance.ROOT = root
        for relative in [".DS_Store", "build/.DS_Store", "lua/.DS_Store"]:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        for name in [
            "pantsu_health_report.tsv",
            "pantsu_sync_conflicts.tsv",
            "pantsu_override_repair_unresolved.tsv",
        ]:
            (root / name).write_text("report\n", encoding="utf-8")
        for index in range(7):
            backup = root / "backups" / f"20260702-00000{index}"
            backup.mkdir(parents=True)
            os.utime(backup, (index, index))
            log = root / "pantsu_maintenance_logs" / f"log-{index}"
            log.mkdir(parents=True)
            os.utime(log, (index, index))
        result = maintenance.cleanup_runtime(clean_shared=False)
        assert result["ds_store_removed"] == 3
        assert result["reports_archived"] == 3
        assert not list(root.rglob(".DS_Store"))
        assert not (root / "pantsu_health_report.tsv").exists()
        assert len([
            path for path in (root / "backups").iterdir()
            if path.is_dir()
        ]) == maintenance.BACKUP_LIMIT
        assert len([
            path for path in (root / "pantsu_maintenance_logs").iterdir()
            if path.is_dir() and path.name != "reports"
        ]) == maintenance.MERGE_LOG_LIMIT
        assert (root / "pantsu_self_words_ops.tsv").read_text(
            encoding="utf-8"
        ) == "version\t1\n"

    print("PASS maintenance interactive sync workflow")


if __name__ == "__main__":
    main()
