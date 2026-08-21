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


# ── 判定三:`- Consensus:` 與逐項共識表(DIR-002 第 5 款)───────────────
#
# DIR-002 從 2026-08-13 生效,管的是「誰有權判定」——而它自己**八天沒有任何機器在看**,
# 全靠主 agent 記得送審。KN-001 的同一個型樣第 10 次,這次落在決定誰有權判定的那條規則上。
#
# 前瞻不追溯:只管檔名編號 >= CONSENSUS_SINCE 的 CHG。既有 41 張是在舊制度下完成的證據,
# 回填等於在已 merge 的歷史上偽造當時不存在的共識紀錄,而全數轉紅又是
# 「閘紅的理由與它要守的不變量無關」(STATUS_BASELINE 註解記過同型)。
# 邊界用**檔名編號字串比大小**而不是解析日期:CHG-YYYYMMDD-NN 的字典序就是時間序,
# 不需要第二套解析器,也就不會有第二套解析器的 bug。
#
# **本閘查得了什麼、查不了什麼,寫在 DIR-002 第 5 款的「判不了的四件事」**。
# 最要緊的一條:欄位可以謊填,同版本 ID 下的處置文字也可以被覆寫——
# 閘查形狀與引用,查不了共識是真的。防線是對造覆核,不是這支腳本。
CONSENSUS_SINCE = "CHG-20260821-01"

CONSENSUS_RE = re.compile(r"^-\s*Consensus[:：]\s*(.*)$", re.M)
ITEM_SEC_RE = re.compile(r"^##\s+修正項目\s*$", re.M)
TABLE_SEC_RE = re.compile(r"^##\s+審議席共識\s*$", re.M)
ITEM_ID_RE = re.compile(r"^-\s*(CHG-\d{8}-\d{2}\.\d+)\s*[—\-–]")
# 四種合法形狀。**「不同意」含「同意」兩字**,所以判同意一律先排除不同意——
# 子字串比對在中文否定式上會反向誤判,這裡不押注在「應該沒事」上。
SHAPE_BOTH = re.compile(r"codex\s*✓.*fable\s*✓|fable\s*✓.*codex\s*✓")
SHAPE_SINGLE = re.compile(r"^單方[(（]\s*(\S+?)\s*缺席[:：]\s*(.+?)\s*[)）]$")
SHAPE_DEADLOCK = re.compile(r"^僵局[(（]\s*記於\s*(\S+?)\s*[,，]\s*待使用者\s*[)）]$")
SHAPE_USER = re.compile(r"^使用者裁決[(（]\s*記於\s*(\S+?)\s*[)）]$")
AGREE_RE = re.compile(r"同意")
DISAGREE_RE = re.compile(r"不同意|反對")


def section_body(text: str, header_re) -> str | None:
    m = header_re.search(text)
    if not m:
        return None
    rest = text[m.end():]
    nxt = NEXT_H2.search(rest)
    return rest[:nxt.start()] if nxt else rest


def declared_items(text: str) -> list[str]:
    body = section_body(text, ITEM_SEC_RE)
    if body is None:
        return []
    out = []
    for ln in body.split("\n"):
        m = ITEM_ID_RE.match(ln.strip())
        if m:
            out.append(m.group(1))
    return out


def parse_table(text: str) -> list[list[str]] | None:
    """回傳資料列(已去掉表頭與分隔列);沒有 `## 審議席共識` 節回 None。"""
    body = section_body(text, TABLE_SEC_RE)
    if body is None:
        return None
    rows = []
    for ln in body.split("\n"):
        ln = ln.strip()
        if not ln.startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):     # 分隔列
            continue
        rows.append(cells)
    return rows[1:] if rows else []                       # 第一列是表頭


def shape_of(value: str) -> str:
    if SHAPE_BOTH.search(value):
        return "兩席具名"
    if SHAPE_SINGLE.match(value):
        return "單方"
    if SHAPE_DEADLOCK.match(value):
        return "僵局"
    if SHAPE_USER.match(value):
        return "使用者裁決"
    return ""


def consensus_verdict(name: str, text: str) -> list[str]:
    """回傳該檔的違規訊息;空清單 = 過。前瞻豁免由呼叫端先擋。"""
    bad = []
    head = header_of(text)
    m = CONSENSUS_RE.search(head)
    if not m:
        return [f"{name}:標頭沒有 `- Consensus:` 欄位"
                "——DIR-002 第 5 款自 " + CONSENSUS_SINCE + " 起強制,缺欄位不算過"]
    value = m.group(1).strip()
    if not value or PLACEHOLDER.match(value):
        bad.append(f"{name}:`- Consensus:` 是空的或還留著佔位字串")
        return bad
    shape = shape_of(value)
    if not shape:
        bad.append(f"{name}:`- Consensus:` 的值「{value[:60]}」不匹配四種合法形狀"
                   "(兩席具名 / 單方 / 僵局 / 使用者裁決)"
                   "——**新形狀要具名加進本閘,不能默默過**")

    items = declared_items(text)
    if not items:
        bad.append(f"{name}:`## 修正項目` 一個 ID 都沒列"
                   "——DIR-002 第 1 款要求**只有一個處置時仍須列一個 ID**")
    dup = {i for i in items if items.count(i) > 1}
    if dup:
        bad.append(f"{name}:修正項目 ID 重複:{'、'.join(sorted(dup))}")

    rows = parse_table(text)
    if len(items) >= 2 and rows is None:
        bad.append(f"{name}:列了 {len(items)} 個修正項目卻沒有 `## 審議席共識` 表"
                   "——兩項以上必須逐項列(單項免表是 BL-032 的分階段安排)")
    if rows is None:
        return bad

    row_ids = [r[0] for r in rows if r]
    for r in rows:
        if len(r) != 7:
            bad.append(f"{name}:共識表第一欄「{(r[0] if r else '')[:24]}」只有 {len(r)} 欄,"
                       "應為 7 欄(ID / 處置版本 ID / codex / fable / 共識狀態 / 輪次 / 未決理由)")
            continue
        rid, ver, cx, fb, state, rounds, _why = r
        if not ver:
            bad.append(f"{name}:{rid} 的處置版本 ID 是空的")
        if state == "通過":
            # **先排除否定式**:「不同意」含「同意」,子字串比對會反向誤判。
            for who, val in (("codex", cx), ("fable", fb)):
                if DISAGREE_RE.search(val) or not AGREE_RE.search(val):
                    bad.append(f"{name}:{rid} 標為通過,但 {who} 欄是「{val[:24]}」"
                               "——通過只能出現在兩席判定皆為同意時")
        try:
            n = int(rounds.strip())
        except ValueError:
            bad.append(f"{name}:{rid} 的收斂輪次「{rounds[:12]}」不是數字")
        else:
            if n > 3:
                bad.append(f"{name}:{rid} 的收斂輪次是 {n},超過第 2 款的三輪上限")

    missing = [i for i in items if i not in row_ids]
    extra = [i for i in row_ids if i not in items]
    for i in missing:
        bad.append(f"{name}:{i} 列在 `## 修正項目` 卻沒有共識表的對應列")
    for i in extra:
        bad.append(f"{name}:共識表有 {i} 這一列,但 `## 修正項目` 沒宣告它")

    # **標頭與表不得互相說謊。** 這一格是兩席在第三輪各自獨立提出的同一條:
    # 一張 CHG 可以整表僵局、標頭卻寫兩席具名,兩層各自全綠。純引用一致性,機器判得了。
    if shape == "兩席具名":
        notpass = [r[0] for r in rows if len(r) == 7 and r[4] != "通過"]
        if notpass:
            bad.append(f"{name}:標頭用了兩席具名形狀,但共識表有 {len(notpass)} 列不是通過"
                       f"({'、'.join(notpass[:3])})——標頭與表互相說謊")
    return bad


def check_consensus(files: list) -> list[str]:
    bad = []
    for f in files:
        if f.stem < CONSENSUS_SINCE:
            continue                                     # 前瞻不追溯
        bad.extend(consensus_verdict(f.name, f.read_text(encoding="utf-8")))
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
        # ── 判定三:綠端一例,紅端**全部由綠端突變產生** ──
        # 綠端就是 CHG-20260821-01 自己的形狀:四個修正項目、標頭因為表裡有非通過列
        # 而不能用兩席具名、輪次都在三輪內。
        cg = (
            "# CHG-20260821-01 — X" + chr(10) + chr(10) +
            "- Consensus: 使用者裁決(記於 CHG-20260821-01)" + chr(10) +
            "- Risk: 中" + chr(10) + chr(10) +
            "## 修正項目" + chr(10) + chr(10) +
            "- CHG-20260821-01.1 — 條文" + chr(10) +
            "- CHG-20260821-01.2 — 斷言條文" + chr(10) + chr(10) +
            "## 審議席共識" + chr(10) + chr(10) +
            "| 修正項目 ID | 處置版本 ID | codex 判定 | fable 判定 | 共識狀態 | 收斂輪次 | 未決理由 |" + chr(10) +
            "|---|---|---|---|---|---|---|" + chr(10) +
            "| CHG-20260821-01.1 | v3-a | 同意 | 同意 | 通過 | 3 | — |" + chr(10) +
            "| CHG-20260821-01.2 | v3-b | 不同意 | 同意 | 使用者裁決 | 3 | 三輪未收斂 |" + chr(10) +
            chr(10) + "## Status" + chr(10) + chr(10) + "已驗收 — ACC-X。" + chr(10)
        )
        if consensus_verdict("green.md", cg):
            fails.append("判定三綠端竟然不綠:" +
                         " / ".join(consensus_verdict("green.md", cg)))
        cmuts = [
            ("缺欄位", cg.replace("- Consensus: 使用者裁決(記於 CHG-20260821-01)" + chr(10), "", 1),
             "沒有 `- Consensus:` 欄位"),
            ("形狀不合法", cg.replace("使用者裁決(記於 CHG-20260821-01)", "兩席都說可以", 1),
             "不匹配四種合法形狀"),
            ("單方理由空白", cg.replace("使用者裁決(記於 CHG-20260821-01)", "單方(codex 缺席:)", 1),
             "不匹配四種合法形狀"),
            ("零個修正項目", cg.replace("- CHG-20260821-01.1 — 條文" + chr(10), "", 1)
                              .replace("- CHG-20260821-01.2 — 斷言條文" + chr(10), "", 1),
             "一個 ID 都沒列"),
            ("兩項以上卻沒表", cg.replace("## 審議席共識", "## 別的節", 1),
             "沒有 `## 審議席共識` 表"),
            ("表缺一列", cg.replace(
                "| CHG-20260821-01.2 | v3-b | 不同意 | 同意 | 使用者裁決 | 3 | 三輪未收斂 |" + chr(10), "", 1),
             "沒有共識表的對應列"),
            ("表多一列", cg.replace(
                "| CHG-20260821-01.2 | v3-b | 不同意 | 同意 | 使用者裁決 | 3 | 三輪未收斂 |",
                "| CHG-20260821-01.2 | v3-b | 不同意 | 同意 | 使用者裁決 | 3 | 三輪未收斂 |" + chr(10) +
                "| CHG-20260821-01.9 | v3-z | 同意 | 同意 | 通過 | 1 | — |", 1),
             "`## 修正項目` 沒宣告它"),
            # **否定式反向誤判的正控**:「不同意」含「同意」,子字串比對會判它通過。
            ("一席不同意卻標通過", cg.replace(
                "| CHG-20260821-01.2 | v3-b | 不同意 | 同意 | 使用者裁決 | 3 |",
                "| CHG-20260821-01.2 | v3-b | 不同意 | 同意 | 通過 | 3 |", 1),
             "通過只能出現在兩席判定皆為同意時"),
            ("輪次超過三", cg.replace("| 同意 | 同意 | 通過 | 3 |", "| 同意 | 同意 | 通過 | 4 |", 1),
             "超過第 2 款的三輪上限"),
            ("處置版本 ID 空白", cg.replace("| CHG-20260821-01.1 | v3-a |",
                                            "| CHG-20260821-01.1 |  |", 1),
             "處置版本 ID 是空的"),
            # 兩席在第三輪各自獨立提出的同一條:標頭與表不得互相說謊。
            ("標頭具名兩席但表有非通過列", cg.replace(
                "使用者裁決(記於 CHG-20260821-01)", "codex ✓ 2026-08-21 / fable ✓ 2026-08-21", 1),
             "標頭與表互相說謊"),
        ]
        for label, text, want in cmuts:
            got = consensus_verdict("m.md", text)
            if not any(want in g for g in got):
                fails.append("判定三紅端「" + label + "」應報「" + want +
                             "」,實得 " + (" / ".join(got) if got else "全綠") +
                             "——**該出口不可達**")
        # 前瞻豁免的正控:同一份壞樣本掛在舊編號上必須被跳過,否則會回頭紅既有 41 張
        import tempfile as _tf
        with _tf.TemporaryDirectory() as d2:
            r2 = Path(d2)
            broken = cg.replace("- Consensus: 使用者裁決(記於 CHG-20260821-01)" + chr(10), "", 1)
            (r2 / "CHG-20260727-01.md").write_text(broken, encoding="utf-8")
            if check_consensus([r2 / "CHG-20260727-01.md"]):
                fails.append("前瞻豁免失效:CHG-20260727-01 早於 " + CONSENSUS_SINCE +
                             ",不該被判定三掃到")
            (r2 / "CHG-20260821-01.md").write_text(broken, encoding="utf-8")
            if not check_consensus([r2 / "CHG-20260821-01.md"]):
                fails.append("生效邊界失效:CHG-20260821-01 是第一張該被掃的,竟然全綠"
                             "——**邊界寫成了永遠豁免**")
        if fails:
            for f in fails:
                print("  ❌ " + f)
            return 1
        print("✅ self-test:佔位字串綠紅兩端可達;"
              "Status 綠端 + 三個紅出口(換詞×2 / 刪段×1)皆由綠端突變產生;"
              "baseline 的 fail-open 與孤兒條目兩個紅端亦可達;"
              "判定三綠端 + " + str(len(cmuts)) + " 個紅端(全部由綠端突變產生)"
              "+ 前瞻邊界的豁免與生效兩側正控皆可達")
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

    # ── 判定三:`- Consensus:` 與逐項共識表(DIR-002 第 5 款)──
    n_scope = sum(1 for f in files if f.stem >= CONSENSUS_SINCE)
    con_bad = check_consensus(files)
    if con_bad:
        print(chr(10) + "✗ 共識欄位檢查 " + str(len(con_bad)) + " 項:")
        for b in con_bad:
            print("  " + b)
        print(chr(10) + "DIR-002 第 5 款自 " + CONSENSUS_SINCE + " 起前瞻生效。"
              "**缺欄位不算過**,否則本閘會退化成恆真。")
        return 1
    print("✅ 共識欄位一致:" + str(n_scope) + " 份在生效範圍內、"
          + str(len(files) - n_scope) + " 份前瞻豁免(舊制度下的歷史帳本)。")
    print("   仍判不了的四件事見 DIR-002 第 5 款:欄位可謊填、"
          "同版本 ID 下的文字可被覆寫、票內可能藏著沒列出的處置、"
          "該開 CHG 而沒開的變更本閘全盲。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
