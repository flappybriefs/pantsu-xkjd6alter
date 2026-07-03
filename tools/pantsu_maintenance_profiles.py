#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SchemeProfile:
    key: str
    label: str
    dictionaries: tuple[str, ...]
    candidate_order_file: str
    phone_files: tuple[str, ...]
    obsolete_phone_files: tuple[str, ...]


COMMON_STATE_FILES = (
    "pantsu_overrides.tsv",
    "pantsu_self_words.tsv",
    "pantsu_self_words_ops.tsv",
    "pantsu_usage.tsv",
    "pantsu_usage_events.tsv",
    "pantsu.user.dict.yaml",
    "pantsu.zzc.dict.yaml",
    "pantsu_history.tsv",
)

CACHE_STATE_FILES = (
    "pantsu_dynamic_roots.tsv",
    "build/pantsu_dynamic_candidates.tsv",
)

SCHEME_PROFILES = {
    "pantsu": SchemeProfile(
        key="pantsu",
        label="胖次键道",
        candidate_order_file="pantsu_candidate_order.tsv",
        phone_files=(
            "default.custom.yaml",
            "hamster.yaml",
            "pantsu.schema.yaml",
            "pantsu.extended.dict.yaml",
            "pantsu.core.dict.yaml",
            "pantsu.danzi.dict.yaml",
            "pantsu.cizu.dict.yaml",
        ),
        obsolete_phone_files=(
            "pantsu_refined.schema.yaml",
            "pantsu.refined.core.dict.yaml",
            "pantsu.refined.dict.yaml",
            "pantsu.refined.extended.dict.yaml",
            "pantsu_refined_candidate_order.tsv",
            "pantsu.waigua.dict.yaml",
        ),
        dictionaries=(
            "pantsu.core.dict.yaml",
            "pantsu.danzi.dict.yaml",
            "pantsu.cizu.dict.yaml",
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


def active_profile() -> SchemeProfile:
    return SCHEME_PROFILES["pantsu"]
