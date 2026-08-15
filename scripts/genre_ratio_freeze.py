#!/usr/bin/env python3
"""配比凍結閘——搬遷期間,流派數值不准漂。

## 為什麼需要這道閘

把子層 skill 搬成 command,是把同一份數值從一個檔案搬到另一個檔案。
搬運途中數字掉一位、區間上下顛倒、或某一支漏搬,**看起來都和搬對了一模一樣**——
因為沒有任何既有的閘在看這些數字。審議席因此把它列為搬遷的強制前置。

凍結表取自搬遷前的 git ref(`FROZEN_REF`),是**寫死在本檔的字面值**,不是
從樹裡讀出來的。理由:從樹裡讀出來的基準會跟著樹一起漂,那等於沒有基準。

## 三欄,不是一欄

搬遷過程中發現的事實(CHG-20260814-05):**同一個「配比」欄位,三個數字的
機器真相程度完全不同。**

| 欄 | 誰在管 | 說明 |
|---|---|---|
| 修辭比例 % | **沒有機器真相** | 沒有程式量得出一段文字有幾成是譬喻。純文案。 |
| 成語密度**上限** | 引擎管 | `fiction_rules.json` 的 `per_1000[1]`,lint 真的會擋 |
| 成語密度**下限** | **引擎不管** | `per_1000[0]` 一律是 0——下限是 CHG-20260810-10 刻意拆掉的 |

而各子層文案寫的是「成語密度 4-8 次/千字 | lint 會數」。
讀者會合理地以為 4 是被檢查的下限。**它不是。**

宣稱引擎在管、實際沒有——這與 KN-001 那一族同型:規則存在,斷言不存在。
所以本閘凍三欄,並且**分別標記各自的可驗證性**;把三者混成一欄,等於把
「引擎擋得住的」和「只是寫在紙上的」混為一談。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Windows 主控台預設 cp950,吐不出 ✅/✗。與 skill_inventory_check.py 同一套前置。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

FROZEN_REF = "6fea545"          # 搬遷前的 main;凍結表由此 ref 量得
RULES = "skills/fiction/assets/fiction_rules.json"

# ---- 執法狀態:凍結表凍的不只是數字,還有「這個數字歸誰管」。
#
# 審議席(fable,CHG-20260814-05)指定要凍狀態本身,理由是它防的不是數字漂移,
# 是**執法狀態漂移**——「原本引擎管的變成沒人管」。那種漂移下每個數字都還在原位,
# 純字面比對一律綠燈,而規範已經名存實亡。
STATUS = {
    "rhetoric": "無機器真相",   # 沒有程式量得出譬喻佔比
    "idiom_hi": "引擎硬管",     # per_1000[1],且 [D] 探針實跑證明會開火
    "idiom_lo": "引擎不管",     # per_1000[0] 恆 0,且引擎裡沒有下限那段程式
}

# ---- 凍結表:(修辭下%, 修辭上%, 成語下限, 成語上限)
# 成語「下限」凍的是**文案宣稱的數字**,不是引擎值——引擎值恆為 0,見上方說明。
FROZEN: dict[str, tuple[int, int, int, int]] = {
    "long":    (25, 35, 4, 8),
    "flash":   (15, 20, 1, 3),
    "mystery": (15, 20, 2, 5),
    "romance": (35, 45, 5, 10),
    "scifi":   (10, 15, 1, 3),
    "wuxia":   (30, 40, 8, 14),
}

# 引擎真的會擋的,只有上限;下限恆為 0。這個期望值寫死,不是從 json 抄過來的
# ——抄過來就變成「json 說什麼就是什麼」,那樣改壞了也不會紅。
ENGINE_FLOOR_IS_ZERO = True

# 一支流派的文案可能住在兩個地方(搬遷期間並存):
#   搬遷前:skills/fiction-<g>/SKILL.md
#   搬遷後:commands/fiction-<g>.md  以及  plugins/fiction/commands/fiction-<g>.md
# **三處都要驗。** 只驗其中一處,另外兩處就是下一個孤兒。
def live_docs(root: Path, genre: str) -> list[Path]:
    return [p for p in (
        root / "skills" / f"fiction-{genre}" / "SKILL.md",
        root / "commands" / f"fiction-{genre}.md",
        root / "plugins" / "fiction" / "commands" / f"fiction-{genre}.md",
    ) if p.is_file()]


PCT = re.compile(r"(\d+)\s*%\s*[-–~]\s*(\d+)\s*%")
IDIOM = re.compile(r"(\d+)\s*[-–~]\s*(\d+)\s*次\s*/\s*千字")

# 誠實欄:文案一旦報出成語區間,就必須同時說清楚下限沒有機器在管。
# 措辭不寫死成單一句子(那會變成關鍵字遊戲),而是要求兩個語義成分同時在場——
# **而且必須在同一個單元裡**,見 units()。
#
# 第二成分原本寫 `不(?:會|被)?(?:檢查|…)`,配不上「不**會被**檢查」
# ——`(?:會|被)?` 只吃得下一個字。閘自己的綠端範例用的正是那個措辭,
# 於是綠端一直靠跨單元污染成立。複審(fable)用合成 probe 打出來的。
HONEST_FLOOR = (
    re.compile(r"下限"),
    re.compile(r"不(?:會)?(?:被)?(?:檢查|檢驗|驗|管|擋|查)"
               r"|沒有(?:程式|引擎|機器|lint)"),
)
HONEST_RHETORIC = (
    re.compile(r"修辭比例"),
    re.compile(r"靠人判斷|沒有機器真相|沒有程式量得出"),
)


def units(text: str) -> list[str]:
    """把文件切成判定單元。**誠實欄的兩個成分必須落在同一個單元裡。**

    為什麼需要這個:整份文件當一個單元時,誠實欄是一場關鍵字賓果。
    複審實測兩個方向都能穿——
      - 成語那列正面說謊「上限與下限都會擋」,卻被**修辭那列**的
        「沒有程式量得出」滿足了第二成分 → 綠燈。
      - 修辭那列說謊「lint 會量」,卻被**成語那列**的「靠人判斷」滿足 → 綠燈,
        而且還誤掛了一條下限的罪名。
    那正是審議席裁決 5「禁止合寫」要擋的形狀,而閘擋不住。

    單元的切法:
      - 表格列(`|` 開頭)**各自成一個單元**——同一張表的兩列不得互相支援
      - 其餘:空行分隔的段落
    兩種都要,因為配比可能寫成表格(舊 SKILL.md)也可能寫成分段(新 command)。
    """
    out: list[str] = []
    buf: list[str] = []

    def flush():
        if buf:
            out.append("\n".join(buf))
            buf.clear()

    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("|"):
            flush()
            out.append(ln)
        elif not s:
            flush()
        else:
            buf.append(ln)
    flush()
    return out


def scan_doc(path: Path) -> dict:
    t = path.read_text(encoding="utf-8", errors="ignore")
    us = units(t)
    # 有報數字的單元,才被要求誠實。沒提到配比的段落不必附免責。
    idiom_units = [u for u in us if IDIOM.search(u)]
    pct_units = [u for u in us if PCT.search(u)]
    return {
        "pct": PCT.findall(t),
        "idiom": IDIOM.findall(t),
        # all(...) over an empty list is True——沒報數字就沒有誠實義務,
        # 這與「報了卻沒說清楚」是兩回事,由呼叫端的 idioms/pcts 判斷分開。
        "honest_floor": all(all(r.search(u) for r in HONEST_FLOOR)
                            for u in idiom_units),
        "honest_rhetoric": all(all(r.search(u) for r in HONEST_RHETORIC)
                               for u in pct_units),
        "text": t,
    }


ENGINE = "skills/fiction/scripts/fiction_check.py"

# 一句含兩個成語、長度固定的骨幹句。重複它就能把密度推到任意高度,
# 而句子本身合法(有句號、不觸發段落長度以外的規則)。
_IDIOM_SENT = "他想起往事,寒來暑往,百感交集,於是繼續走。"
_PLAIN_SENT = "他走了出去,又走了回來,然後坐下,再站起來,看著窗外。"

# **只認違規行,不認統計行。** 初版寫 `"成語" in blob`,而引擎每次都會印一行
# 「成語 N 次(X/千字)」的統計——於是兩端都「命中」,超標與零成語看起來一樣,
# 上限被改成天文數字也照樣綠燈。那是探針自己的假陽性,和它要抓的病同型:
# 訊號存在不等於斷言存在。
#
# 方向詞收多個同義寫法。初版只寫「超過」,而引擎的用字是「**高於**」——
# 那個字面是我從亂碼終端機裡猜的,不是量出來的,於是探針對真引擎恆為假陰性。
# 同一個病的第三次:**用回憶代替量測**。
CEIL_HIT = re.compile(r"成語密度[^\n]*(?:高於|超過|超出|多於)[^\n]*上限")
FLOOR_HIT = re.compile(r"成語密度[^\n]*(?:低於|不足|少於|未達)[^\n]*下限")


def enforcement_probe(root: Path, only: tuple[str, ...] | None = None) -> list[str]:
    """[D] 用**跑的**證明兩個狀態,不是用讀的。

    凍結表宣稱「成語密度上限=引擎硬管、下限=引擎不管」。這兩句話的真假,
    讀 `fiction_rules.json` 只能看出配置長什麼樣,看不出引擎**會不會真的開火**
    ——那是 KN-001 那一族的整個教訓:規則存在不等於斷言存在。

    所以這裡合成兩份稿:
      - 超過上限一大截 → 引擎**必須**點名成語密度。不點名 = 「硬管」是假的。
      - 完全沒有成語   → 引擎**必須不**點名。點名了 = 下限偷偷復活了,
                          而那是 CHG-20260810-10 拆掉的東西。

    兩端都驗,是因為只驗一端的話,「引擎永遠開火」和「引擎永遠不開火」
    各自都能騙過其中一端。
    """
    import subprocess
    import tempfile

    engine = root / ENGINE
    if not engine.is_file():
        return [f"[D] 找不到引擎 {ENGINE}——無法證明執法狀態,不得以「設定看起來對」代替"]

    out: list[str] = []
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    with tempfile.TemporaryDirectory() as td:
        hi = Path(td) / "over.md"
        lo = Path(td) / "none.md"
        hi.write_text("「走。」他說。\n\n" + _IDIOM_SENT * 40 + "\n", encoding="utf-8")
        lo.write_text("「走。」他說。\n\n" + _PLAIN_SENT * 40 + "\n", encoding="utf-8")

        def run(path: Path, g: str) -> str | None:
            r = subprocess.run(
                [sys.executable, str(engine), str(path), "--genre", g],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", env=env, cwd=root)
            blob = (r.stdout or "") + (r.stderr or "")
            if "Traceback" in blob:
                return None
            return blob

        # only:自檢用。真實 repo 一律跑滿六支——少跑一支就等於那支沒被驗。
        for g in sorted(only or FROZEN):
            over, none = run(hi, g), run(lo, g)
            if over is None or none is None:
                out.append(f"[D] {g}: 引擎在探針上炸了——無法證明執法狀態,"
                           "不得以「設定看起來對」代替")
                continue
            # 期望值由 STATUS 推出來,不是寫死的。這樣把 STATUS 改成
            # 與現實不符的字串,閘會立刻紅——狀態欄本身也被斷言看著。
            if (STATUS["idiom_hi"] == "引擎硬管") != bool(CEIL_HIT.search(over)):
                out.append(f"[D] {g}: 凍結表說成語上限「{STATUS['idiom_hi']}」,"
                           f"但把密度推到遠超 {FROZEN[g][3]} 時引擎"
                           f"{'沒有' if STATUS['idiom_hi'] == '引擎硬管' else '卻'}報違規"
                           "——狀態欄與實跑不符")
            if (STATUS["idiom_lo"] == "引擎硬管") != bool(FLOOR_HIT.search(none)):
                out.append(f"[D] {g}: 凍結表說成語下限「{STATUS['idiom_lo']}」,"
                           "但零成語稿的實跑結果相反——下限復活了,"
                           "而它是 CHG-20260810-10 拆掉的")
    return out


def is_command(rel: str) -> bool:
    """誠實欄只對 command 檔強制,不對搬遷前的舊 SKILL.md 強制。

    這不是網開一面,是審議席(fable,CHG-20260814-05 裁決 4)畫的線:
    舊 SKILL.md 在倒數第二步就要被刪,回頭改注定要刪的檔是白工;
    而**把已知半真的文案原文照抄進新的 command,是把已確認的缺陷複製進新檔**
    ——那才是要擋的東西。所以判準是住址,不是旗標。

    用旗標(`--strict-honest`)的話,閘會有一個「未驗」狀態,而未驗與通過
    在 CI 輸出裡長得一樣——這個 repo 已經為那件事付過一次代價。
    """
    return rel.startswith("commands/") or "/commands/" in rel


def check(root: Path, engine: bool = True) -> list[str]:
    """回傳問題清單。空 = 全綠。"""
    bad: list[str] = []

    # ---- A:引擎上限 vs 凍結表
    rules_p = root / RULES
    if not rules_p.is_file():
        return [f"找不到規則檔:{RULES}"]
    genres = json.loads(rules_p.read_text(encoding="utf-8"))["idioms"]["genres"]

    for g, (_, _, _, hi) in sorted(FROZEN.items()):
        if g not in genres:
            bad.append(f"[A] 引擎少了流派 {g}——凍結表有、規則檔沒有")
            continue
        got = genres[g].get("per_1000")
        if not (isinstance(got, list) and len(got) == 2):
            bad.append(f"[A] {g}: per_1000 形狀不對({got!r})")
            continue
        if got[1] != hi:
            bad.append(f"[A] {g}: 引擎上限 {got[1]} ≠ 凍結表 {hi}(ref {FROZEN_REF})")
        if ENGINE_FLOOR_IS_ZERO and got[0] != 0:
            bad.append(f"[A] {g}: 引擎下限成了 {got[0]}——"
                       "下限是 CHG-20260810-10 刻意拆掉的,復活要先開 CHG")

    for g in sorted(set(genres) - set(FROZEN)):
        bad.append(f"[A] 規則檔多了凍結表沒有的流派 {g}——名冊與現實分岔")

    # ---- D:執法狀態不是用讀的,是用跑的
    if engine:
        bad += enforcement_probe(root)

    # ---- B/C:文案數值 vs 凍結表(三處住址逐一驗)
    for g, (lo_p, hi_p, lo_i, hi_i) in sorted(FROZEN.items()):
        docs = live_docs(root, g)
        if not docs:
            bad.append(f"[B] {g}: 三處住址都找不到文案——搬遷把它弄丟了")
            continue
        for d in docs:
            rel = d.relative_to(root).as_posix()
            s = scan_doc(d)
            pcts = {tuple(map(int, m)) for m in s["pct"]}
            idioms = {tuple(map(int, m)) for m in s["idiom"]}
            if (lo_p, hi_p) not in pcts:
                bad.append(f"[B] {rel}: 修辭比例 {sorted(pcts) or '查無'} "
                           f"不含凍結值 {lo_p}%-{hi_p}%")
            if (lo_i, hi_i) not in idioms:
                bad.append(f"[B] {rel}: 成語密度 {sorted(idioms) or '查無'} "
                           f"不含凍結值 {lo_i}-{hi_i} 次/千字")
            if is_command(rel) and idioms and not s["honest_floor"]:
                bad.append(f"[C] {rel}: 報了成語區間卻沒說「下限沒有機器在管」"
                           "——讀者會以為 lint 會擋下限,它不會")
            if is_command(rel) and pcts and not s["honest_rhetoric"]:
                bad.append(f"[C] {rel}: 報了修辭比例卻沒說它靠人判斷"
                           "——那個百分比沒有機器真相")
    return bad


# ---------------------------------------------------------------- self-test
_GOOD_DOC = """---
description: 測試用
---
| **修辭比例** | 中高(25%-35%) | 靠人判斷——沒有程式量得出一段文字有幾成是譬喻 |
| **成語密度** | 4-8 次/千字 | lint 只擋上限;**下限不會被檢查**(引擎值為 0) |
"""


def _tree(root: Path, rules: dict, docs: dict[str, str]) -> None:
    p = root / RULES
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"idioms": {"genres": rules}}, ensure_ascii=False),
                 encoding="utf-8")
    for rel, body in docs.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body, encoding="utf-8")


def probe_self_test() -> list[str]:
    """[D] 的紅端——**打真引擎**,不是打合成樹。

    三案:
      13 綠端:原封不動的引擎樹 → probe 無話可說
      14 紅端:把上限改成天文數字 → 超標稿不再被點名 → 「引擎硬管」應被戳破
      15 紅端:把下限改回非 0 → 零成語稿被點名 → 「下限不管」應被戳破

    案 14 這個形狀就是最危險的一種漂移:配置還在、數字還在、`per_1000` 兩個
    元素也都在,**只是不再擋任何東西**。單看字面比對的閘一律綠燈。
    """
    import shutil
    import tempfile

    # 自檢只打一支流派。六支跑滿 × 四輪 = 48 個 subprocess,在 Windows 上會把
    # 自檢拖過五分鐘,而這三案驗的是**探針本身的機制**,與流派無關。
    # 真實 repo 那一趟仍然六支跑滿。
    ONE = ("long",)
    src = Path(".").resolve()
    if not (src / ENGINE).is_file():
        return ["[D-self] 找不到真引擎,無法驗 probe 的紅端"]

    fails: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        shutil.copytree(src / "skills" / "fiction", root / "skills" / "fiction",
                        ignore=shutil.ignore_patterns("__pycache__"))
        rp = root / RULES

        if probe_self := enforcement_probe(root, ONE):                  # 13
            fails.append(f"13 綠端:原封引擎樹不該有話說,卻回 {probe_self[:2]}")

        orig = rp.read_text(encoding="utf-8")
        d = json.loads(orig)
        for g in FROZEN:
            d["idioms"]["genres"][g]["per_1000"] = [0, 999999]
        rp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        if not any("狀態欄與實跑不符" in x for x in enforcement_probe(root, ONE)):  # 14
            fails.append("14 紅端:上限被改成天文數字(規則還在但擋不住任何東西),"
                         "probe 沒戳破")

        # 15:**光改設定復活不了下限**——引擎裡 `lo, hi = band` 的 lo 解出來就丟掉,
        # 根本沒有下限那段程式。所以紅端必須把那段**注回去**,否則這條斷言
        # 就是一條沒有紅端的規則(KN-001 本人)。
        rp.write_text(orig, encoding="utf-8")
        ep = root / ENGINE
        src_txt = ep.read_text(encoding="utf-8")
        anchor = "            if d > hi:\n"
        if anchor not in src_txt:
            fails.append("15 紅端:引擎裡找不到成語上限的注入點 "
                         "`if d > hi:`——引擎換形狀了,本探針的紅端隨之失效,"
                         "**這比探針沒過更嚴重**")
        else:
            inject = ('            if d < lo:\n'
                      '                res["warnings"].append(\n'
                      '                    f"成語密度 {d:.1f}/千字,低於 {label} 的下限 {lo}")\n')
            ep.write_text(src_txt.replace(anchor, inject + anchor, 1), encoding="utf-8")
            d = json.loads(orig)
            for g in FROZEN:
                d["idioms"]["genres"][g]["per_1000"] = [FROZEN[g][2], FROZEN[g][3]]
            rp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            if not any("下限復活了" in x for x in enforcement_probe(root, ONE)):
                fails.append("15 紅端:下限被注回引擎且設定給了非 0 值,probe 沒戳破")
    return fails


def self_test() -> int:
    """紅綠端:每一條斷言都要有一個能讓它亮的合成案例。

    KN-001 的教訓:沒有紅端的規則,和引擎壞掉看起來一樣。
    """
    import tempfile
    full = {g: {"per_1000": [0, hi]} for g, (_, _, _, hi) in FROZEN.items()}
    fails: list[str] = []

    def run(rules, docs, want, label, forbid=None):
        # 合成樹裡沒有引擎,[D] 由 probe_self_test 另外驗——那條斷言的紅端
        # 必須打真引擎才有意義,拿假樹跑等於自己跟自己對答案。
        #
        # forbid:**不得誤掛的罪名**。只驗「有沒有紅」不夠——複審實測的兩個穿孔
        # 裡,有一個是修辭說謊時閘去掛了一條下限的罪名。抓錯人和沒抓到一樣壞。
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _tree(root, rules, docs)
            got = check(root, engine=False)
            hit = any(want in x for x in got) if want else not got
            if not hit:
                fails.append(f"{label}:want={want!r} got={got}")
            if forbid and any(forbid in x for x in got):
                fails.append(f"{label}:誤掛罪名 {forbid!r} got={got}")

    all_docs = {}
    for g, (lo_p, hi_p, lo_i, hi_i) in FROZEN.items():
        all_docs[f"skills/fiction-{g}/SKILL.md"] = (
            _GOOD_DOC.replace("25%-35%", f"{lo_p}%-{hi_p}%")
                     .replace("4-8 次/千字", f"{lo_i}-{hi_i} 次/千字"))

    run(full, all_docs, None, "1 綠端:六支齊全且誠實")                       # 1

    broken = json.loads(json.dumps(full)); broken["long"]["per_1000"] = [0, 9]
    run(broken, all_docs, "[A] long: 引擎上限", "2 引擎上限漂移")             # 2

    floor = json.loads(json.dumps(full)); floor["wuxia"]["per_1000"] = [3, 14]
    run(floor, all_docs, "下限成了 3", "3 下限被復活")                        # 3

    short = {g: v for g, v in full.items() if g != "scifi"}
    run(short, all_docs, "[A] 引擎少了流派 scifi", "4 引擎缺流派")             # 4

    extra = json.loads(json.dumps(full)); extra["horror"] = {"per_1000": [0, 5]}
    run(extra, all_docs, "多了凍結表沒有的流派 horror", "5 引擎多流派")        # 5

    gone = {k: v for k, v in all_docs.items() if "fiction-flash" not in k}
    run(full, gone, "[B] flash: 三處住址都找不到", "6 文案整支不見")           # 6

    drift = dict(all_docs)
    drift["skills/fiction-long/SKILL.md"] = _GOOD_DOC.replace("4-8 次", "4-9 次")
    run(full, drift, "成語密度", "7 文案數字漂移")                            # 7

    pdrift = dict(all_docs)
    pdrift["skills/fiction-long/SKILL.md"] = _GOOD_DOC.replace("25%-35%", "25%-36%")
    run(full, pdrift, "修辭比例", "8 修辭比例漂移")                           # 8

    _DISHONEST = _GOOD_DOC.replace(
        "lint 只擋上限;**下限不會被檢查**(引擎值為 0)", "lint 會數")

    dis = dict(all_docs)
    dis["commands/fiction-long.md"] = _DISHONEST
    run(full, dis, "[C]", "9 誠實欄:command 沒說下限不管")                    # 9

    rh = dict(all_docs)
    rh["commands/fiction-long.md"] = _GOOD_DOC.replace(
        "靠人判斷——沒有程式量得出一段文字有幾成是譬喻", "lint 會數")
    run(full, rh, "[C]", "10 誠實欄:command 沒說修辭比例靠人判斷")            # 10

    # 11:**同一段不誠實的文字,住址決定紅綠。** 這案同時證明兩件事:
    # 誠實欄真的只綁 command(裁決 4 的線),以及它不是靠關鍵字碰運氣
    # ——內容一字未改,只換了住址。
    ex = dict(all_docs)
    ex["skills/fiction-long/SKILL.md"] = _DISHONEST
    run(full, ex, None, "11 同一段文字放在待刪的舊 SKILL.md 應豁免")          # 11

    # 12:同一支流派住在兩處,其中一處漂了也要紅——只驗一處就是下一個孤兒
    two = dict(all_docs)
    two["commands/fiction-long.md"] = _GOOD_DOC.replace("4-8 次", "5-8 次")
    run(full, two, "commands/fiction-long.md", "12 並存住址其一漂移")

    # ---- 16、17 由複審(fable)的合成 probe 打出來:**兩個方向都能穿**。
    # 舊實作把整份文件當一個單元,於是一列說謊、另一列的用字替它擔保。
    # 這兩案各自把一列改成謊話、另一列保持誠實,所以跨列支援一旦復活就會紅。

    # 16:成語那列**正面說謊**(說下限也會擋)。修辭列維持誠實,
    #     所以舊實作會被它跨列滿足而放行——實測綠燈。
    lie_floor = dict(all_docs)
    lie_floor["commands/fiction-long.md"] = _GOOD_DOC.replace(
        "lint 只擋上限;**下限不會被檢查**(引擎值為 0)",
        "上限與下限都會擋,低於下限一樣紅")
    run(full, lie_floor, "沒說「下限沒有機器在管」",
        "16 成語列對下限說謊(修辭列誠實,不得替它擔保)",
        forbid="修辭比例卻沒說")                                              # 16

    # 17:修辭那列說謊。成語列維持誠實。除了要紅,**還不得誤掛下限的罪名**
    #     ——舊實作在這個方向上不但沒抓到謊,反而掛錯了人。
    lie_rh = dict(all_docs)
    lie_rh["commands/fiction-long.md"] = _GOOD_DOC.replace(
        "靠人判斷——沒有程式量得出一段文字有幾成是譬喻", "lint 會量")
    run(full, lie_rh, "修辭比例卻沒說",
        "17 修辭列說謊(成語列誠實,不得替它擔保)",
        forbid="沒說「下限沒有機器在管」")                                     # 17

    fails += probe_self_test()

    if fails:
        for f in fails:
            print(f"  ❌ {f}")
        print("\n✗ self-test 未通過:配比凍結閘的紅綠端不可達。")
        return 1
    print("✅ self-test:17 案全過——設定四條(上限漂移/下限復活/缺流派/多流派)、"
          "文案四條(整支不見/成語漂移/修辭漂移/並存住址其一漂移)、"
          "誠實欄五條(下限、修辭、豁免,加上**兩個方向的說謊**且不得誤掛罪名)、"
          "綠端一條,以及 [D] 執法探針三條"
          "(原封綠端 / 上限被架空 / 下限被注回引擎)。")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    root = Path(".").resolve()
    if "--repo" in argv:
        root = Path(argv[argv.index("--repo") + 1]).resolve()
    # 誠實欄沒有旗標:它依住址判定(見 is_command)。沒有旗標就沒有「未驗」狀態,
    # 而未驗與通過在 CI 輸出裡長得一樣——這個 repo 已經為那件事付過一次代價。
    bad = check(root)
    if bad:
        print(f"✗ 配比凍結閘(基準 ref {FROZEN_REF}):")
        for b in bad:
            print("  - " + b)
        print("\n  凍結表寫死在 scripts/genre_ratio_freeze.py。數值真要改,"
              "\n  是一次帶 CHG 的登記變更,不是把基準改到能通過。")
        return 1
    cmds = sum(1 for g in FROZEN for d in live_docs(root, g)
               if is_command(d.relative_to(root).as_posix()))
    print(f"✅ 配比凍結閘:{len(FROZEN)} 支流派 × 三欄與 ref {FROZEN_REF} 一致;"
          f"誠實欄驗到 {cmds} 個 command 檔")
    for k, col in (("rhetoric", "修辭比例"), ("idiom_hi", "成語上限"),
                   ("idiom_lo", "成語下限")):
        print(f"   {col}:{STATUS[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
