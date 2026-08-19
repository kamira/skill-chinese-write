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

判定一(欄位):標頭(第一個 `##` 之前)的 `- 欄位:` 值若整個被 `<...>` 包住,即違規。
`<close-out 回填>`、`<hash / PR link>`、`<change title>` 都是這一類。

判定二(`## Status` 的**內容**,BL-024):本檔原本的收尾句自承「查的是有沒有填,
查不了填得對不對」——這一條就是把後半補掉。

`doc_integrity_check` 只查 `## Status` 這一節**存不存在**。而「施工中」不是可辨識的
佔位字串,是一句**看起來完整的假陳述**:`CHG-20260814-07` 掛著它一路 merge 進 main,
第三天才被眼睛抓到(`632cbe4` / #17);`CHG-20260817-03` 同樣掛著,靠人在 merge 前攔下。
**一次進了 main,一次靠眼睛——兩次都不是閘擋的。**

切法(審議席兩輪對審後定案,fail-closed):

    取精確 `^## Status$` 至下一個 `##` 前 → 按空行切段 → **跳過整段每行都以 `>` 開頭的段**
    → 取第一個平文段 → 判狀態詞

四個出口,三個是紅:

| 出口 | 條件 |
|---|---|
| `GREEN` | 首個平文段含「已驗收 / Accepted」 |
| `RED(bad-state)` | 首個平文段含「施工中 / 進行中 / WIP」——**先於綠判,歧義往紅倒** |
| `RED(no-plain-para)` | 跳掉引用段後**沒有平文段**——狀態不得藏在引用塊裡 |
| `RED(unknown-state)` | 兩者皆無——**新狀態詞必須具名加進本閘,不能默默過** |

跳引用段是必要的:`CHG-20260814-07` 的已驗收 Status **引用了舊的「施工中」在說明事故**,
掃整節會誤紅它——而它正是這條規則要保護的那張。
初版審議席的採樣「只列首行零誤紅」證不了「掃整節零誤紅」:**量的東西和判的東西不是同一個。**

而只跳引用段又會開一個逃逸口(把「施工中」寫成引用就繞過),所以「無平文段」也是紅。

**本閘不設防的面**:首段直接**謊寫**「已驗收」的,任何內容閘都判不了。
本閘治的是「模板狀態忘了改」,不是蓄意造假。

**紅燈可達內建**:`--self-test` 拿嵌在檔內的好壞兩份標頭各跑一次;
Status 那三個紅出口各有一例,且**全部由綠端突變產生**(換詞 / 刪段),不另寫假資料。

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


# ── `## Status` 的內容判定(BL-024)────────────────────────────────────
BAD_STATE = re.compile(r"施工中|進行中|WIP")
OK_STATE = re.compile(r"已驗收|Accepted")

# **具名 baseline,只能縮不能長。** 這 16 張是模板前的歷史帳本,帳本自己規定不回改
# (`docs/writing/backlog.md`)。名單以檔名具名而**不綁內容雜湊**:要守的性質是
# 「這幾張沒有 Status 節」,雜湊會把整份文件的全部內容釘進閘,改個錯字就紅——
# 閘紅的理由與它要守的不變量無關。
#
# 三條斷言把 fail-open 關掉(BL-015 的教訓:白名單可登記從未存在的東西而全綠):
#   1 不在 baseline 的 CHG 必須有精確 `## Status`——缺就紅
#   2 baseline 裡的檔名必須存在於磁碟——不存在就紅
#   3 baseline 裡的檔必須**確實沒有** `## Status`——長出來了就紅,強迫移出 baseline
# 第 1 條讓「全 repo 都沒有 Status」不可能全綠;第 3 條讓每筆條目自帶失效期。
STATUS_BASELINE = frozenset("""
CHG-20260727-01.md CHG-20260728-01.md CHG-20260728-02.md CHG-20260729-01.md
CHG-20260804-01.md CHG-20260804-02.md CHG-20260804-03.md CHG-20260810-02.md
CHG-20260810-03.md CHG-20260810-04.md CHG-20260810-05.md CHG-20260810-06.md
CHG-20260810-08.md CHG-20260810-09.md CHG-20260810-10.md CHG-20260814-02.md
""".split())


def status_verdict(text: str) -> tuple[str, str]:
    """回 (出口, 首個平文段前 80 字)。出口見模組 docstring 的四出口表。

    切段刻意用迴圈而不用 regex:空行可能夾雜空白或 TAB,而寫成 `[ \t]` 這種
    跳脫字元在經過多層工具傳遞時會被吃掉——施工時就發生過一次:`
` 變成真換行、
    `\t` 變成真 TAB,整個檔語法錯。**不需要跳脫就不要用跳脫。**
    """
    # **圍籬內的一律不算。** CHG 常在正文裡用 ``` 引一段別張的 Status 當證據
    # (本張自己就引了 `632cbe4` 的「施工中 — 待 ACC-20260814-07。」),
    # 不濾圍籬的話會抓到那一段,判到的是別張的狀態。施工時實際發生過。
    lines = []
    fence = False
    for ln in text.splitlines():
        s = ln.lstrip()
        if s.startswith("```") or s.startswith("~~~"):
            fence = not fence
            lines.append("")          # 佔位,維持段落切分不被圍籬黏起來
            continue
        lines.append("" if fence else ln)
    start = None
    for i, ln in enumerate(lines):
        if ln.rstrip().rstrip(chr(9)) == "## Status":
            start = i + 1
            break
    if start is None:
        return ("NO_STATUS", "")
    body = []
    for ln in lines[start:]:
        if ln.startswith("## "):
            break
        body.append(ln)
    paras, cur = [], []
    for ln in body:
        if ln.strip():
            cur.append(ln)
        elif cur:
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)
    # 整段每行都以 `>` 開頭 = 引用段,跳過。
    plain = [q for q in paras
             if not all(x.lstrip().startswith(">") for x in q)]
    if not plain:
        return ("RED(no-plain-para)", "")
    first = " ".join(" ".join(plain[0]).split())
    # **先判紅**:同一段同時出現「已驗收」與「施工中」時往紅倒。
    if BAD_STATE.search(first):
        return ("RED(bad-state)", first[:80])
    if OK_STATE.search(first):
        return ("GREEN", first[:80])
    return ("RED(unknown-state)", first[:80])


def check_status(files: list) -> list[str]:
    """回違規訊息。files 是 Path 清單。"""
    bad = []
    seen = set()
    for f in files:
        seen.add(f.name)
        in_base = f.name in STATUS_BASELINE
        code, detail = status_verdict(f.read_text(encoding="utf-8"))
        if in_base:
            # 斷言 3
            if code != "NO_STATUS":
                bad.append(f"{f.name}:在 baseline 裡卻已經有 `## Status` 了"
                           "——請把它從 STATUS_BASELINE 移除,改走內容檢查")
            continue
        # 斷言 1
        if code == "NO_STATUS":
            bad.append(f"{f.name}:沒有精確的 `## Status` 節,也不在具名 baseline 裡"
                       "——**缺節不算過**,否則本閘會退化成恆真")
        elif code.startswith("RED"):
            why = {"RED(bad-state)": "`## Status` 說它還在施工,而它已經在帳本裡",
                   "RED(no-plain-para)": "`## Status` 只有引用塊,沒有平文段"
                                         "——狀態不得藏在引用裡",
                   "RED(unknown-state)": "`## Status` 的狀態詞不在本閘認得的名單內"
                                         "——新狀態詞要具名加進閘,不能默默過"}[code]
            bad.append(f"{f.name}:{why}" + (f"「{detail}」" if detail else ""))
    # 斷言 2
    for name in sorted(STATUS_BASELINE - seen):
        bad.append(f"{name}:登記在 STATUS_BASELINE 裡,但掃不到這個檔"
                   "——名單可以縮,不能留孤兒(BL-015 的形狀)")
    return bad


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
        # ── Status 內容判定:三個紅出口各一例,**全部由綠端突變產生** ──
        # 綠端不是我造的樣本,是 `CHG-20260814-07` 現行 Status 的形狀:
        # 首段「已驗收」,而**後面的引用塊裡引了舊的「施工中」在說明事故**。
        # 掃整節會誤紅它——而它正是這條規則要保護的那張。
        green = """## Status

已驗收 — ACC-20260814-07(**通過(二讀)**);已 merge:632cbe4 / #17。

> 本欄原本寫「施工中 — 待 ACC-20260814-07。」
> 而它已驗收、已 merge。
"""
        first_para = "已驗收 — ACC-20260814-07(**通過(二讀)**);已 merge:632cbe4 / #17。"
        muts = [
            # 換詞突變:只動首段的狀態詞
            ("bad-state", green.replace("已驗收 —", "施工中 —", 1),
             "RED(bad-state)"),
            ("unknown-state", green.replace("已驗收 —", "完成了 —", 1),
             "RED(unknown-state)"),
            # 刪段突變:刪掉首個平文段,只留引用塊
            ("no-plain-para", green.replace(first_para, "", 1),
             "RED(no-plain-para)"),
        ]
        code, _ = status_verdict(green)
        if code != "GREEN":
            fails.append("Status 綠端竟然不綠(" + code +
                         ")——引用塊裡的「施工中」被誤判了")
        for label, text, want in muts:
            got, _ = status_verdict(text)
            if got != want:
                fails.append("Status 紅端「" + label + "」應為 " + want +
                             ",實得 " + got + "——**該出口不可達**")
        # 圍籬回歸:正文裡引了別張的 Status 當證據,不得被當成本張的狀態
        fenced = ("# X" + chr(10) + chr(10) +
                  "```" + chr(10) + "## Status" + chr(10) + chr(10) +
                  "施工中 — 待 ACC-9999-99。" + chr(10) + "```" + chr(10) + chr(10) +
                  green)
        got_f, det_f = status_verdict(fenced)
        if got_f != "GREEN":
            fails.append("圍籬裡引用的 Status 被當成本張的狀態(" + got_f +
                         ":" + det_f + ")——**判到的是別張的狀態**")
        # 正控:同一份把圍籬拿掉,必須紅。否則上面那條會退化成「圍籬內外都不看」
        if status_verdict(fenced.replace("```", "", 2))[0] != "RED(bad-state)":
            fails.append("拿掉圍籬後竟然還綠——正控失敗,濾圍籬變成濾掉全部")
        if status_verdict("# 沒有 Status 節" + chr(10))[0] != "NO_STATUS":
            fails.append("缺 Status 節應回 NO_STATUS,由 baseline 斷言接手")
        # baseline 三條斷言的紅端(BL-015 的形狀:白名單可登記從未存在的東西)
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "CHG-9999-01.md").write_text(
                green.replace("已驗收 —", "施工中 —", 1), encoding="utf-8")
            # **斷言要打在訊息內容上,不能只看「非空」。** check_status 對單檔子集
            # 會同時噴 16 條「baseline 孤兒」——只斷言非空的話,就算 bad-state 那條
            # 規則整個壞掉,孤兒訊息也會讓這個測試照樣過:**斷言被別的東西滿足了**。
            got = check_status([root / "CHG-9999-01.md"])
            if not any("CHG-9999-01.md" in g and "還在施工" in g for g in got):
                fails.append("baseline 外、Status 說施工中的檔竟然通過")
            (root / "CHG-9999-02.md").write_text("# X" + chr(10), encoding="utf-8")
            got2 = check_status([root / "CHG-9999-02.md"])
            if not any("CHG-9999-02.md" in g and "沒有精確的" in g for g in got2):
                fails.append("baseline 外、**沒有 Status 節**的檔竟然通過"
                             "——fail-open,本閘會退化成恆真")
        orphan = check_status([])
        if len(orphan) != len(STATUS_BASELINE) or not all(
                "掃不到這個檔" in g for g in orphan):
            fails.append("STATUS_BASELINE 的 " + str(len(STATUS_BASELINE)) +
                         " 筆在掃不到任何檔時應全部報孤兒,實得 " +
                         str(len(orphan)) + " 條")
        if fails:
            for f in fails:
                print("  ❌ " + f)
            return 1
        print("✅ self-test:佔位字串綠紅兩端可達;"
              "Status 綠端 + 三個紅出口(換詞×2 / 刪段×1)皆由綠端突變產生;"
              "baseline 的 fail-open 與孤兒條目兩個紅端亦可達")
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
    print("✅ 所有標頭欄位都已填。")

    # ── 判定二:`## Status` 的內容(BL-024)──
    status_bad = check_status(files)
    n_base = sum(1 for f in files if f.name in STATUS_BASELINE)
    if status_bad:
        print(chr(10) + "✗ `## Status` 內容檢查 " + str(len(status_bad)) + " 項:")
        for b in status_bad:
            print("  " + b)
        print(chr(10) + "「施工中」不是可辨識的佔位字串,是一句**看起來完整的假陳述**"
              "——CHG-20260814-07 掛著它一路 merge 進 main,第三天才被眼睛抓到。")
        return 1
    print("✅ `## Status` 內容一致:" + str(len(files) - n_base) + " 份判為已驗收、"
          + str(n_base) + " 份在具名 baseline(模板前的歷史帳本)。")
    print("   仍判不了的:首段直接**謊寫**已驗收。"
          "本閘治的是模板狀態忘了改,不是蓄意造假。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
