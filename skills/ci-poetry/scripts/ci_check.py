#!/usr/bin/env python3
"""宋詞格律檢查 — 依白香詞譜之體,判句式、韻組與平仄。

## 判什麼、不判什麼

| 判 | 不判(明標) |
|---|---|
| 啟用牌的句數、每句字數(對照譜) | 未啟用牌 → 「非本工具所收白香體/未判定」 |
| 韻組(`△▲` run)內是否同詞林部 | 同牌異體(欽定詞譜 2304 體) |
| `○●` 位置的平仄(`⊙` 一律放行) | 換韻的合法性、通叶「平仄兩組須同部」 |
| | 領字、去聲位、片界 |

**「未收之體」不是違規。** 使用者填的若是欽定詞譜收而白香未收的體,
輸出「非本工具所收白香體/未判定」——不是報錯、不硬猜最近的牌。
誤殺會教人忽略這道閘(KN-002)。

## 三席定案的兩條核心規則

### 一、聲類三分:平 / 上去 / 入

**上去通押、入聲獨押。** 證據在來源結構本身:詞林正韻第 1–14 部一律
`平聲:…通用` ∥ `仄聲:上聲…去聲…通用`(上去同節);第 15–19 部一律
`入聲:…通用`(獨立成部、獨立標頭,無一例外)。**這不是學術意見,是戈載的分部結構。**

`▲` 位在 `上去 ∪ 入` 聯集域求共同部。非橋接字不可能跨舒入,混押組天然無共同部,
**殘餘誤放面恰好是 47 個橋接字**(名單在 `cilin.json` 的 `_stats.bridge_chars`)。

這個數字一度是 50,而多出來的 `上、下、木` **是資料污染造的假橋接**:
字形結構模板 `{{!|𣘼|上「啟」下「木」}}` 的描述文字被當韻字收進表。
實測假綠是 `▲ 組「月發閱上」全綠`——**污染剛好落在誤放面宣稱安全的正中央**。
守恆閘當時是綠的,因為 `assets_verify.py` 的 raw parser 犯同一個錯:**一起錯就是一致**。

**不採「依詞牌要求選上去或入」**——白香的 `▲` 不分域,「某牌要求入聲韻」是
欽定詞譜層級的外部知識,造它就踩了「禁止自行造規則資料」的紅線。

### 二、韻組按連續同符號 run 切,同符號再現另起新組

菩薩蠻若把整首的 `△` 併成一組會**假陽性**:

    ▲織碧(十七部)  △樓愁(十二部)  ▲立急(十七部)  △程亭(十一部)

四組各自成部,而 pooled `△` 的「樓愁程亭」無共同部——**那是換韻,不是違規**。
組內求共同部,**組間完全不比較**。

## 名家範例也可能不合後世韻書

白香收的念奴嬌範例詞(**薩都剌〈登石頭城〉**)`▲` 組為 物壁雪傑發滅發月,
其中 `壁` 屬第十七部、其餘七字屬第十八部——**入聲寬押的實例**;
它另有第 20 句第 3 字「一」譜為 `○` 而實屬入聲。九個啟用牌的譜例只有它不全綠。

所以診斷文案是「**依詞林正韻無共同部**」,不是「錯」;
而驗收線**不訂「名家範例 100% 通過」**,改訂:全樣本必須完成判定且無靜默未驗、
每個不通過案例必須可重現並列出逐字部屬、版本更新不得新增未解釋的退步。
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

ASSETS = Path(__file__).resolve().parent.parent / "assets"
# **Ext-B 也要收**,而且要與 `cilin.json` 的 `_template_strip.cjk_class_now` 同一個類別。
# 上一輪只加寬了 `assets_verify.py` 與建置側,**漏了這裡**:於是 𣘼 在韻表裡查得到,
# 而使用者稿裡寫 𣘼 會被 `lines_of` 靜默丟字,誤紅成「第 4 句 5 字,譜為 6 字」——
# **表裡有、引擎永遠讀不到。修正沒落完整,比沒修更難發現。**
CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0003ffff]")
# **只剝真正的 Markdown 結構。** 舊版把行首的 `-` `*` 也算結構,
# 於是「詞寫成清單」整首被剝光(誤紅句數 0)、行首當裝飾的 `-` 整行蒸發。
# 引擎既宣稱讀 `.md`,就不能把常見 Markdown 表達誤當正文或刪掉正文(KN-002)。
MD = ("#", ">", "|", "`")
# 清單項:**去掉 marker、保留內容**。marker 後必須有空白,
# 沒有空白的行首 `-`／`*` 一律當正文(它不是漢字,`CJK` 過濾自然會丟掉)。
LIST = re.compile(r"^\s*[-*+]\s+")


def load() -> dict:
    bx = json.loads((ASSETS / "baixiang.json").read_text(encoding="utf-8"))
    cl = json.loads((ASSETS / "cilin.json").read_text(encoding="utf-8"))
    idx: dict[str, set[tuple[str, str]]] = {}
    for pn, p in cl["parts"].items():
        for r in p["rhymes"].values():
            for ch in r["chars"]:
                idx.setdefault(ch, set()).add((pn, r["tone"]))
    return {"tunes": bx["tunes"], "enabled": set(bx["_enabled"]["list"]),
            "idx": idx, "bx": bx, "cl": cl}


def parts_in(tbl: dict, ch: str, domain: set[str]) -> set[str]:
    """該字在指定聲類域內所屬的部。空集合 = 域內查無。"""
    return {pn for pn, tone in tbl["idx"].get(ch, ()) if tone in domain}


def rhyme_runs(rows: list[dict]) -> list[tuple[str, list[str]]]:
    """按**連續同符號 run** 切韻組。同符號再次出現另起新組。"""
    out: list[tuple[str, list[str]]] = []
    cur, buf = None, []
    for r in rows:
        for ch, t in zip(r["chars"], r["tones"]):
            if t not in "△▲":
                continue
            if t != cur:
                if buf:
                    out.append((cur, buf))
                cur, buf = t, []
            buf.append(ch)
    if buf:
        out.append((cur, buf))
    return out


def lines_of(text: str) -> list[str]:
    """切句。**標題請用 `#` 開頭**——這是輸入契約,寫在 SKILL.md。

    無標點又無 `#` 前綴的標題行(如 `清平樂・晚春`)會併進第一句,
    誤紅成「第 1 句 9 字」——**紅在錯的地方,使用者會去改沒錯的首句**。
    自動辨識它需要「首行短、含詞牌名」這類猜測,那會新增誤殺面,
    所以改用明確契約收口,不猜。
    """
    body = "\n".join(LIST.sub("", l) for l in text.splitlines()
                     if not l.lstrip().startswith(MD))
    out, cur = [], ""
    for ch in body:
        if ch in "。！？；，、,.!?;":
            if s := "".join(CJK.findall(cur)):
                out.append(s)
            cur = ""
        else:
            cur += ch
    if s := "".join(CJK.findall(cur)):
        out.append(s)
    return out


DOMAIN = {"△": {"平"}, "▲": {"上去", "入"}}


def check(tune: str, text: str, tbl: dict) -> tuple[list[str], list[str]]:
    """回 (違規, 未判定)。**未判定不是通過,也不是違規。**"""
    bad: list[str] = []
    unk: list[str] = []

    if tune not in tbl["tunes"]:
        unk.append(f"「{tune}」非本工具所收白香詞譜之調——未判定")
        return bad, unk
    if tune not in tbl["enabled"]:
        why = ("該調在資產中逐行對齊未通過(來源缺字),未啟用"
               if not tbl["tunes"][tune]["aligned"] else "該調不在首發啟用名單")
        unk.append(f"「{tune}」{why}——非本工具所收白香體,未判定")
        return bad, unk

    spec = tbl["tunes"][tune]["rows"]
    got = lines_of(text)
    if len(got) != len(spec):
        bad.append(f"句數 {len(got)},白香〈{tune}〉之體為 {len(spec)} 句"
                   "——**不硬對齊**,請確認是否為同一體")
        return bad, unk
    for i, (g, s) in enumerate(zip(got, spec), 1):
        if len(g) != len(s["chars"]):
            bad.append(f"第 {i} 句 {len(g)} 字,譜為 {len(s['chars'])} 字:「{g}」")
    if bad:
        return bad, unk

    # ── 平仄:⊙ 一律放行 ──
    for i, (g, s) in enumerate(zip(got, spec), 1):
        for j, (ch, t) in enumerate(zip(g, s["tones"]), 1):
            if t == "⊙":
                continue
            want = {"○": {"平"}, "●": {"上去", "入"}, "△": {"平"},
                    "▲": {"上去", "入"}}[t]
            have = {tone for _, tone in tbl["idx"].get(ch, ())}
            if not have:
                unk.append(f"第 {i} 句第 {j} 字「{ch}」不在詞林正韻表內——本位不判")
            elif not (have & want):
                bad.append(f"第 {i} 句第 {j} 字「{ch}」譜為 {t},實為 {'/'.join(sorted(have))}")

    # ── 韻組:run 內求共同部,組間不比較 ──
    # **這裡必須呼叫 `rhyme_runs()`,不可再內聯一份。** 初版兩處各有一份切法,
    # 於是 self-test 的 run 回歸打在**引擎不用的那一份**上:審議席實測把
    # `check()` 的內聯版改成「只併 ▲、保留 △」,self-test 八案全過、CI 夾具全綠,
    # 而正確的虞美人譜例當場假陽性。**兩份實作,測到的永遠是沒人跑的那份。**
    runs = rhyme_runs([{"chars": g, "tones": s["tones"]}
                       for g, s in zip(got, spec)])

    for k, (sym, chars) in enumerate(runs, 1):
        dom = DOMAIN[sym]
        known = [c for c in chars if parts_in(tbl, c, dom)]
        for c in chars:
            if not parts_in(tbl, c, dom):
                unk.append(f"韻組 {k}({sym})的「{c}」在{'/'.join(sorted(dom))}域內查無——本字不判")
        if len(known) < 2:
            continue
        common = set.intersection(*(parts_in(tbl, c, dom) for c in known))
        if not common:
            detail = "、".join(f"{c}({'/'.join(sorted(parts_in(tbl, c, dom)))})" for c in known)
            bad.append(f"韻組 {k}({sym})依詞林正韻無共同部:{detail}")
    return bad, unk


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="宋詞格律檢查(白香詞譜之體)")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--tune", help="詞牌名")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    tbl = load()
    rc = 0
    for f in a.files:
        bad, unk = check(a.tune or "", Path(f).read_text(encoding="utf-8"), tbl)
        print(f"\n── {f}({a.tune or '未指定詞牌'})")
        for b in bad:
            print("  ✗ " + b)
        for u in unk:
            print("  ⚠ 未判定:" + u)
        if not bad and not unk:
            print("  ✅ 句式、韻組同部、平仄未見違規")
        elif not bad:
            print(f"  ✅ 未見違規(另有 {len(unk)} 項未判定,見上)")
        else:
            rc = 1
    print("\n**不判的部分**:同牌異體、換韻合法性、通叶「平仄兩組須同部」、"
          "領字、去聲位、片界——判不了的不假裝有把關。")
    return rc


def self_test() -> int:
    tbl = load()
    fails: list[str] = []
    ran: list[str] = []

    def spec_text(tune: str) -> str:
        return "，".join(r["chars"] for r in tbl["tunes"][tune]["rows"]) + "。"

    def case(label, tune, text, want_bad=None, want_unk=None):
        ran.append(label)
        bad, unk = check(tune, text, tbl)
        if want_bad is None and want_unk is None:
            if bad:
                fails.append(f"{label} 應綠卻紅:{bad}")
        if want_bad and not any(want_bad in b for b in bad):
            fails.append(f"{label} 應紅於「{want_bad}」,實得:{bad or '全綠'}")
        if want_unk and not any(want_unk in u for u in unk):
            fails.append(f"{label} 應未判定於「{want_unk}」,實得:{unk or '無'}")
        if want_unk and bad:
            fails.append(f"{label} 未判定的情形**不得同時報違規**:{bad}")

    # 1 未收牌名 → 未判定,不是報錯
    case("1 未收牌名→未判定", "水龍吟無此調", "隨便幾個字。", want_unk="非本工具所收")
    # 2 未啟用牌 → 未判定
    case("2 未啟用牌→未判定", "一斛珠", spec_text("菩薩蠻"), want_unk="未判定")
    # 3 句數不符 → 不硬對齊
    case("3 句數不符", "菩薩蠻", "平林漠漠煙如織。", want_bad="句數")
    # 4 某句字數不符
    t = tbl["tunes"]["菩薩蠻"]["rows"]
    bads = "，".join((r["chars"] + "多") if i == 0 else r["chars"]
                    for i, r in enumerate(t)) + "。"
    case("4 某句字數不符", "菩薩蠻", bads, want_bad="第 1 句")
    # 5 綠端:譜例詞自己過檢
    case("5 綠 菩薩蠻譜例", "菩薩蠻", spec_text("菩薩蠻"))
    # 6 回歸:換韻牌四組分別判(pooled 會假陽性)
    ran.append("6 回歸 菩薩蠻四韻組")
    runs = rhyme_runs(tbl["tunes"]["菩薩蠻"]["rows"])
    if len(runs) != 4:
        fails.append(f"6 菩薩蠻應切出 4 個韻組,實得 {len(runs)}")
    else:
        for k, (sym, chars) in enumerate(runs, 1):
            common = set.intersection(*(parts_in(tbl, c, DOMAIN[sym]) for c in chars))
            if not common:
                fails.append(f"6 韻組 {k}({sym}){''.join(chars)} 無共同部")
        pooled = [c for sym, ch in runs if sym == "△" for c in ch]
        if set.intersection(*(parts_in(tbl, c, {"平"}) for c in pooled)):
            fails.append("6 pooled △ 竟有共同部——那道回歸夾具測不到 run 切法")
    # 6b **▲ 側也要有 run 回歸**,而綠端必須是「▲ 換到不同仄部」的牌。
    #    菩薩蠻兩個 ▲ run 都是第十七部,pool 起來仍有共同部——所以只用它時,
    #    「只併 ▲、保留 △」的突變照樣八案全過。虞美人是現成的反例:
    #    了少(第八部)/ 在改(第五部),pool 起來必紅。
    case("6b 綠 虞美人譜例(▲ 換到不同仄部)", "虞美人", spec_text("虞美人"))
    ran.append("6c 反向 虞美人 pooled ▲ 必須無共同部")
    yruns = rhyme_runs(tbl["tunes"]["虞美人"]["rows"])
    ypool = [c for sym, ch in yruns if sym == "▲" for c in ch]
    if sum(1 for sym, _ in yruns if sym == "▲") < 2:
        fails.append("6c 虞美人應有 ≥2 個 ▲ run,否則這條反向斷言測不到 ▲ 側的 run 切法")
    elif set.intersection(*(parts_in(tbl, c, DOMAIN["▲"]) for c in ypool)):
        fails.append("6c pooled ▲ 竟有共同部——▲ 側的 run 切法就算寫錯也照樣綠")
    # 7 回歸:念奴嬌譜例的**兩處**紅都要 pin(已知診斷,非「錯」)
    #   只 pin 韻組那處不夠:那第二處是全測試面唯一的平仄紅,
    #   審議席實測把整段 ○● 檢查刪掉,self-test 八案照樣全過、CI 夾具照樣全綠。
    #   **一條規則可以被整段刪除而沒有任何測試發現,那條規則等於沒有被測。**
    ran.append("7 已知診斷 念奴嬌譜例兩處紅(韻組跨部 + 平仄「一」)")
    bad7, _ = check("念奴嬌", spec_text("念奴嬌"), tbl)
    if not any("無共同部" in b for b in bad7):
        fails.append("7 念奴嬌譜例應報無共同部(壁 17 / 其餘 18),實得:" + str(bad7))
    if not any("「一」譜為 ○" in b for b in bad7):
        fails.append("7 念奴嬌第 20 句第 3 字「一」的平仄紅未出現"
                     "——**整段平仄檢查失去負控**,實得:" + str(bad7))
    if any("錯" in b for b in bad7):
        fails.append("7 診斷文案不得出現「錯」字——名家範例不合後世韻書不是作品的錯")
    # 8 域內帶正控(禁全域缺席斷言)
    ran.append("8 域內正控 間∉第一部 且 間∈第七部")
    if "第一部" in {p for p, _ in tbl["idx"].get("間", ())}:
        fails.append("8 「間」出現在第一部——釋義污染回歸")
    if "第七部" not in {p for p, _ in tbl["idx"].get("間", ())}:
        fails.append("8 「間」不在第七部——正控失敗,斷言退化成全域缺席")
    # 9 字形結構模板污染回歸
    #   舊版把 `{{!|𣘼|上「啟」下「木」}}` 的**描述文字**當韻字收進表,
    #   於是「上」被污染出一個第十八部入聲身分——而橋接字正是「入聲獨押」
    #   宣稱的殘餘誤放面,污染落在它的正中央。真字 𣘼 𦶟 反被丟(CJK 類別不含 Ext-B)。
    ran.append("9 模板污染回歸 上/下無入聲、木無上去,且 𣘼/𦶟 在表內")
    for c in "上下":
        if any(t == "入" for _, t in tbl["idx"].get(c, ())):
            fails.append(f"9 「{c}」帶入聲身分——字形結構模板污染回歸")
    if any(t == "上去" for _, t in tbl["idx"].get("木", ())):
        fails.append("9 「木」帶上去身分——字形結構模板污染回歸")
    for c in "𣘼𦶟":
        if not tbl["idx"].get(c):
            fails.append(f"9 「{c}」不在表內——正控失敗,"
                         "斷言退化成「模板整段被丟掉也算過」")
    # 10 `lines_of` 三個誤判輸入(審議席實測,codex 裁為「既有宣稱的瑕疵」)
    qp = tbl["tunes"]["清平樂"]["rows"]
    plain = "，".join(r["chars"] for r in qp) + "。"
    ran.append("10a 詞寫成 md 清單 → 去 marker 保留內容,不得剝光")
    listed = "\n".join("- " + r["chars"] + "，" for r in qp)
    if len(lines_of(listed)) != len(qp):
        fails.append(f"10a 清單型輸入應切出 {len(qp)} 句,實得 {len(lines_of(listed))}"
                     "——整首被剝光就是誤紅句數 0")
    ran.append("10b 行首半形 - 當裝飾 → 整行不得蒸發")
    deco = "\n".join("-" + r["chars"] + "，" for r in qp)
    if len(lines_of(deco)) != len(qp):
        fails.append(f"10b 行首無空白的 `-` 應當正文,實得 {len(lines_of(deco))} 句")
    ran.append("10c 正控:`# 標題` 仍必須被剝掉")
    if len(lines_of("# 清平樂 — 黃庭堅\n" + plain)) != len(qp):
        fails.append("10c `#` 標題沒被剝掉——正控失敗,10a/10b 退化成「什麼都不剝」")
    # 10d 是**已知限制的快照**,不是綠端:無標點又無 `#` 的標題行會併進第一句。
    #     壞的不是句數(句數不變),是第一句的內容——所以斷言必須打在內容上。
    #     我第一版斷在句數上,它恆真,測不到它宣稱測的東西。
    ran.append("10d 已知限制快照:無標點且無 `#` 的標題行會併進第一句")
    got10 = lines_of("清平樂・晚春\n" + plain)
    if got10[0] == qp[0]["chars"]:
        fails.append("10d 這一案已能正確切句——SKILL.md 的輸入契約說明過時了,要一起改")
    elif got10[0] != "清平樂晚春" + qp[0]["chars"]:
        fails.append(f"10d 併法與記載不符:實得「{got10[0]}」——限制的形狀變了,敘述要跟著改")
    # 10e Ext-B 罕字不得被 `lines_of` 靜默丟掉——**表裡有,引擎就要讀得到**
    ran.append("10e Ext-B 正控 𣘼 進得了 lines_of,不被靜默丟字")
    if lines_of("喚取歸來同𣘼。") != ["喚取歸來同𣘼"]:
        fails.append("10e 「𣘼」被 lines_of 丟掉——`CJK` 類別與資產側不同步,"
                     f"實得 {lines_of('喚取歸來同𣘼。')}")
    if not tbl["idx"].get("𣘼"):
        fails.append("10e 「𣘼」不在韻表——正控失敗,斷言退化成「兩邊都沒有也算同步」")
    ran.append("9b 假綠實例 月發閱上 必須無共同部")
    if not parts_in(tbl, "上", {"上去"}):
        fails.append("9b 「上」在上去域內查無——正控失敗")
    else:
        k9 = [c for c in "月發閱上" if parts_in(tbl, c, DOMAIN["▲"])]
        if set.intersection(*(parts_in(tbl, c, DOMAIN["▲"]) for c in k9)):
            fails.append("9b 「月發閱上」竟有共同部——入聲獨押沒有真的落地")

    if fails:
        for f in fails:
            print("  ❌ " + f)
        print("\n✗ self-test 未通過。")
        return 1
    print(f"✅ self-test:{len(ran)} 案全過\n   " + "\n   ".join(ran))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
