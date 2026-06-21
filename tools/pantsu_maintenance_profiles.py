#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SchemeProfile:
    key: str
    label: str
    dictionaries: tuple[str, ...]
    candidate_order_file: str


COMMON_STATE_FILES = (
    "pantsu_overrides.tsv",
    "pantsu_self_words.tsv",
    "pantsu_usage.tsv",
    "pantsu_usage_events.tsv",
    "pantsu.user.dict.yaml",
    "pantsu.zzc.dict.yaml",
    "pantsu_history.tsv",
)

SCHEME_PROFILES = {
    "pantsu": SchemeProfile(
        key="pantsu",
        label="胖次键道",
        candidate_order_file="pantsu_candidate_order.tsv",
        dictionaries=(
            "pantsu.core.dict.yaml",
            "pantsu.danzi.dict.yaml",
            "pantsu.cizu.dict.yaml",
            "pantsu.temp.dict.yaml",
            "pantsu.user.dict.yaml",
            "pantsu.zzc.dict.yaml",
            "pantsu.waigua.dict.yaml",
        ),
    ),
    "pantsu_refined": SchemeProfile(
        key="pantsu_refined",
        label="胖次键道·精炼版",
        candidate_order_file="pantsu_refined_candidate_order.tsv",
        dictionaries=(
            "pantsu.refined.core.dict.yaml",
            "pantsu.danzi.dict.yaml",
            "pantsu.refined.dict.yaml",
            "pantsu.temp.dict.yaml",
            "pantsu.user.dict.yaml",
            "pantsu.zzc.dict.yaml",
        ),
    ),
}

STATE_FILES = tuple(dict.fromkeys((
    *COMMON_STATE_FILES,
    *(profile.candidate_order_file for profile in SCHEME_PROFILES.values()),
)))


def selected_profiles(name: str = "all") -> tuple[SchemeProfile, ...]:
    if name == "all":
        return tuple(SCHEME_PROFILES.values())
    try:
        return (SCHEME_PROFILES[name],)
    except KeyError as exc:
        choices = "、".join(["all", *SCHEME_PROFILES])
        raise ValueError(f"未知方案：{name}；可选：{choices}") from exc


def profiles_for_dictionary(name: str) -> tuple[SchemeProfile, ...]:
    return tuple(
        profile
        for profile in SCHEME_PROFILES.values()
        if name in profile.dictionaries
    )
