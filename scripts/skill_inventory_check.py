#!/usr/bin/env python3
"""
skill_inventory_check.py — 全部 skill 的一致性清點(唯讀;不改任何檔)

拆成一文體一支之後,一致性不能再靠人記。查六件事:

  1. 每支 skill 的 SKILL.md 存在,且 `name:` 與目錄名一致
  2. `PLUGINS` 打包的每一支 skill 都存在
  3. 每支 skill 都被**至少一個 plugin 打包**——沒被打包的 skill 裝不到,等於不存在
  4. 前門若在 SKILL.md 裡叫人跑某支引擎的 lint,該引擎**必須在同一個 plugin 的打包清單裡**
     (否則只裝前門的人手上沒有那支腳本)
  5. 沒有自己 lint 腳本的 skill,SKILL.md **必須有「本支沒有 lint」的明標節**
     ——KN-001 的第二條路;缺這一節就是空頭規則
  6. `plugins/` 底下的**目錄集合** == `PLUGINS` 的鍵集合 == marketplace 的 plugin 名單
     ——三者必須完全相等(CHG-20260814-02)

版本三處同步由 `plugins/catalog_check.py` 負責,本檔不重複。

**第 6 項為什麼在這裡而不是在 `catalog_check.py`**:方向相反。既有的三道閘全部是
**名冊 → 磁碟**(catalog_check 走訪 marketplace 條目、build_suite 與本檔第 2 項走訪
`PLUGINS`),所以**不在任何名冊裡的目錄,三道閘都走不到**。`plugins/bizdoc/` 與
`plugins/techdoc/` 就是這樣在 main 上活了四天:被 git 追蹤、不被 build_suite 同步、
與單一真相分岔 11 個檔(含半形標點的夾具),而 CI 全綠。第 6 項補的是
**磁碟 → 名冊**這一條;本檔的職責是「齊備與可達」,這正好是它。

**紅燈可達內建**:`--self-test` 拿嵌在檔案裡的好壞兩份樣本各跑一次判定,
好的要過、壞的要被抓。零失敗與引擎壞掉看起來一樣,所以這一步不能省。

用法:
  python3 scripts/skill_inventory_check.py --repo .
  python3 scripts/skill_inventory_check.py --self-test

退出碼:0 全數一致 | 1 有不一致 | 2 環境/參數錯誤
"""
from __future__ import annotations
import argparse
import ast
import json
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

NAME_RE = re.compile(r"^name:\s*(\S+)\s*$", re.M)
NO_LINT_RE = re.compile(r"^##\s*.*本支沒有\s*lint", re.M)
ENGINE_CALL_RE = re.compile(r"skills/([a-z-]+)/scripts/[a-z_]+\.py")


def load_plugins(repo: Path) -> dict[str, tuple[str, ...]]:
    """從 build_suite.py 的 PLUGINS 字面值讀,不 import——不執行別人的程式碼。"""
    src = (repo / "plugins" / "build_suite.py").read_text(encoding="utf-8")
    m = re.search(r"PLUGINS = (\{.*?\n\})", src, re.S)
    if not m:
        raise ValueError("build_suite.py 裡找不到 PLUGINS")
    return ast.literal_eval(m.group(1))


def load_market_names(repo: Path) -> set[str]:
    """marketplace 的 plugin 名單。"""
    mk = json.loads((repo / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    return {str(e.get("name", "")) for e in mk.get("plugins", [])}


def plugin_dirs_on_disk(repo: Path) -> set[str]:
    """`plugins/` 底下的目錄名。只走訪目錄——build_suite.py 與 catalog_check.py
    是工具檔,不是 plugin,不參與判定。"""
    base = repo / "plugins"
    return {p.name for p in base.iterdir() if p.is_dir() and p.name != "__pycache__"}


def catalog_consistency(on_disk: set[str], packaged: set[str], market: set[str]) -> list[str]:
    """三向相等的判定。**刻意寫成對三個集合的純函式**,self-test 才餵得進合成輸入。

    不寫成單向包含(`on_disk ⊆ market`):單向擋得住孤兒目錄,擋不住反向的
    「名冊有、磁碟沒有」。這次的洞就是單向造成的。
    """
    problems: list[str] = []
    for name in sorted(on_disk | packaged | market):
        where = (name in on_disk, name in packaged, name in market)
        if all(where):
            continue
        d, p, m = where
        if d and not p and not m:
            problems.append(
                f"`plugins/{name}/` 兩份名冊都沒有它——**孤兒目錄**。被 git 追蹤但 "
                f"build_suite 不同步、治理閘掃不到,必然與 skills/ 分岔。要嘛登記進 "
                f"PLUGINS 與 marketplace,要嘛從 plugins/ 底下移走")
            continue
        missing = ", ".join(n for n, ok in
                            (("`plugins/` 目錄", d), ("PLUGINS", p), ("marketplace 名冊", m))
                            if not ok)
        present = ", ".join(n for n, ok in
                            (("`plugins/` 目錄", d), ("PLUGINS", p), ("marketplace 名冊", m))
                            if ok)
        problems.append(f"plugin「{name}」只在 {present},缺 {missing}——三者必須相等")
    return problems


def skill_name(skill_md: Path) -> str | None:
    m = NAME_RE.search(skill_md.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def has_own_lint(repo: Path, skill: str) -> bool:
    return any((repo / "skills" / skill / "scripts").glob("*.py"))


def engines_referenced(text: str, own: str) -> set[str]:
    return {g for g in ENGINE_CALL_RE.findall(text) if g != own}


def check(repo: Path) -> list[str]:
    problems: list[str] = []
    plugins = load_plugins(repo)
    skills_dir = repo / "skills"
    on_disk = {p.name for p in skills_dir.iterdir() if p.is_dir()}
    packaged = {s for tup in plugins.values() for s in tup}

    for skill in sorted(on_disk):
        md = skills_dir / skill / "SKILL.md"
        if not md.is_file():
            problems.append(f"skill「{skill}」缺 SKILL.md")
            continue
        nm = skill_name(md)
        if nm != skill:
            problems.append(f"skill「{skill}」的 SKILL.md name={nm},與目錄名不符")
        if skill not in packaged:
            problems.append(f"skill「{skill}」沒有任何 plugin 打包它——裝不到,等於不存在")
        if not has_own_lint(repo, skill) and not NO_LINT_RE.search(md.read_text(encoding="utf-8")):
            text = md.read_text(encoding="utf-8")
            if not engines_referenced(text, skill):
                problems.append(
                    f"skill「{skill}」沒有自己的 lint,也沒有指向任何引擎,"
                    f"卻缺少「本支沒有 lint」的明標節——空頭規則(KN-001)")

    for plug, tup in sorted(plugins.items()):
        for s in tup:
            if s not in on_disk:
                problems.append(f"plugin「{plug}」打包了不存在的 skill「{s}」")
        front = tup[0]
        md = skills_dir / front / "SKILL.md"
        if md.is_file():
            for eng in engines_referenced(md.read_text(encoding="utf-8"), front):
                if eng not in tup:
                    problems.append(
                        f"plugin「{plug}」的前門叫人跑 `{eng}` 的 lint,"
                        f"但打包清單沒有帶上它——只裝這個 plugin 的人跑不動")

    problems += catalog_consistency(plugin_dirs_on_disk(repo), set(plugins),
                                    load_market_names(repo))
    return problems


GOOD_MD = """---
name: demo
description: >
  示範。
metadata:
  version: 1.0.0
---

## ⚠ 本支沒有 lint,規則靠人判斷

明標在此。
"""
BAD_MD = GOOD_MD.replace("## ⚠ 本支沒有 lint,規則靠人判斷", "## 規則")


# 第 6 項的合成樣本。三向相等要過;三種偏離各要被抓——只驗「相等會過」等於沒驗。
TRIO_OK = ({"official", "press"}, {"official", "press"}, {"official", "press"})
TRIO_CASES = [
    ("孤兒目錄(磁碟有、兩份名冊都沒有)",
     ({"official", "press", "bizdoc"}, {"official", "press"}, {"official", "press"})),
    ("名冊有、磁碟沒有",
     ({"official"}, {"official", "press"}, {"official", "press"})),
    ("兩份名冊自己分岔(PLUGINS 有、marketplace 沒有)",
     ({"official", "press"}, {"official", "press"}, {"official"})),
]


def self_test() -> int:
    """紅燈可達:每一項判定的綠燈與紅燈都要各走一次。"""
    fails = []

    if not NO_LINT_RE.search(GOOD_MD):
        fails.append("好樣本(有明標節)竟然沒被認出來——判定過嚴")
    if NO_LINT_RE.search(BAD_MD):
        fails.append("壞樣本(拿掉明標節)竟然通過——**紅燈不可達,這道閘等於不存在**")

    if catalog_consistency(*TRIO_OK):
        fails.append("三向相等的樣本竟然被判為不一致——第 6 項判定過嚴,會誤殺")
    for label, trio in TRIO_CASES:
        if not catalog_consistency(*trio):
            fails.append(f"第 6 項:「{label}」竟然通過——**這個方向的紅燈不可達**")

    if fails:
        for f in fails:
            print(f"  ❌ {f}")
        return 1
    print("✅ self-test:明標節與三向相等(含三種偏離)的綠燈與紅燈皆可達")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="skill 清單一致性")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--self-test", action="store_true", help="只跑紅燈可達自檢")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    repo = Path(args.repo)
    if not (repo / "skills").is_dir():
        print(f"ERROR: {repo}/skills 不存在", file=sys.stderr)
        return 2
    try:
        problems = check(repo)
    except (ValueError, SyntaxError, OSError) as e:
        print(f"ERROR: 讀不到 PLUGINS 或 marketplace — {e}", file=sys.stderr)
        return 2

    plugins = load_plugins(repo)
    n_skill = len([p for p in (repo / "skills").iterdir() if p.is_dir()])
    engines = sorted({s for tup in plugins.values() for s in tup[1:]})
    n_dir = len(plugin_dirs_on_disk(repo))
    print(f"skill 清點 — {n_skill} 支 skill / {len(plugins)} 個 plugin"
          f"(磁碟上 {n_dir} 個目錄)/ 引擎 {len(engines)} 支({'、'.join(engines) or '無'})")
    if problems:
        print(f"\n✗ {len(problems)} 處不一致:")
        for p in problems:
            print(f"  {p}")
        return 1
    print("✅ 一致。注意:本閘查的是**齊備與可達**,查不了 SKILL.md 寫得對不對。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
