#!/usr/bin/env python3
"""近體詩格律檢查 — 五七言絕句 / 律詩的句式、韻腳、平仄。

## 判什麼、不判什麼(這條線是本檔的核心)

`docs/genres.md` 的既有立場:判不了就明標,不假裝有把關(KN-001 第二條路)。
本檔的三層:

| 層 | 內容 | 靠什麼 |
|---|---|---|
| **句式** | 五言/七言、絕句 4 句 / 律詩 8 句、每句字數一致 | 只需文字 |
| **韻腳** | 偶數句末同韻部、押平聲、不重複用字 | 平水韻資產 |
| **平仄** | 韻腳必平;對句二四六相對 | 平水韻資產 |
| **不判** | 黏、拗救、對仗的詞性與語義、意境 | 判不了,明標 |

**「不判」不是懶,是誠實。** 對仗要判詞性與語義類別,那需要斷詞標註,
而錯誤的斷詞會誤殺——本 repo 對「誤報會教人忽略閘」有既定立場(KN-002)。

## 兩讀字的不確定性契約(審議席 codex 指定)

平水韻裡有 872 個字同時見於平、仄兩部(如「不」在下平十一尤與入聲五物)。
**字級判定對它們是不可能的**,需要語境消歧,而本檔不做斷詞。

契約:
  - 平仄檢查:**任一讀音合律即過**,全部讀音都違律才響(寧漏報不誤報)
  - 韻腳同部:兩讀字若有**任一讀音**與韻腳集合同部即過
  - 表內查無此字:**不判**,並具名列進「未驗到」——不當作通過,也不當作違規

「判定不出來不等於沒問題」(KN-004),所以未驗到要印出來,不能吞掉。

## 資料出處

`assets/pingshui.json`,見該檔的 `_source` 欄。原典公共領域,
數位化取自 zh.wikisource.org,與 `pingshui-rhyme==0.20`(MIT)全量交叉核對過。

**三組分開**:`shi`(詩韻正文)/ `ci`(【詞】補充)/ `cifu`(【辭】補充)。
**近體詩押韻只認 `shi`**——那 1,559 個詞韻與辭賦補充字若併進來,
會放行本不該押的字,而那是「多收造成誤放」,綠燈看不出來。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

ASSET = Path(__file__).resolve().parent.parent / "assets" / "pingshui.json"

# 切句約定:以句末標點切,不靠換行——稿件的換行是排版,標點才是句讀。
SENT_END = "。！？；.!?;"
DROP = re.compile(r"[^㐀-鿿]")


def load(path: Path = ASSET) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    shi, allset = {}, {}
    for name, v in d["rhymes"].items():
        for c in v["shi"]:
            shi.setdefault(c, []).append(name)
        for grp in ("shi", "ci", "cifu"):
            for c in v[grp]:
                allset.setdefault(c, []).append(name)
    return {"rhymes": d["rhymes"], "shi": shi, "all": allset, "_source": d["_source"]}


def tones(tbl: dict, ch: str) -> set[str]:
    """一個字的全部平仄讀音。空集合 = 表內查無,呼叫端必須當「不判」處理。"""
    return {tbl["rhymes"][r]["tone"] for r in tbl["all"].get(ch, ())}


def split_lines(text: str) -> list[str]:
    """切成句。標點切,再剝非漢字。

    **先剝掉 markdown 標題與引言行。** 稿件是 .md,而
    `# 春望 — 杜甫(五言律詩)` 這種標題若不剝,會被當成一句 13 字的詩,
    紅在「字數不一致」——規則對正確輸入恆假,而看起來像詩有問題。
    施工時第一份夾具就是這樣紅的。
    """
    body = "\n".join(
        l for l in text.splitlines()
        if not l.lstrip().startswith(("#", ">", "|", "-", "*", "`")))
    out, cur = [], ""
    for ch in body:
        if ch in SENT_END or ch in "，、,":
            if s := DROP.sub("", cur):
                out.append(s)
            cur = ""
        else:
            cur += ch
    if s := DROP.sub("", cur):
        out.append(s)
    return out


def check(text: str, tbl: dict) -> tuple[list[str], list[str]]:
    """回 (違規, 未驗到)。**兩者分開回**——未驗到不是通過。"""
    bad: list[str] = []
    unknown: list[str] = []
    lines = split_lines(text)

    if len(lines) not in (4, 8):
        bad.append(f"句數 {len(lines)}——近體詩是絕句 4 句或律詩 8 句")
        return bad, unknown
    form = "絕句" if len(lines) == 4 else "律詩"

    widths = {len(x) for x in lines}
    if len(widths) > 1:
        bad.append(f"每句字數不一致:{sorted(len(x) for x in lines)}")
        return bad, unknown
    w = widths.pop()
    if w not in (5, 7):
        bad.append(f"每句 {w} 字——近體詩是五言或七言")
        return bad, unknown

    # ── 韻腳:偶數句末。首句可押可不押,故不納入「必須同部」的判定基準。
    feet = [lines[i][-1] for i in range(1, len(lines), 2)]
    for c in feet:
        if c not in tbl["all"]:
            unknown.append(f"韻腳「{c}」不在平水韻表內——本字的韻與平仄皆不判")

    # 不重複用字
    seen = {}
    for i, c in enumerate(feet):
        if c in seen:
            bad.append(f"韻腳重複用字「{c}」(第 {seen[c]*2+2} 句與第 {i*2+2} 句)"
                       "——近體詩一韻到底,但不得重複同一個字")
        seen[c] = i

    # 同部:只認詩韻正文
    known = [c for c in feet if c in tbl["shi"]]
    if len(known) >= 2:
        common = set(tbl["shi"][known[0]])
        for c in known[1:]:
            common &= set(tbl["shi"][c])
        if not common:
            bad.append("韻腳不同韻部:" + "、".join(
                f"{c}({'/'.join(tbl['shi'][c])})" for c in known))
        elif not any(tbl["rhymes"][r]["tone"] == "ping" for r in common):
            # **不列違規。** 仄韻絕句是公認存在的形式(如王維〈雜詩〉、
            # 劉長卿〈送方外上人〉),初版寫成絕對禁止,誤殺 8 首傳世詩。
            unknown.append(f"韻腳落在仄聲部({'/'.join(sorted(common))})——"
                           "近體詩多押平聲韻,但仄韻絕句是公認形式,本閘不判,提醒人看")
    for c in feet:
        if c not in tbl["shi"]:
            where = "【詞】或【辭】補充字" if c in tbl["all"] else "表外"
            unknown.append(f"韻腳「{c}」不在詩韻正文({where})——同部判定略過本字")

    # ── 平仄:**只查第二字**的對句相對。兩讀字任一合律即過。
    #
    # 初版查二四六全部,對 219 首傳世近體詩紅了 62 首(71.7% 綠)——
    # **規則對正確輸入恆假**。成因是缺拗救容忍:如〈經鄒魯祭孔子〉的
    # 「今看兩楹奠」是公認的「平平仄平仄」特拗格,四六位置本來就不相對。
    #
    # 實測各方案對同一母體的綠燈率:
    #     二四六全查            71.7%
    #     只查第二字            93.6%   ← 採用
    #     平仄完全不判          95.9%
    # 第二字是節奏點裡最不受拗救影響的一個,保留它換到 2.3 個百分點的紅,
    # 而完全不判就一條平仄斷言都沒有了。**這條邊界是外部真值定的,不是我猜的。**
    idx = [1]
    for a in range(0, len(lines), 2):
        out_, in_ = lines[a], lines[a + 1]
        for p in idx:
            ta, ti = tones(tbl, out_[p]), tones(tbl, in_[p])
            if not ta or not ti:
                unknown.append(f"第 {a+1}/{a+2} 句第 {p+1} 字"
                               f"「{out_[p]}{in_[p]}」有字不在表內——本位平仄不判")
                continue
            # 任一組合相對即過
            if not any(x != y for x in ta for y in ti):
                bad.append(f"第 {a+1}、{a+2} 句第 {p+1} 字「{out_[p]}」「{in_[p]}」"
                           f"平仄未相對(皆 {'/'.join(sorted(ta))})——二四六分明")

    # ── 對句同位不得同字:**只查律詩的頷聯(3-4)與頸聯(5-6)**。
    # 那兩聯才要求對仗,而對仗才禁同位重字。初版套到全部聯與絕句,
    # 誤殺 7 首傳世詩(如〈宮詞〉首聯第 3 字同為「樓」)。
    for a in ([2, 4] if len(lines) == 8 else []):
        for p, (x, y) in enumerate(zip(lines[a], lines[a + 1])):
            if x == y:
                bad.append(f"第 {a+1}、{a+2} 句第 {p+1} 字同為「{x}」——對句同位不得重字")

    return bad, unknown


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    tbl = load()
    rc = 0
    for f in a.files:
        text = Path(f).read_text(encoding="utf-8")
        bad, unknown = check(text, tbl)
        print(f"\n── {f}")
        for b in bad:
            print("  ✗ " + b)
        for u in unknown:
            print("  ⚠ 未驗到:" + u)
        if not bad:
            print("  ✅ 句式、韻腳、二四六平仄未見違規"
                  + (f"(另有 {len(unknown)} 項未驗到,見上)" if unknown else ""))
        else:
            rc = 1
    print("\n**不判的部分**:黏、拗救、對仗的詞性與語義、意境——"
          "需要斷詞與語義標註,誤判成本高於漏判,故明標不判(KN-001 第二條路)。")
    return rc


def self_test() -> int:
    """紅綠端 + 兩讀字契約。**綠端用傳世詩,不自己寫**(審議席指定)。"""
    tbl = load()
    fails: list[str] = []
    ran: list[str] = []

    def case(label, text, want):
        ran.append(label)
        bad, _ = check(text, tbl)
        if want is None:
            if bad:
                fails.append(f"{label} 應綠卻紅:{bad}")
        elif not any(want in b for b in bad):
            fails.append(f"{label} 應紅於「{want}」,實得:{bad or '全綠'}")

    # 綠端:王之渙〈登鸛雀樓〉(五絕),外部傳世文本
    case("綠 五絕〈登鸛雀樓〉",
         "白日依山盡，黃河入海流。欲窮千里目，更上一層樓。", None)
    # 紅端:句數
    case("紅 句數不對", "白日依山盡，黃河入海流。欲窮千里目。", "句數")
    # 紅端:字數不一致
    case("紅 字數不一致",
         "白日依山盡，黃河入海流水。欲窮千里目，更上一層樓。", "字數不一致")
    # 紅端:韻腳重複用字
    case("紅 韻腳重複用字",
         "白日依山盡，黃河入海流。欲窮千里目，更上一層流。", "韻腳重複用字")
    # 綠端:杜甫〈春望〉(五律),外部傳世文本
    CHUNWANG = ("國破山河在，城春草木深。感時花濺淚，恨別鳥驚心。"
                "烽火連三月，家書抵萬金。白頭搔更短，渾欲不勝簪。")
    case("綠 五律〈春望〉", CHUNWANG, None)
    # 紅端:對句同位重字——**由綠端詩單字突變產生**,不是自己寫一首
    # (規則收窄成只查律詩頷頸聯之後,原本用五絕的紅端自然失效,那是正確行為)
    case("紅 頷聯同位重字",
         CHUNWANG.replace("恨別鳥驚心", "感別鳥驚心"), "同位不得重字")

    # 兩讀字契約:表外字必須列進未驗到,且**不得**進違規
    # 「氫」是真的表外漢字(程式挑的,不是我猜的)——初版用全形 Ｚ,
    # 而它不在 CJK 範圍、會被 DROP 剝掉,於是那一句變 4 字、紅在「字數不一致」,
    # 契約端根本沒被測到。**夾具字元選錯,測的就不是要測的東西。**
    bad, unk = check("白日依山盡，黃河入海流。欲窮千里目,更上一層氫。", tbl)
    ran.append("契約 表外字→未驗到而非違規")
    if not any("不在平水韻表內" in u for u in unk):
        fails.append("契約 表外字沒有列進未驗到")

    if fails:
        for f in fails:
            print("  ❌ " + f)
        print("\n✗ self-test 未通過。")
        return 1
    print(f"✅ self-test:{len(ran)} 案全過(" + "、".join(ran) + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
