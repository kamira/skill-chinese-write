#!/usr/bin/env python3
"""
chg_diagram_gate.py — 中/高風險 CHG 必須附設計圖(唯讀;不改任何檔)

ai-sdlc 自 v1.21 起要求中/高風險的 CHG 附兩張圖:受影響區域的架構圖,以及本次變更的
流程圖。這條規則在本 repo 一直沒有任何機器在查——三張中風險 CHG 都有圖,純粹因為
寫的人記得畫。規則存在、沒有斷言,是 KN-001 的型樣;這支就是那條斷言。

判定順序(任何一關豁免就放行):
  1. Template: lite            → 豁免(記帳成本隨風險縮放)
  2. Skill 版本 < 1.21 或沒有欄位 → 豁免(**前瞻**,與 ai-sdlc 的 DIAGRAM_SINCE 一致)
  3. Risk 不是中/高             → 豁免
  4. Diagrams: skipped — <理由> → 具名跳過,放行並列出;**理由空白視同未宣告**
  5. 有 ## Design diagrams 節且節內有可辨識的圖 → 通過,否則擋下

「什麼算一張圖」不在本檔定義,從 skills/techdoc/assets/techdoc_rules.json 的
diagram_patterns 讀——同一個定義有兩個消費者,分成兩份必然分岔。

**只查圖存不存在,不查圖對不對。** 依賴方向畫反了本腳本看不出來,那正是要給人看的原因。

用法:
  python3 scripts/chg_diagram_gate.py --repo .
  python3 scripts/chg_diagram_gate.py --repo . --glob 'tests/fixtures/chg-gate/*.md'

退出碼:0 全數通過 | 1 有 CHG 缺圖 | 2 環境/參數錯誤
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

DIAGRAM_SINCE = (1, 21)
RULES_REL = "skills/techdoc/assets/techdoc_rules.json"
SECTION_RE = re.compile(r"^##\s+Design diagrams\s*$", re.M)
NEXT_H2_RE = re.compile(r"^##\s+", re.M)
# 中風險在本 repo 寫成「中」或 medium;lite 格式把 Risk 擠在 Date 那一行,兩種都要認。
RISK_RE = re.compile(r"Risk:\s*([^\s|]+)")
SKILL_RE = re.compile(r"^-\s*Skill:.*?v(\d+)\.(\d+)", re.M)
TEMPLATE_RE = re.compile(r"^-\s*Template:\s*(\S+)", re.M)
DIAGRAMS_RE = re.compile(r"^-\s*Diagrams:\s*(.*)$", re.M)
SKIP_RE = re.compile(r"skipped\s*[—\-–]\s*(.*)$")
HIGH_MED = {"中", "高", "medium", "high", "中風險", "高風險"}


def header_of(text: str) -> str:
    """標頭 = 第一個 ## 之前。避免內文提到 Risk: 時被誤讀成欄位。"""
    m = NEXT_H2_RE.search(text)
    return text[:m.start()] if m else text


def diagram_section(text: str) -> str | None:
    m = SECTION_RE.search(text)
    if not m:
        return None
    rest = text[m.end():]
    nxt = NEXT_H2_RE.search(rest)
    return rest[:nxt.start()] if nxt else rest


def judge(path: Path, rxs) -> tuple[str, str]:
    """回傳 (verdict, 說明)。verdict ∈ pass / exempt / skipped / fail。"""
    text = path.read_text(encoding="utf-8")
    head = header_of(text)

    t = TEMPLATE_RE.search(head)
    if t and t.group(1).lower() == "lite":
        return "exempt", "Template: lite"

    s = SKILL_RE.search(head)
    if not s:
        return "exempt", "沒有 Skill 欄位——視為 v1.21 之前,前瞻不追溯"
    ver = (int(s.group(1)), int(s.group(2)))
    if ver < DIAGRAM_SINCE:
        return "exempt", f"Skill v{ver[0]}.{ver[1]} < v1.21,前瞻不追溯"

    r = RISK_RE.search(head)
    risk = r.group(1) if r else ""
    if not any(risk.startswith(k) for k in HIGH_MED):
        return "exempt", f"Risk「{risk or '未標'}」不是中/高"

    d = DIAGRAMS_RE.search(head)
    if d:
        sk = SKIP_RE.search(d.group(1))
        if sk:
            reason = sk.group(1).strip().strip("<>` ")
            if reason:
                return "skipped", f"具名跳過:{reason}"
            return "fail", "Diagrams 宣告 skipped 但理由空白——空白的簽名不是簽名"

    body = diagram_section(text)
    if body is None:
        return "fail", "缺 `## Design diagrams` 節"
    if not any(rx.search(line) for line in body.split("\n") for rx in rxs):
        return "fail", "`## Design diagrams` 節裡沒有可辨識的圖(mermaid 區塊 / markdown 圖片 / ASCII 方框)"
    return "pass", "有圖"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="中/高風險 CHG 必須附設計圖")
    ap.add_argument("--repo", default=".", help="repo 根目錄")
    ap.add_argument("--glob", default="docs/writing/changes/CHG-*.md", help="要掃描的 CHG 樣式")
    args = ap.parse_args(argv)

    root = Path(args.repo)
    rules_path = root / RULES_REL
    if not rules_path.is_file():
        print(f"ERROR: 找不到圖的定義 {rules_path}", file=sys.stderr)
        return 2
    try:
        patterns = json.loads(rules_path.read_text(encoding="utf-8"))["diagram_patterns"]
    except (json.JSONDecodeError, KeyError) as e:
        print(f"ERROR: 讀不到 diagram_patterns — {e}", file=sys.stderr)
        return 2
    rxs = [re.compile(p) for p in patterns]

    files = sorted(root.glob(args.glob))
    if not files:
        # 掃到零份就回報「沒驗到」,不冒充通過(KN-004:判定不出來不等於沒問題)
        print(f"ERROR: {args.glob} 掃不到任何檔案——沒驗到不等於通過", file=sys.stderr)
        return 2

    checked, exempt, skipped, failed = [], [], [], []
    for f in files:
        verdict, why = judge(f, rxs)
        {"pass": checked, "exempt": exempt, "skipped": skipped, "fail": failed}[verdict].append((f, why))

    print(f"CHG 設計圖閘 — 掃描 {len(files)} 份")
    print(f"  真的檢查了 {len(checked)} 份 / 豁免 {len(exempt)} 份 / 具名跳過 {len(skipped)} 份")
    for f, why in skipped:
        print(f"  ⓘ {f.name}:{why}")
    if failed:
        print(f"\n✗ {len(failed)} 份缺設計圖:")
        for f, why in failed:
            print(f"  {f.name} — {why}")
        print("\n中/高風險的確認材料要看得懂才叫確認。散文描述模組關係最容易被點頭放過,"
              "也最容易錯——那正是圖存在的理由。")
        return 1
    print("\n✅ 通過。注意:本閘只查圖**存不存在**,查不了圖畫得對不對——那一半靠人。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
