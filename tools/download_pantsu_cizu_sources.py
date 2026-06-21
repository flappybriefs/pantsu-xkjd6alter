#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from pantsu_merge_cizu import SOURCE_LOCK, combined_sha256, sha256

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def checkout(url: str, commit: str, target: Path) -> None:
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    run("git", "-C", str(target), "init", "-q")
    run("git", "-C", str(target), "remote", "add", "origin", url)
    run(
        "git",
        "-C",
        str(target),
        "fetch",
        "-q",
        "--depth",
        "1",
        "origin",
        commit,
    )
    run("git", "-C", str(target), "checkout", "-q", "FETCH_HEAD")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="下载并校验胖次键道合并词库固定语料"
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=ROOT / "build/cizu_sources",
    )
    args = parser.parse_args()
    target = args.target.resolve()
    target.mkdir(parents=True, exist_ok=True)

    wheel_dir = target / "wheel"
    shutil.rmtree(wheel_dir, ignore_errors=True)
    wheel_dir.mkdir()
    run(
        sys.executable,
        "-m",
        "pip",
        "download",
        "-q",
        "--no-deps",
        "--dest",
        str(wheel_dir),
        "wordfreq==3.1.1",
    )
    wheel = next(wheel_dir.glob("wordfreq-3.1.1-*.whl"))
    if sha256(wheel) != SOURCE_LOCK["wordfreq"]["sha256"]:
        raise SystemExit("wordfreq 下载文件校验失败")

    rime = target / "rime-essay"
    checkout(
        SOURCE_LOCK["rime_essay"]["url"],
        SOURCE_LOCK["rime_essay"]["commit"],
        rime,
    )
    if sha256(rime / "essay.txt") != SOURCE_LOCK["rime_essay"]["sha256"]:
        raise SystemExit("Rime Essay 下载文件校验失败")

    thuocl = target / "THUOCL"
    checkout(
        SOURCE_LOCK["thuocl"]["url"],
        SOURCE_LOCK["thuocl"]["commit"],
        thuocl,
    )
    if (
        combined_sha256(list((thuocl / "data").glob("*.txt")))
        != SOURCE_LOCK["thuocl"]["sha256"]
    ):
        raise SystemExit("THUOCL 下载文件校验失败")

    names = target / "Chinese-Names-Corpus"
    checkout(
        SOURCE_LOCK["chinese_names"]["url"],
        SOURCE_LOCK["chinese_names"]["commit"],
        names,
    )
    names_file = (
        names
        / "Chinese_Names_Corpus"
        / "Chinese_Names_Corpus（120W）.txt"
    )
    if sha256(names_file) != SOURCE_LOCK["chinese_names"]["sha256"]:
        raise SystemExit("中文人名语料下载文件校验失败")

    python_dir = target / "python"
    shutil.rmtree(python_dir, ignore_errors=True)
    run(
        sys.executable,
        "-m",
        "pip",
        "install",
        "-q",
        "--target",
        str(python_dir),
        "wordfreq==3.1.1",
        "jieba==0.42.1",
    )

    print("下载及校验完成")
    print(f"wordfreq wheel: {wheel}")
    print(f"Rime Essay: {rime / 'essay.txt'}")
    print(f"THUOCL: {thuocl / 'data'}")
    print(f"中文人名语料: {names_file}")
    print(f"Python 依赖: {python_dir}")


if __name__ == "__main__":
    main()
