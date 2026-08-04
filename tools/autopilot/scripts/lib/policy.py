#!/usr/bin/env python3
"""停點政策:永遠停點(硬編碼)、風險×階段矩陣、Autonomy 加嚴。治理語意錨定 ai-sdlc autonomy.md。"""
from __future__ import annotations
import json
from pathlib import Path

from .plan import AUTONOMY_HALT_RE

# 永遠停點:硬編碼——任何設定檔不可移除或放寬
PERMANENT_HALTS = ("irreversible-delete", "payments", "prod-migration", "security-boundary")
STAGES = ("confirm_gate", "task_review", "operational_verify", "acceptance", "pr", "merge")
ACTIONS = {"auto", "confirm", "halt", "halt_independent"}
# medium 的 merge 由 auto 收緊為 halt(CHG-20260803-02 T5)。
# 原值與 ai-sdlc 的 halt_policy.json(before_merge_or_release/medium = halt)矛盾——
# drive 層比治理層寬鬆,等同讓中風險變更繞過治理層的合併停點。本 skill 自己的
# 「tighten only」與「讀 ai-sdlc、不修改它」都蘊含 drive 層不得放寬。
# 由 features/halt_policy.feature 的跨層場景持續把關,再漂移就會紅。
DEFAULT_POLICY = {
    "low":    {"confirm_gate": "auto",    "task_review": "auto", "operational_verify": "auto", "acceptance": "auto",             "pr": "auto", "merge": "auto"},
    "medium": {"confirm_gate": "confirm", "task_review": "auto", "operational_verify": "auto", "acceptance": "auto",             "pr": "auto", "merge": "halt"},
    "high":   {"confirm_gate": "halt",    "task_review": "auto", "operational_verify": "halt", "acceptance": "halt_independent", "pr": "auto", "merge": "halt"},
}


def load_policy(path):
    """載入停點矩陣;驗證值域,且 permanent_halts 不可縮減(硬清單以程式碼為準)。"""
    matrix = DEFAULT_POLICY
    if path:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        cfg_perm = data.get("permanent_halts")
        if cfg_perm is not None and not set(PERMANENT_HALTS) <= set(cfg_perm):
            raise ValueError("policy 不得縮減 permanent_halts(硬清單:%s)" % ", ".join(PERMANENT_HALTS))
        matrix = data.get("defaults", matrix)
    for risk, stages in matrix.items():
        for st, act in stages.items():
            if st not in STAGES or act not in ACTIONS:
                raise ValueError(f"policy 值域錯誤:{risk}.{st}={act}")
    return matrix


def stage_action(matrix, risk: str, stage: str, chg_text: str) -> str:
    act = matrix.get(risk, matrix["high"]).get(stage, "halt")
    if AUTONOMY_HALT_RE.search(chg_text) and stage in ("confirm_gate", "merge"):
        act = "halt"  # Autonomy 欄只准加嚴
    return act
