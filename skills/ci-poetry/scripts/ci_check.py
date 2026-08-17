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
**殘餘誤放面恰好是 50 個橋接字**(名單在 `cilin.json` 的 `_stats.bridge_chars`)。

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
CJK = re.compile(r"[㐀-鿿]")
MD = ("#", ">", "|", "-", "*", "`")


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
    body = "\n".join(l for l in text.splitlines()
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
    pos = 0
    flat = [(ch, t) for g, s in zip(got, spec) for ch, t in zip(g, s["tones"])]
    runs, cur, buf = [], None, []
    for ch, t in flat:
        if t not in "△▲":
            continue
        if t != cur:
            if buf:
                runs.append((cur, buf))
            cur, buf = t, []
        buf.append(ch)
    if buf:
        runs.append((cur, buf))

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
    # 7 回歸:念奴嬌譜例依詞林無共同部(已知診斷,非「錯」)
    ran.append("7 已知診斷 念奴嬌譜例跨十七/十八部")
    bad7, _ = check("念奴嬌", spec_text("念奴嬌"), tbl)
    if not any("無共同部" in b for b in bad7):
        fails.append("7 念奴嬌譜例應報無共同部(壁 17 / 其餘 18),實得:" + str(bad7))
    if any("錯" in b for b in bad7):
        fails.append("7 診斷文案不得出現「錯」字——名家範例不合後世韻書不是作品的錯")
    # 8 域內帶正控(禁全域缺席斷言)
    ran.append("8 域內正控 間∉第一部 且 間∈第七部")
    if "第一部" in {p for p, _ in tbl["idx"].get("間", ())}:
        fails.append("8 「間」出現在第一部——釋義污染回歸")
    if "第七部" not in {p for p, _ in tbl["idx"].get("間", ())}:
        fails.append("8 「間」不在第七部——正控失敗,斷言退化成全域缺席")

    if fails:
        for f in fails:
            print("  ❌ " + f)
        print("\n✗ self-test 未通過。")
        return 1
    print(f"✅ self-test:{len(ran)} 案全過\n   " + "\n   ".join(ran))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
