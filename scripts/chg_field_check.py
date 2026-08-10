#!/usr/bin/env python3
"""
chg_field_check.py — CHG 標頭欄位不得留佔位字串(唯讀;不改任何檔)

`doc_integrity_check.py` 查 CHG↔ACC 配對、結構同步、欄位**存在**與 secrets,
但**不查欄位有沒有真的填**。兩張 CHG 的 `Commit/PR:` 停在「<close-out 回填>」
一路綠燈進了 main,是用眼睛抓到的。

模板要求 close-out 時回填,而斷言只驗那一行在不在——KN-001 的同一個型樣,
這次落在治理模板自己的欄位上。這支就是那條斷言。

它為什麼不寫進 `tools/autopilot/scripts/doc_integrity_check.py`:那是
`kamira/skill-ai-sdlc-autopilot` 的**隨身副本**,就地改會讓漂移檢查轉紅
(AGENTS.md 第 4 條)。要改得送回上游再同步下來,所以本 repo 自己的斷言
放在 `scripts/`。

判定:標頭(第一個 `##` 之前)的 `- 欄位:` 值若整個被 `<...>` 包住,即違規。
`<close-out 回填>`、`<hash / PR link>`、`<change title>` 都是這一類。

**紅燈可達內建**:`--self-test` 拿嵌在檔內的好壞兩份標頭各跑一次。

用法:
  python3 scripts/chg_field_check.py --repo .
  python3 scripts/chg_field_check.py --self-test

退出碼:0 全數已填 | 1 有佔位字串 | 2 環境/參數錯誤
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

FIELD = re.compile(r"^-\s*([^:：]+)[:：]\s*(.*)$", re.M)
NEXT_H2 = re.compile(r"^##\s+", re.M)
# 值整個被角括號包住 = 還是模板裡的佔位字串。
PLACEHOLDER = re.compile(r"^<[^>]*>$")


def header_of(text: str) -> str:
    m = NEXT_H2.search(text)
    return text[:m.start()] if m else text


def check_text(text: str) -> list[tuple[str, str]]:
    """回傳 [(欄位, 佔位值)]。"""
    out = []
    for m in FIELD.finditer(header_of(text)):
        name, value = m.group(1).strip(), m.group(2).strip()
        if PLACEHOLDER.match(value):
            out.append((name, value))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CHG 欄位不得留佔位字串")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--glob", default="docs/writing/changes/CHG-*.md")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        good = "# X\n\n- Commit/PR: https://example.com/pull/1\n- Risk: 低\n\n## 內文\n"
        bad = "# X\n\n- Commit/PR: <close-out 回填>\n- Risk: 低\n\n## 內文\n"
        fails = []
        if check_text(good):
            fails.append("好樣本被誤判為有佔位字串")
        if not check_text(bad):
            fails.append("壞樣本(Commit/PR 留佔位)竟然通過——**紅燈不可達**")
        if fails:
            for f in fails:
                print(f"  ❌ {f}")
            return 1
        print("✅ self-test:佔位字串的判定綠燈與紅燈皆可達")
        return 0

    root = Path(args.repo)
    files = sorted(root.glob(args.glob))
    if not files:
        print(f"ERROR: {args.glob} 掃不到任何檔案——沒驗到不等於通過", file=sys.stderr)
        return 2

    problems = []
    for f in files:
        for name, value in check_text(f.read_text(encoding="utf-8")):
            problems.append((f.name, name, value))

    print(f"CHG 欄位檢查 — 掃描 {len(files)} 份")
    if problems:
        print(f"\n✗ {len(problems)} 個欄位還留著佔位字串:")
        for fn, name, value in problems:
            print(f"  {fn}  {name}: {value}")
        print("\n模板要求 close-out 時回填。空著的欄位與「沒做這一步」在稽核時長得一樣。")
        return 1
    print("✅ 所有標頭欄位都已填。注意:本閘查的是**有沒有填**,查不了填得對不對。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
