#!/usr/bin/env python3
"""詞資產守恆閘 — **從 vendored raw 獨立重算**,再與 asset 對帳。

## 這支存在的理由

審議席的原話:**「否則守恆檢查退化成信任聲明。」**

資產 meta 裡的數字(對數、符號數、19 部、5,046 字…)原本全部出自沒有進 repo 的
session 內程式碼。任何人拿到 repo 都無法重跑——那不是「可獨立重跑」,是「請相信我算過」。

## 初版的閘比我描述的弱,這是二讀修掉的

我把初版描述成「對 vendored raw 獨立重算」,而實測不是:

    baixiang 符號數     真的從 raw 算
    baixiang raw_pairs  **沒有**從 raw 算
    cilin 全部數字      **全由成品 JSON 自算**,raw 只驗 hash/bytes

審議席(codex)的判詞:**「這仍是『成品與自稱一致』,不是 raw→asset 守恆。」**

那是本 repo 反覆出現的病在描述層的形態:**閘的名字比它的能力大**,
而綠燈時沒有人會去讀它到底算了什麼。本版把兩份資產的**每一個結構數字**
都從 raw 重新 parse 出來。

## 為什麼守恆的起點必須在 parser 之前

初版的守恆檢查**跑在丟失的下游**:parser 靜默丟了 4 行
(西江月 3 行毀在嵌套標記 `-{叶}-`、鷓鴣天 1 行毀在行內全形空格),
而檢查從 parser 的輸出算起,於是它算的是「丟完之後的東西自己一致」。

**斷言與被斷言物出自同一次認知,錯會成對地錯。**

## 豁免要顯式

raw 檔頭有圖例「○平 ●仄 ⊙可平可仄 △平韻 ▲仄韻」,五個符號各一,不屬任何詞牌。
naive 全檔 7255 − 圖例 5 = 7250。`cilin` 的兩個污染字(热、艹)同理記在 `_exemptions`。

**豁免不寫出來,對帳就永遠差那幾個,而下一個人只能選擇相信或推翻整份資產。**
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from fnmatch import fnmatch
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

DEFAULT_BASE = Path(__file__).resolve().parent.parent / "assets"


def _repo_root() -> Path | None:
    """往上找 `.git`。**寫死 `parents[3]` 是錯的**——`skills/` 下算對,
    `plugins/classical/skills/` 下會指到 plugin 目錄,而副本才是使用者裝到的那份。"""
    for d in Path(__file__).resolve().parents:
        if (d / ".git").exists():
            return d
    return None


def _read_gitattributes() -> str | None:
    """回 None 代表**不在 git 工作樹裡**(已安裝的 plugin 副本)。

    這不是 fail-open:第 6 條防的是 git 簽出時的行尾轉換,
    **沒有 git 就沒有那個轉換**,條件本身不成立。而在 repo 裡缺規則一定紅。"""
    root = _repo_root()
    if root is None:
        return None
    p = root / ".gitattributes"
    return p.read_text(encoding="utf-8") if p.exists() else ""

TONE_SYMS = "○●⊙△▲"
# **Ext-B 也要收。** 舊版寫 `[㐀-鿿]`,不含 U+20000 以上,於是 𣘼 𦶟 這兩個罕字
# 落在類別外被丟掉——而它們正是下面 TPL 那兩個模板真正代表的字。
CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0003ffff]")
ANN = re.compile(r"\{\{\*\|[^}]*\}\}")
LANGVAR = re.compile(r"-\{(?:[^{}|]*\|)?([^{}]*)\}-")     # -{叶}- 這類嵌套標記
# 字形結構模板 `{{!|𣘼|上「啟」下「木」}}`——**第二引數是描述,不是韻字**。
# 這一行是補上來的:舊版兩邊(資產建置與本檔的 raw parser)**犯同一個錯**,
# 把「上啟下木」「上艹下热」當四個韻字收進表,於是 上、下、木 成為假橋接字,
# 而橋接字正是「入聲獨押」宣稱的殘餘誤放面。守恆閘照樣綠——**一起錯就是一致**。
TPL = re.compile(r"\{\{!\|([^|{}]+)\|[^{}]*\}\}")


# ── 從 raw 獨立 parse(不看成品)────────────────────────────────────────

def parse_baixiang_raw(t: str) -> dict:
    """對 raw 重算詞牌數、對數、符號數。**不引用成品的任何欄位。**"""
    tunes, pairs, syms = {}, 0, 0
    for head, body in re.findall(r"===\s*([^=]+?)\s*===\s*<poem>(.*?)</poem>", t, re.S):
        name = ANN.sub("", LANGVAR.sub(r"\1", head)).split("·")[0].strip().split("、")[-1]
        lines = []
        for l in body.splitlines():
            s = ANN.sub("", LANGVAR.sub(r"\1", l))
            s = re.sub(r"\s|　", "", s)
            if s:
                lines.append(s)
        rows = 0
        for a, b in zip(lines, lines[1:]):
            if b and set(b) <= set(TONE_SYMS):
                rows += 1
                syms += len(b)
        tunes[name] = rows
        pairs += rows
    return {"tunes": len(tunes), "pairs": pairs, "symbols": syms, "per_tune": tunes}


def parse_cilin_raw(t: str) -> dict:
    """對 raw 重算部數、韻目數、字數。**不看成品。**

    來源結構:`==第N部==` → `===平聲:一東二冬通用===` → `【一東】東同童…`
    釋義字要連括號帶內文一起剝——初版只剝括號留內文,
    **677 個釋義字污染 106/115 個字表**(「間」進第一部、「高」進第二部)。
    """
    parts, cur, rhymes = {}, None, {}
    # **釋義有兩種括號,兩種都要剝。**
    #   圓括號 480 處:「中（中間）」——初版只剝括號留內文,677 個釋義字污染 106/115 個字表
    #   方括號   5 處:「臟[骯髒]」「輓[輓聯]」「鬱[馥鬱,鬱鬱乎文哉]」
    # 二讀時我的 raw parser 漏了方括號那 5 處,於是守恆閘紅了 11 字——
    # **而錯的是新 parser,不是資產**。這正是 raw→asset 雙向對帳的用處:
    # 它不預設哪一邊對,只要求兩邊能對上,對不上就必須查到成因。
    GLOSS = re.compile(r"（[^）]*）|\([^)]*\)|\[[^\]]*\]")
    for line in t.splitlines():
        line = line.strip()
        m = re.match(r"^==\s*(第[一二三四五六七八九十]+部)\s*==$", line)
        if m:
            cur = m.group(1)
            parts[cur] = {}
            continue
        if not cur:
            continue
        for rm in re.finditer(r"【([^】]+)】([^【]*)", line):
            name = rm.group(1)
            chars = GLOSS.sub("", TPL.sub(r"\1", rm.group(2)))
            chars = "".join(CJK.findall(chars))
            if chars:
                parts[cur][name] = chars
                rhymes[(cur, name)] = chars
    toks = sum(len(v) for p in parts.values() for v in p.values())
    uniq = {c for p in parts.values() for v in p.values() for c in v}
    return {"parts": len(parts), "rhymes": len(rhymes), "tokens": toks,
            "unique": len(uniq), "chars": uniq, "detail": parts}


# ── 對帳 ───────────────────────────────────────────────────────────────

def check(base: Path = DEFAULT_BASE, attrs: str | None = None) -> list[str]:
    bad: list[str] = []
    bx = json.loads((base / "baixiang.json").read_text(encoding="utf-8"))
    cl = json.loads((base / "cilin.json").read_text(encoding="utf-8"))
    raw_bx = base / "raw" / "baixiang.wikitext"
    raw_cl = base / "raw" / "cilin.wikitext"

    # 1. raw 是資產宣稱的那一份
    for asset, raw, name in ((bx, raw_bx, "baixiang"), (cl, raw_cl, "cilin")):
        if not raw.exists():
            bad.append(f"{name}:vendored raw 不存在——reproduce 鏈第一環斷掉,"
                       "meta 的數字誰也重跑不了")
            continue
        got = hashlib.sha256(raw.read_bytes()).hexdigest()
        if asset["_source"].get("raw_sha256") != got:
            bad.append(f"{name}:raw sha256 不符——資產與它宣稱的來源已經分家")
        if asset["_source"].get("raw_bytes") != raw.stat().st_size:
            bad.append(f"{name}:raw_bytes 與實檔不符")
        if "oldid" not in json.dumps(asset["_source"], ensure_ascii=False):
            bad.append(f"{name}:_source 沒有 oldid——limits 欄談 oldid,"
                       "記的卻是活頁連結,那條限制形同虛設")
    if bad:
        return bad

    # 2. baixiang:raw → asset 全欄守恆
    t = raw_bx.read_text(encoding="utf-8")
    r = parse_baixiang_raw(t)
    cons = bx["_conservation"]
    naive = sum(t.count(c) for c in TONE_SYMS)
    if naive != cons["raw_symbols_naive_total"]:
        bad.append(f"baixiang:raw naive 符號 {naive} ≠ 自稱 "
                   f"{cons['raw_symbols_naive_total']}")
    if naive - cons["legend_exemption"] != r["symbols"]:
        bad.append(f"baixiang:naive {naive} − 圖例 {cons['legend_exemption']} "
                   f"≠ **從 raw 重 parse 的符號數** {r['symbols']}")
    a_sym = sum(len(x["tones"]) for v in bx["tunes"].values() for x in v["rows"])
    a_pair = sum(len(v["rows"]) for v in bx["tunes"].values())
    if r["symbols"] != a_sym:
        bad.append(f"baixiang:**符號守恆破了** raw {r['symbols']} vs asset {a_sym}"
                   "——parser 丟了東西,而丟失的下游看不見")
    if r["pairs"] != a_pair:
        bad.append(f"baixiang:**對數守恆破了** raw {r['pairs']} vs asset {a_pair}")
    if r["tunes"] != len(bx["tunes"]):
        bad.append(f"baixiang:詞牌數 raw {r['tunes']} vs asset {len(bx['tunes'])}")

    # 3. baixiang 對齊與啟用:重算,不看旗標
    clean = [n for n, v in bx["tunes"].items()
             if all(len(CJK.findall(x["chars"])) == len(x["tones"]) for x in v["rows"])]
    if len(clean) != bx["_alignment"]["clean_tunes"]:
        bad.append(f"baixiang:重算對齊 {len(clean)} ≠ 自稱 "
                   f"{bx['_alignment']['clean_tunes']}")
    if not set(bx["_enabled"]["list"]) <= set(clean):
        bad.append("baixiang:**啟用了不對齊的牌**"
                   f"{sorted(set(bx['_enabled']['list']) - set(clean))}"
                   "——不齊的牌一律不啟用是本資產的硬規矩")

    # 4. cilin:raw → asset 全欄守恆(二讀補;初版全由成品自算)
    rc = parse_cilin_raw(raw_cl.read_text(encoding="utf-8"))
    a_toks = sum(len(x["chars"]) for p in cl["parts"].values() for x in p["rhymes"].values())
    a_uniq = {c for p in cl["parts"].values() for x in p["rhymes"].values() for c in x["chars"]}
    a_rhy = sum(len(p["rhymes"]) for p in cl["parts"].values())
    exempt = {e["char"] for e in cl.get("_exemptions", {}).get("removed", [])}
    if rc["parts"] != len(cl["parts"]):
        bad.append(f"cilin:部數 raw {rc['parts']} vs asset {len(cl['parts'])}")
    if rc["rhymes"] != a_rhy:
        bad.append(f"cilin:韻目數 raw {rc['rhymes']} vs asset {a_rhy}")
    if rc["tokens"] - len(exempt) != a_toks:
        bad.append(f"cilin:**字數守恆破了** raw {rc['tokens']} − 豁免 {len(exempt)} "
                   f"≠ asset {a_toks}")
    lost = (rc["chars"] - exempt) - a_uniq
    if lost:
        bad.append(f"cilin:raw 有而 asset 沒有的字 {len(lost)} 個"
                   f"(例 {''.join(sorted(lost)[:8])})——不在豁免名單內,是靜默丟失")
    if a_toks != cl["_stats"]["tokens"]:
        bad.append(f"cilin:asset 實算 tokens {a_toks} ≠ 自稱 {cl['_stats']['tokens']}")
    if len(a_uniq) != cl["_stats"]["unique_chars"]:
        bad.append(f"cilin:asset 實算唯一字 {len(a_uniq)} ≠ 自稱 "
                   f"{cl['_stats']['unique_chars']}")
    for e in cl.get("_exemptions", {}).get("removed", []):
        if e["char"] in json.dumps(cl["parts"], ensure_ascii=False):
            bad.append(f"cilin:已豁免的「{e['char']}」仍在字表裡——豁免沒生效")

    # 5. **非 CJK 污染**(ASCII / 標點 / 空白)
    #
    # **這一條抓不到「热」「艹」,而且從來就不該宣稱它能。**
    # 那兩個字都在 CJK 範圍內(U+70ED / U+8279)——簡化字與部首都是漢字。
    # 初版把本條的存在理由寫成「擋掉那兩個字」,那是**閘的名字比它的能力大**,
    # 綠燈時沒有人會去讀它到底算了什麼(審議席 codex 二讀指正)。
    #
    # 它真正管的是:頁尾文字、ASCII、標點混進字表——平水韻資產就被
    # 'Public domain' 混進過 14 個 ASCII 字元。
    # 「是漢字但不是韻字」由第 4 條的 raw→asset 差異與具名豁免守恆處理。
    for pn, pv in cl["parts"].items():
        for rn, x in pv["rhymes"].items():
            junk = [c for c in x["chars"] if not CJK.fullmatch(c)]
            if junk:
                bad.append(f"cilin:{pn}/{rn} 含非 CJK 字元 {junk}")

    # 6. **vendored raw 必須被 .gitattributes 釘成不轉換。**
    #
    # 為什麼這條要存在,而不是「加了 .gitattributes 就好」:
    # `core.autocrlf=true` 是 Windows 版 git 的預設,簽出時會注入 CRLF——
    # baixiang 80170 → 83739 bytes、cilin 27665 → 28025。第 1 條的 sha256
    # 於是在**任何 Windows checkout 上都紅**,而 CI runner 是 Linux,永遠綠。
    #
    # 所以第 1 條的紅端在 CI 上不可達,**這條規則等於沒有被 CI 測過**(KN-001)。
    # 本條把「設定有沒有寫」變成平台無關的斷言:誰把 `*.wikitext -text` 刪掉,
    # Linux 上也會紅。**保護 sha 的不是 sha 檢查本身,是這一條。**
    raws = sorted((base / "raw").glob("*")) if (base / "raw").is_dir() else []
    text = attrs if attrs is not None else _read_gitattributes()
    if raws and text is not None:
        pinned = set()
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            pat, *rest = line.split()
            if any(a in ("-text", "binary") for a in rest):
                pinned.add(pat)
        for r in raws:
            if not any(fnmatch(r.name, pat) for pat in pinned):
                bad.append(f"vendored raw「{r.name}」沒有被 .gitattributes 釘成 "
                           "`-text`——Windows 簽出會注入 CRLF,sha256 當場分家,"
                           "而 Linux CI 看不見")
    return bad


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    bad = check()
    if bad:
        print("✗ 詞資產守恆閘:")
        for b in bad:
            print("  - " + b)
        return 1
    bx = json.loads((DEFAULT_BASE / "baixiang.json").read_text(encoding="utf-8"))
    cl = json.loads((DEFAULT_BASE / "cilin.json").read_text(encoding="utf-8"))
    print(f"✅ 詞資產守恆閘(**raw → asset 全欄重算**):"
          f"baixiang {len(bx['tunes'])} 牌 / 對齊 {bx['_alignment']['clean_tunes']} "
          f"/ 啟用 {len(bx['_enabled']['list'])};"
          f"cilin {len(cl['parts'])} 部 / {cl['_stats']['unique_chars']} 字,"
          f"豁免 {len(cl.get('_exemptions', {}).get('removed', []))} 條已生效")
    return 0


def self_test() -> int:
    """紅端可達。**在 temp copy 上跑,不碰正式資產**(審議席 codex 二讀指正:
    初版直接覆寫正式檔,中斷或並行會留下污染——而這個 session 被逾時殺過多次)。"""
    import shutil
    import tempfile
    fails: list[str] = []
    ran: list[str] = []

    def probe(label, mutate, want):
        ran.append(label)
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "assets"
            shutil.copytree(DEFAULT_BASE, base)
            mutate(base)
            got = check(base)
            if want is None:
                if got:
                    fails.append(f"{label} 應綠卻紅:{got}")
            elif not any(want in g for g in got):
                fails.append(f"{label} 應紅於「{want}」,實得:{got or '全綠'}")

    def edit(base, name, fn):
        p = base / name
        d = json.loads(p.read_text(encoding="utf-8"))
        fn(d)
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    probe("綠 真實資產", lambda b: None, None)

    # 第 6 條的紅綠兩端。**這一條的價值全在紅端能不能在 Linux 上到達**——
    # 若只靠第 1 條的 sha256,紅端只在 Windows 可達,CI 永遠測不到。
    def attrs_probe(label, attrs, want):
        ran.append(label)
        got = check(DEFAULT_BASE, attrs=attrs)
        if want is None:
            if got:
                fails.append(f"{label} 應綠卻紅:{got}")
        elif not any(want in g for g in got):
            fails.append(f"{label} 應紅於「{want}」,實得:{got or '全綠'}")

    attrs_probe("紅 .gitattributes 沒釘 vendored raw", "*.sh text eol=lf",
                "沒有被 .gitattributes 釘成")
    attrs_probe("綠 釘了就過", "*.wikitext -text", None)
    # 註解掉的規則不算數——`#` 之後要被剝掉
    attrs_probe("紅 規則被註解掉", "# *.wikitext -text",
                "沒有被 .gitattributes 釘成")
    # **把「不在 git 工作樹就跳過」這條路徑也釘住。** 已安裝的 plugin 副本沒有
    # `.git`,第 6 條不成立而非通過;不釘的話,哪天 `_repo_root()` 壞掉退回 None,
    # 整條規則會在 repo 裡靜默消失,而 self-test 照樣全綠。
    ran.append("邊界 不在 git 工作樹時第 6 條不成立(非靜默通過)")
    if check(DEFAULT_BASE, attrs=None) != []:
        fails.append("邊界 真實 repo 應綠,第 6 條在本 repo 內必須是成立且通過的")
    if _read_gitattributes() is None:
        fails.append("邊界 本檔在 repo 內卻找不到 git 工作樹"
                     "——`_repo_root()` 壞了,第 6 條會靜默消失")

    probe("紅 非 CJK 污染(ASCII)",
          lambda b: edit(b, "cilin.json", lambda d: next(
              iter(next(iter(d["parts"].values()))["rhymes"].values())
          ).__setitem__("chars", next(iter(next(iter(d["parts"].values()))["rhymes"].values()))["chars"] + "A")),
          "含非 CJK")

    # **負向案:釘住第 5 條抓不到簡化字。** 不是缺陷,是能力邊界的釘子——
    # 哪天有人以為這條涵蓋簡繁,這個案子會提醒他它從來沒有涵蓋過。
    # 而它會被第 4 條的 raw→asset 差異抓到(簡化字不在 raw 裡),那才是對的守門人。
    ran.append("邊界 第 5 條抓不到簡化字,但第 4 條抓得到")
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "assets"
        shutil.copytree(DEFAULT_BASE, base)
        edit(base, "cilin.json", lambda d: (
            next(iter(next(iter(d["parts"].values()))["rhymes"].values())).__setitem__(
                "chars",
                next(iter(next(iter(d["parts"].values()))["rhymes"].values()))["chars"] + "国"),
            d["_stats"].__setitem__("tokens", d["_stats"]["tokens"] + 1),
            d["_stats"].__setitem__("unique_chars", d["_stats"]["unique_chars"] + 1)))
        got = check(base)
        if any("含非 CJK" in g for g in got):
            fails.append("邊界案:第 5 條竟然抓到簡化字——與 docstring 的能力邊界不符")
        if not any("字數守恆破了" in g for g in got):
            fails.append("邊界案:第 4 條沒抓到簡化字——那 raw→asset 守恆是空的")

    probe("紅 tokens 自稱與實算不符",
          lambda b: edit(b, "cilin.json",
                         lambda d: d["_stats"].__setitem__("tokens", d["_stats"]["tokens"] + 1)),
          "asset 實算 tokens")
    probe("紅 啟用了不對齊的牌",
          lambda b: edit(b, "baixiang.json",
                         lambda d: d["_enabled"].__setitem__(
                             "list", d["_enabled"]["list"] + [d["_alignment"]["dirty_tunes"][0]])),
          "啟用了不對齊的牌")
    probe("紅 raw 被抽掉一行(符號守恆)",
          lambda b: (b / "raw" / "baixiang.wikitext").write_text(
              (b / "raw" / "baixiang.wikitext").read_text(encoding="utf-8").replace("○○●●", "", 1),
              encoding="utf-8"),
          "sha256 不符")

    if fails:
        for f in fails:
            print("  ❌ " + f)
        print("\n✗ self-test 未通過。")
        return 1
    print(f"✅ self-test:{len(ran)} 案全過(" + "、".join(ran) + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
