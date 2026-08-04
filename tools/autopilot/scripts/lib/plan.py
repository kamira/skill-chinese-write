#!/usr/bin/env python3
"""計畫解析:CHG markdown → task 清單、風險、CHG id。無 LLM、stdlib-only。"""
from __future__ import annotations
import re
from pathlib import Path

TASK_RE = re.compile(r"^- \[(?P<tick>[ xX])\] (?P<tid>T\d+)\. (?P<title>.+?)\s*$")
IFACE_RE = re.compile(r"^\s+-\s*interfaces:\s*\S")
TEST_RE = re.compile(r"^\s+-\s*test:\s*(?P<v>\S.*)$")
GC_RE = re.compile(r"^###\s*Global Constraints", re.MULTILINE)
AOP_RE = re.compile(r"^###\s*Acceptance operation", re.MULTILINE)
# 行為規格(CHG-20260803-02 T5):CHG 的使用者故事是驗收條件的第一順位來源(ai-sdlc v1.19),
# 但那一直只是散文。本節宣告對應的 .feature 路徑,讓故事變成可重跑的斷言。
BSPEC_RE = re.compile(r"^###\s*Behaviour spec", re.MULTILINE)
BSPEC_PATH_RE = re.compile(r"^-\s*feature:\s*(\S+)", re.MULTILINE)
# 前瞻適用起點:比照 ai-sdlc「重複性檢查」欄的先例,不追殺既有 CHG
AUTOPILOT_VER_RE = re.compile(r"ai-sdlc-autopilot\s*v(\d+)\.(\d+)", re.IGNORECASE)
BSPEC_SINCE = (1, 5)
DOCS_ONLY_RE = re.compile(r"Acceptance-operation:\s*n/?a|docs-only", re.IGNORECASE)
RISK_RE = re.compile(r"(風險分級|Risk)\s*[::]\s*[^\n]{0,40}?(高|high|中|medium|低|low)", re.IGNORECASE)
CHG_ID_RE = re.compile(r"CHG-\d{8}-\d+")
PERM_RE = re.compile(r"permanent-halt:\s*([\w-]+)")
AUTONOMY_HALT_RE = re.compile(r"^-\s*Autonomy\s*[::].*halt", re.MULTILINE | re.IGNORECASE)
VERDICT_RE = re.compile(
    r"\[task-review\]\s*(?:T\d+|branch)\s*\|\s*spec:\s*(pass|fail|cannot-verify)\s*\|\s*quality:\s*(pass|fail)",
    re.IGNORECASE)


def read_chg(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def chg_id_of(text: str, fallback: str = "?") -> str:
    m = CHG_ID_RE.search(text)
    return m.group(0) if m else fallback


def risk_of(text: str) -> str:
    m = RISK_RE.search(text)
    if not m:
        return "high"  # 查無=保守
    v = m.group(2).lower()
    return {"高": "high", "中": "medium", "低": "low"}.get(v, v)


def parse_tasks(text: str):
    """回傳 (problems, tasks);task = {tid,title,ticked,has_iface,has_test,line_no}"""
    problems, tasks = [], []
    lines = text.splitlines()
    if not GC_RE.search(text):
        problems.append("缺「### Global Constraints」節——全域約束是 task 簡報自包含的前提")
    for i, line in enumerate(lines):
        m = TASK_RE.match(line)
        if not m:
            continue
        # 前瞻視窗必須在**下一個 task 開始時截斷**(CHG-20260803-01 T9)。
        # 原本固定取 5 行,會越界讀到下一個 task 的子行——缺 `interfaces:` 或 `test:` 的 task
        # 只要後面那個 task 有,就能借到它的行而通過 plan-check。即這道閘可以被無聲地繞過,
        # 而它是整個 autopilot 的第一道閘。
        block = []
        for l in lines[i + 1:i + 6]:
            if TASK_RE.match(l):
                break
            block.append(l)
        sub = [l for l in block if l.startswith((" ", "\t")) and l.strip().startswith("-")]
        tasks.append({
            "tid": m.group("tid"), "title": m.group("title"),
            "ticked": m.group("tick").lower() == "x", "line_no": i,
            "has_iface": any(IFACE_RE.match(l) for l in sub),
            "has_test": any(TEST_RE.match(l) for l in sub),
        })
    if not tasks:
        problems.append("找不到任何 task(格式:- [ ] T1. <標題>)")
    for t in tasks:
        if not t["has_iface"]:
            problems.append(f"{t['tid']} 缺 interfaces: 行(consumes/produces)")
        if not t["has_test"]:
            problems.append(f"{t['tid']} 缺 test: 行(指令或可斷言條件)")
    nums = [int(str(t["tid"])[1:]) for t in tasks]
    if nums != list(range(1, len(nums) + 1)):
        problems.append(f"task 編號須 T1..T{len(nums)} 連續,實得 {[t['tid'] for t in tasks]}")
    return problems, tasks


def bspec_required(text: str) -> bool:
    """本 CHG 是否需要行為規格:程式類 + Skill ≥ v1.5.0(前瞻適用)。"""
    if DOCS_ONLY_RE.search(text):
        return False
    m = AUTOPILOT_VER_RE.search(text)
    if m is None:
        return False
    # 明確早退而不是 `bool(m) and m.group(...)`:後者在執行期正確,但型別上
    # narrow 不掉,於是每個這樣寫的檔案都得欠一筆基線豁免(CHG-20260804-09)。
    return (int(m.group(1)), int(m.group(2))) >= BSPEC_SINCE


def bspec_paths(text: str) -> list[str]:
    m = BSPEC_RE.search(text)
    if not m:
        return []
    seg = text[m.start():]
    nxt = re.search(r"^###\s", seg[3:], re.MULTILINE)
    if nxt:
        seg = seg[:nxt.start() + 3]
    return BSPEC_PATH_RE.findall(seg)


def tick_task(chg_path: Path, tid: str) -> None:
    lines = read_chg(chg_path).splitlines(keepends=True)
    for i, line in enumerate(lines):
        m = TASK_RE.match(line.rstrip("\n"))
        if m and m.group("tid") == tid:
            lines[i] = line.replace("- [ ]", "- [x]", 1)
            break
    Path(chg_path).write_text("".join(lines), encoding="utf-8")
