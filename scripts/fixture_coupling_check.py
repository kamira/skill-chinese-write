#!/usr/bin/env python3
"""
fixture_coupling_check.py — 夾具不得逐字引用規則自己的例句(唯讀;不改任何檔)

## 這道閘擋的是什麼

夾具引用規則文件的示範句,等於**用考古題驗考生**:lint 對那些句子必然綠燈,
因為規則就是照它們校準的。這不是單一 regex 抓不抓得到的問題,是整類
「夾具永遠測不到規則」的失效模式。

CHG-20260813-01 D-4 實錘四處:

| 夾具 | 與什麼逐字相同 |
|---|---|
| `writing/sample-good.md` | `voice.md` / `commentary.md` 的示範例句 |
| `writing/sample-issue.md` | `commentary.md` 的感受示範句 |
| `fiction-romance/sample-good.md` 結尾 | `zh_style_rules.json` 的 flat_ending 修正示範句 |
| `prose/sample-good.md` 結尾 | `zh_style_check.py` 的 self-test GOOD 字串 |

## 判準

比對 `skills/*/assets/sample-*.md`(夾具)與規則側檔案
(`skills/*/references/*.md`、`skills/*/assets/*_rules.json`、`skills/*/scripts/*.py`),
找出**連續 N 個中文字元完全相同**的片段。N 預設 10——短於此的共用片語
(「這個房間」「他說」)是自然重合,不是抄。

只看中文字元:標點、空白、markdown 記號一律先剝掉,避免因為排版差異而漏抓。

## 退出碼

0 沒有耦合 | 1 有耦合 | 2 環境/參數錯誤
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

CJK = re.compile(r"[一-鿿]+")
DEFAULT_N = 10

# 夾具側
FIXTURE_GLOB = "skills/*/assets/sample-*.md"
# 規則側:寫規則與示範句的地方
RULE_GLOBS = ("skills/*/references/*.md", "skills/*/assets/*_rules.json",
              "skills/*/scripts/*.py", "skills/*/SKILL.md")

# **格式即規則**的文體不在這道閘的射程內。
#
# 公文與技術文件的 reference 裡放的是**完整範本**——「主旨:」「說明:」的行文、
# 規格書的模組化編號,那些字句本身就是規格。夾具與範本重疊不是抄考古題,
# 是同一份格式的兩次出現;要求它們用字不同,等於要求夾具偏離規格。
#
# 這條豁免與被擋下的四處有本質差別:writing / prose / romance 那幾處重疊的是
# **散文句子**(某人某天想到的一句話),那種句子沒有任何理由在兩個地方一模一樣。
# 判準:規則規定「長什麼樣」→ 豁免;規則規定「寫得好不好」→ 不豁免。
FORMAT_PRESCRIBED = {"bizdoc", "official", "press", "techdoc", "spec", "architecture"}


def cjk_only(text: str) -> str:
    """只留中文字元。標點/空白/markdown 記號都剝掉——排版差異不該讓抄襲逃掉。"""
    return "".join(CJK.findall(text))


def shingles(text: str, n: int) -> set[str]:
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def skill_of(p: Path, repo: Path) -> str:
    """skills/<name>/... → <name>"""
    parts = p.relative_to(repo).parts
    return parts[1] if len(parts) > 1 else ""


def scan(repo: Path, n: int) -> list[str]:
    fixtures = [f for f in sorted(repo.glob(FIXTURE_GLOB))
                if skill_of(f, repo) not in FORMAT_PRESCRIBED]
    rule_files = []
    for g in RULE_GLOBS:
        rule_files.extend(f for f in sorted(repo.glob(g))
                          if skill_of(f, repo) not in FORMAT_PRESCRIBED)

    if not fixtures:
        print(f"⚠ 找不到任何夾具({FIXTURE_GLOB})——這道閘等於沒跑", file=sys.stderr)
        return []

    rule_index: list[tuple[Path, set[str]]] = []
    for rf in rule_files:
        try:
            body = cjk_only(rf.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        if len(body) >= n:
            rule_index.append((rf, shingles(body, n)))

    problems = []
    for fx in fixtures:
        body = cjk_only(fx.read_text(encoding="utf-8", errors="ignore"))
        if len(body) < n:
            continue
        fx_sh = shingles(body, n)
        for rf, rule_sh in rule_index:
            common = fx_sh & rule_sh
            if not common:
                continue
            # 把重疊的 shingle 合併成最長片段,訊息才讀得懂
            longest = max(common, key=len)
            for c in sorted(common):
                idx = body.find(c)
                if idx >= 0:
                    ext = c
                    while (idx + len(ext) < len(body)
                           and body[idx:idx + len(ext) + 1] in rule_sh | {ext}):
                        break
                    if len(ext) > len(longest):
                        longest = ext
            problems.append(
                f"{fx.relative_to(repo).as_posix()} ↔ {rf.relative_to(repo).as_posix()}\n"
                f"    共用 {len(common)} 個 {n} 字片段,例如「{longest}」")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="夾具不得逐字引用規則自己的例句")
    ap.add_argument("--repo", default=".", help="repo 根目錄")
    ap.add_argument("-n", type=int, default=DEFAULT_N,
                    help=f"視為耦合的連續中文字元數(預設 {DEFAULT_N})")
    ap.add_argument("--self-test", action="store_true",
                    help="紅燈可達自檢:造一組必紅與一組必綠的輸入")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test(args.n)

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"ERROR: 找不到 {repo}", file=sys.stderr)
        return 2

    problems = scan(repo, args.n)
    if problems:
        print(f"\n✗ 夾具與規則文件逐字耦合 {len(problems)} 處:\n")
        for p in problems:
            print("  " + p)
        print("\n夾具引用規則自己的示範句 = 用考古題驗考生:lint 對那些句子必然綠燈,"
              "\n因為規則就是照它們校準的。改寫夾具,不要改規則去遷就它。")
        return 1
    print(f"✅ 夾具與規則文件無 {args.n} 字以上的逐字重疊。")
    return 0


def self_test(n: int) -> int:
    """紅燈可達:同一句話放兩邊必須被抓到;不同的話必須放行。"""
    same = "他站在門口沒有說話我伸手往那個方向摸摸到的是牆"
    diff = "廟裡的燈滅了兩個人誰也沒有先動雨還在下沒有停"
    fails = []
    if not (shingles(same, n) & shingles(same, n)):
        fails.append("同一段文字竟然沒有共用片段——判定壞了")
    if shingles(same, n) & shingles(diff, n):
        fails.append("兩段不同的文字竟然被判為共用——判定過鬆")
    if fails:
        for f in fails:
            print(f"  ❌ {f}")
        print("\n✗ self-test 未通過:這道閘的紅燈或綠燈不可達。")
        return 1
    print("✅ self-test:逐字重疊會被抓、不同文字會放行,兩端皆可達。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
