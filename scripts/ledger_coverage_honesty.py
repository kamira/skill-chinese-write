#!/usr/bin/env python3
"""
ledger_coverage_honesty.py — `[15/19]` 只准宣稱它真的驗到的東西(唯讀;不改任何檔)

## 病灶

`.github/ci_local.sh` 第 [15/19] 步的標題寫「帳本完整性(CHG↔ACC + 結構同步 + secrets)」,
它呼叫隨身副本 `doc_integrity_check.py --repo .`。而在本 repo:

  · `check_chg_acc` 掃 `repo/docs/changes` —— **本 repo 的帳本在 `docs/writing/changes`**,
    45 張 CHG 一張都沒看過。A/B 實測:同一份壞 CHG(Status 宣稱已驗收而該 ACC 不存在)
    放真實位置 **綠**,放 `docs/changes` **紅**。差別只在目錄。
  · `check_structural_sync` **只在帶 `--staged` 時執行**,而第 [15/19] 步沒有帶。
  · `check_fields` / `check_recurrence_field` / `check_knowledge_bootstrap` 同樣寫死 `docs/changes`。
  · `check_entry_point` 用 `docs/changes` 存廢判「受不受治理」,於是把本 repo 判成**未受治理**。

三個宣稱裡只有 secrets 是真的。**而回報「沒問題」比回報「有問題」更難被發現:
沒有人會去追查一個綠燈。**

上游早就修了(`ledger_roots()`,其 docstring 自述「同一個錯誤修過兩次,這是第三次」),
本 repo 的隨身副本停在修好之前;依 AGENTS.md 第 4 條不得就地改,同步案記於 `BL-034`。

## 本閘做什麼

**不修覆蓋率,修宣稱**——讓 `[15/19]` 的標題不得說出它沒驗到的東西,並把空轉清單釘死。

  1. 標題宣稱:`[15/19]` 那一行不得含 `CHG↔ACC` / `結構同步` / `欄位` 三個 token。
     想說回大話,先讓這格紅。
  2. 空轉清單:`EXPECT_VACUOUS` 具名八格,**一多一少都紅**——名單腐爛成裝飾是本 repo
     記過的形狀(`BL-015`)。清單分兩類,成因不同,不得混為一談:路徑修好只救得回前四格。
  3. 機制自證:`--self-test` 造出 `docs/changes` 與一份壞 CHG,斷言 A/B 兩側都成立——
     真實佈局綠、`docs/changes` 紅。否則本閘自己的前提就沒有證據。

**本閘不宣稱**:CHG↔ACC 配對已受驗證。那件事沒有任何機器在看,記於 `BL-034`。

用法:
  python3 scripts/ledger_coverage_honesty.py --repo .
  python3 scripts/ledger_coverage_honesty.py --self-test

退出碼:0 宣稱與覆蓋一致 | 1 宣稱超出覆蓋,或空轉清單漂了 | 2 環境/參數錯誤
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

STEP_LINE = re.compile(r'^echo "\[15/19\](.*)"$', re.M)
# 宣稱 token:出現在標題裡就是說了大話。secrets 不在名單內——那一格是真的。
FORBIDDEN_CLAIMS = ("CHG↔ACC", "結構同步", "欄位")

# 空轉八格,**分兩類**:成因不同,處置也不同(路徑修好只救得回前四格)。
EXPECT_VACUOUS = {
    "路徑寫死": ("check_chg_acc", "check_fields",
                 "check_recurrence_field", "check_knowledge_bootstrap"),
    "標的物在本 repo 不存在": ("check_knowledge_entries", "check_knowledge_index",
                               "check_regression_pointers", "check_coverage_registry"),
}
MISJUDGED = ("check_entry_point",)      # 不是空轉,是把本 repo 判成未受治理
REALLY_RUNS = ("check_secrets",)
HARDCODED_MARK = '"docs" / "changes"'


def claims_of(ci_local: str) -> str | None:
    m = STEP_LINE.search(ci_local)
    return m.group(1) if m else None


def check(ci_local: str, doc_integrity: str) -> list[str]:
    """純函式:吃文字、吐問題。**吃文字是為了讓 self-test 打得到每一端。**"""
    bad: list[str] = []
    title = claims_of(ci_local)
    if title is None:
        return ["找不到 `[15/19]` 那一行——本閘失去標的,而找不到不等於沒問題"]
    for tok in FORBIDDEN_CLAIMS:
        if tok in title:
            bad.append("`[15/19]` 的標題宣稱「" + tok + "」,而它在本 repo 沒有驗到"
                       "——想說回大話,先修覆蓋(BL-034)")

    named = {n for group in EXPECT_VACUOUS.values() for n in group} | set(MISJUDGED)
    # 名單雙向嚴格:具名了不存在的函式 → 腐爛;寫死 docs/changes 而沒具名 → 偷渡
    for n in sorted(named):
        if "def " + n + "(" not in doc_integrity:
            bad.append("EXPECT_VACUOUS/MISJUDGED 具名了不存在的 `" + n + "`"
                       "——名單腐爛成裝飾(BL-015 的形狀)")
    for n in sorted(set(re.findall(r"def (check_\w+)\(", doc_integrity))):
        start = doc_integrity.index("def " + n + "(")
        nxt = doc_integrity.find("\ndef ", start + 1)
        body = doc_integrity[start:nxt if nxt > 0 else len(doc_integrity)]
        if HARDCODED_MARK in body and n not in named:
            bad.append("`" + n + "` 也寫死 `docs/changes` 卻不在名單裡"
                       "——名單漏了一格,而漏掉的那格會靜默空轉")
    return bad


_FAKE_DI = "".join(
    "def " + n + "(repo):\n    x = repo / " + HARDCODED_MARK + "\n"
    for n in ("check_chg_acc", "check_fields", "check_recurrence_field",
              "check_knowledge_bootstrap", "check_entry_point")
) + "".join(
    "def " + n + "(repo):\n    pass\n"
    for n in ("check_knowledge_entries", "check_knowledge_index",
              "check_regression_pointers", "check_coverage_registry", "check_secrets")
)

_OK_TITLE = 'echo "[15/19] 帳本完整性(**只驗到 secrets**;其餘見 BL-034)"\n'


def self_test() -> int:
    import tempfile
    fails: list[str] = []

    if check(_OK_TITLE, _FAKE_DI):
        fails.append("綠端不綠:" + str(check(_OK_TITLE, _FAKE_DI)))
    # 標題說回大話 → 三個 token 各一個紅端,全由綠端突變產生
    loud = _OK_TITLE.replace("**只驗到 secrets**", "CHG↔ACC + 結構同步 + 欄位", 1)
    for tok in FORBIDDEN_CLAIMS:
        if not any(tok in g for g in check(loud, _FAKE_DI)):
            fails.append("紅端「標題宣稱 " + tok + "」不可達")
    if not any("找不到" in g for g in check("echo 別的\n", _FAKE_DI)):
        fails.append("紅端「找不到 [15/19]」不可達")
    rotted = _FAKE_DI.replace("def check_chg_acc(", "def gone(", 1)
    if not any("腐爛" in g for g in check(_OK_TITLE, rotted)):
        fails.append("紅端「名單具名了不存在的函式」不可達")
    smuggled = _FAKE_DI + "def check_new_thing(repo):\n    x = repo / " + HARDCODED_MARK + "\n"
    if not any("名單漏了一格" in g for g in check(_OK_TITLE, smuggled)):
        fails.append("紅端「新的寫死格沒進名單」不可達")

    # 機制自證:A/B 兩側都要成立,否則本閘的整個前提沒有證據
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                           / "tools" / "autopilot" / "scripts"))
    try:
        import doc_integrity_check as dic
    except Exception as e:                                  # pragma: no cover
        fails.append("機制自證:匯入隨身副本失敗 " + repr(e)[:60])
    else:
        broken = ("# CHG-99999999-99 — x\n\n- Project: x\n\n## Status\n\n"
                  "已驗收 — ACC-99999999-99。\n")
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            (r / "docs" / "writing" / "changes").mkdir(parents=True)
            (r / "docs" / "writing" / "changes" / "CHG-99999999-99.md").write_text(
                broken, encoding="utf-8")
            if dic.check_chg_acc(r):
                fails.append("機制自證:壞 CHG 放**本 repo 的真實佈局**竟然被擋了"
                             "——那本案的前提就不成立,請重新量")
            (r / "docs" / "changes").mkdir(parents=True)
            (r / "docs" / "changes" / "CHG-99999999-99.md").write_text(
                broken, encoding="utf-8")
            if not dic.check_chg_acc(r):
                fails.append("機制自證:壞 CHG 放 `docs/changes` 也沒被擋"
                             "——**空轉偵測器本身是恆真的**,本閘沒有任何證據")
    if fails:
        for f in fails:
            print("  ❌ " + f)
        print("\n✗ self-test 未通過。")
        return 1
    print("✅ self-test:標題三個宣稱 token + 找不到標的 + 名單雙向嚴格,五個紅端"
          "皆由綠端突變產生;機制自證確認 A/B 兩側(真實佈局綠 / docs-changes 紅)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="[15/19] 只准宣稱它真的驗到的東西")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()

    root = Path(args.repo)
    ci = root / ".github" / "ci_local.sh"
    di = root / "tools" / "autopilot" / "scripts" / "doc_integrity_check.py"
    for f in (ci, di):
        if not f.is_file():
            print("ERROR: 找不到 " + str(f) + "——沒驗到不等於通過", file=sys.stderr)
            return 2
    bad = check(ci.read_text(encoding="utf-8"), di.read_text(encoding="utf-8"))
    if bad:
        print("✗ 宣稱與覆蓋不一致 " + str(len(bad)) + " 項:")
        for b in bad:
            print("  " + b)
        return 1
    n_vac = sum(len(v) for v in EXPECT_VACUOUS.values())
    print("✅ `[15/19]` 的宣稱不超出覆蓋。具名空轉 " + str(n_vac) + " 格("
          + " / ".join(k + ":" + str(len(v)) for k, v in EXPECT_VACUOUS.items())
          + ")、誤判 " + str(len(MISJUDGED)) + " 格、真的在跑 "
          + str(len(REALLY_RUNS)) + " 格。")
    print("   **本閘不宣稱 CHG↔ACC 配對已受驗證**——那件事沒有任何機器在看,記於 BL-034。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
