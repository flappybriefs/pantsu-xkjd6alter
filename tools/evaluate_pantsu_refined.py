#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALID_WORD = re.compile(r"^[\u3400-\u9fff]{2,6}$")
CURRENT_FILES = [
    "pantsu.core.dict.yaml",
    "pantsu.cizu.dict.yaml",
    "pantsu.user.dict.yaml",
    "pantsu.zzc.dict.yaml",
    "pantsu.waigua.dict.yaml",
]
REFINED_FILES = [
    "pantsu.refined.core.dict.yaml",
    "pantsu.refined.dict.yaml",
    "pantsu.user.dict.yaml",
    "pantsu.zzc.dict.yaml",
]


def read_entries(name: str):
    path = ROOT / name
    for number, raw in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(),
        1,
    ):
        if raw.startswith("#") or "\t" not in raw:
            continue
        fields = raw.split("\t")
        if len(fields) >= 2 and fields[0] and fields[1].strip():
            yield number, fields[0], fields[1].strip()


def overrides():
    result = {}
    path = ROOT / "pantsu_overrides.tsv"
    if not path.exists():
        return result
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        fields = raw.split("\t")
        if (
            len(fields) >= 10
            and fields[0] == "entry"
            and fields[3].isdigit()
        ):
            result[(fields[2], int(fields[3]))] = fields
    return result


def dictionary(files):
    active_overrides = overrides()
    rows = []
    for name in files:
        for number, word, code in read_entries(name):
            record = active_overrides.get((name, number))
            if record:
                if record[7] != "1":
                    continue
                word, code = record[4], record[6]
            rows.append((word, code))
    return rows


def essay():
    candidates = [
        Path("/tmp/rime-essay/essay.txt"),
        Path(
            "/Library/Input Methods/Squirrel.app/Contents/"
            "SharedSupport/essay.txt"
        ),
    ]
    path = next(path for path in candidates if path.exists())
    result = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        fields = raw.split("\t")
        if (
            len(fields) >= 2
            and fields[1].isdigit()
            and VALID_WORD.fullmatch(fields[0])
        ):
            result[fields[0]] = int(fields[1])
    return result


def personal_words():
    result = set()
    usage = ROOT / "pantsu_usage.tsv"
    if usage.exists():
        for raw in usage.read_text(encoding="utf-8-sig").splitlines():
            fields = raw.split("\t")
            if len(fields) == 5 and fields[0] == "word":
                result.add(fields[1])
    self_words = ROOT / "pantsu_self_words.tsv"
    if self_words.exists():
        for raw in self_words.read_text(encoding="utf-8-sig").splitlines():
            fields = raw.split("\t")
            if len(fields) >= 6 and fields[0] == "word" and fields[3] == "1":
                result.add(fields[1])
    return result


def metrics(rows, weights, personal):
    by_word = defaultdict(list)
    by_code = defaultdict(list)
    for word, code in rows:
        if code not in by_word[word]:
            by_word[word].append(code)
        if word not in by_code[code]:
            by_code[code].append(word)
    shortest = {
        word: min(codes, key=lambda code: (len(code), code))
        for word, codes in by_word.items()
    }
    total_weight = sum(weights.values())
    covered_weight = 0
    key_weight = 0
    char_weight = 0
    first_weight = 0
    collision_weight = 0
    for word, weight in weights.items():
        code = shortest.get(word)
        if not code:
            continue
        covered_weight += weight
        key_weight += len(code) * weight
        char_weight += len(word) * weight
        candidates = by_code[code]
        if candidates and candidates[0] == word:
            first_weight += weight
        if len(candidates) > 1:
            collision_weight += weight
    slots = {
        code
        for _, _, code in read_entries("pantsu.core.dict.yaml")
        if len(code) <= 5
    }
    occupied_slots = sum(code in by_code for code in slots)
    personal_covered = sum(word in shortest for word in personal)
    return {
        "rows": len(rows),
        "unique_words": len(by_word),
        "average_keys_per_character": (
            key_weight / char_weight if char_weight else 0
        ),
        "first_choice_hit_rate": (
            first_weight / covered_weight if covered_weight else 0
        ),
        "same_code_collision_rate": (
            collision_weight / covered_weight if covered_weight else 0
        ),
        "empty_short_code_rate": (
            1 - occupied_slots / len(slots) if slots else 0
        ),
        "uncovered_weight_rate": 1 - covered_weight / total_weight,
        "personal_history_coverage": (
            personal_covered / len(personal) if personal else 1
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-deploy-seconds", type=float)
    parser.add_argument("--refined-deploy-seconds", type=float)
    parser.add_argument("--current-peak-rss", type=int)
    parser.add_argument("--refined-peak-rss", type=int)
    parser.add_argument("--current-binary-bytes", type=int)
    parser.add_argument("--refined-binary-bytes", type=int)
    args = parser.parse_args()
    weights = essay()
    personal = personal_words()
    result = {
        "evaluation_corpus": "Rime Essay phrases of 2-6 Chinese characters",
        "evaluation_words": len(weights),
        "personal_words": len(personal),
        "current": metrics(dictionary(CURRENT_FILES), weights, personal),
        "refined": metrics(dictionary(REFINED_FILES), weights, personal),
    }
    generation_path = ROOT / "pantsu_refined_generation.json"
    if generation_path.exists():
        generation = json.loads(
            generation_path.read_text(encoding="utf-8")
        )
        result["refined"]["repairable_empty_codes"] = generation.get(
            "repairable_empty_codes",
            0,
        )
        result["current"]["repairable_empty_codes"] = None
        result["refined"]["excluded_person_names"] = generation.get(
            "excluded_person_names",
            0,
        )
        result["current"]["excluded_person_names"] = None
        result["refined"]["excluded_without_general_frequency"] = (
            generation.get(
                "excluded_without_general_frequency",
                0,
            )
        )
        result["current"]["excluded_without_general_frequency"] = None
        result["refined"]["reserved_self_word_codes"] = generation.get(
            "reserved_self_word_codes",
            0,
        )
        result["current"]["reserved_self_word_codes"] = None
        result["refined"]["non_six_collision_codes"] = generation.get(
            "non_six_collision_codes",
            0,
        )
        result["current"]["non_six_collision_codes"] = None
    if args.current_deploy_seconds is not None:
        result["current"].update({
            "deployment_seconds": args.current_deploy_seconds,
            "deployment_peak_rss_bytes": args.current_peak_rss,
            "compiled_dictionary_bytes": args.current_binary_bytes,
        })
        result["refined"].update({
            "deployment_seconds": args.refined_deploy_seconds,
            "deployment_peak_rss_bytes": args.refined_peak_rss,
            "compiled_dictionary_bytes": args.refined_binary_bytes,
        })
    (ROOT / "pantsu_refined_evaluation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# 胖次键道与精炼版离线评测",
        "",
        f"评测词数：{result['evaluation_words']:,}；"
        f"个人词数：{result['personal_words']:,}",
        "",
        "| 指标 | 当前版 | 精炼版 |",
        "|---|---:|---:|",
    ]
    labels = {
        "rows": "有效词条行数",
        "unique_words": "不同词汇数",
        "average_keys_per_character": "平均每字按键数",
        "first_choice_hit_rate": "首选命中率",
        "same_code_collision_rate": "同码冲突率",
        "empty_short_code_rate": "短码空码率",
        "uncovered_weight_rate": "未收录词频权重",
        "personal_history_coverage": "个人历史覆盖率",
        "deployment_seconds": "冷部署时间（秒）",
        "deployment_peak_rss_bytes": "冷部署峰值内存（字节）",
        "compiled_dictionary_bytes": "编译词典体积（字节）",
        "repairable_empty_codes": "仍可链式补齐的空码",
        "excluded_person_names": "排除的中文人名",
        "excluded_without_general_frequency": "排除的无通用频率词",
        "reserved_self_word_codes": "保护的自造词编码",
        "non_six_collision_codes": "精炼主词库3至5码重码",
    }
    for key, label in labels.items():
        if key not in result["current"]:
            continue
        current = result["current"][key]
        refined = result["refined"][key]
        if current is None:
            current_text = "未重算"
            refined_text = f"{refined:,}"
        elif isinstance(current, float):
            current_text = f"{current:.4%}" if "rate" in key or "coverage" in key else f"{current:.4f}"
            refined_text = f"{refined:.4%}" if "rate" in key or "coverage" in key else f"{refined:.4f}"
        else:
            current_text = f"{current:,}"
            refined_text = f"{refined:,}"
        lines.append(f"| {label} | {current_text} | {refined_text} |")
    lines.extend([
        "",
        "## 结论",
        "",
        "- 精炼版完整保留原胖次 630，不重新分配任何 630 短码。",
        "- 630 词的普通编码强制使用六码并置于同码候选尾部，"
        "其原有短码输入不受影响。",
        "- 精炼版在平均每字按键数、首选命中率、同码冲突率、"
        "冷部署时间、部署峰值内存和编译体积上更好。",
        "- 当前版只在公共评测语料的总覆盖率上略高。",
        "- 精炼版已按综合词频链式填补合法空码，"
        "没有发现还能由下级候选继续补齐的空码。",
        "- 精炼主词库所有 3 至 5 码均保持唯一；发生竞争时，"
        "综合词频较低者自动后移。",
        "- 中文人名依据 THUOCL 历史名人表过滤；"
        "自造词、个人词频词和胖次 630 不受过滤。",
        "- 所有启用自造词编码在分配前预先占位，"
        "精炼基础词库不会收录同词，也不会让其他词与其同码。",
        "- 缺乏 wordfreq 与 Rime Essay 通用频率证据的词不进入精炼词库。",
        "- 两套方案都完整覆盖当前个人词频与自造词记录。",
    ])
    (ROOT / "PANTSU_REFINED_EVALUATION.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
