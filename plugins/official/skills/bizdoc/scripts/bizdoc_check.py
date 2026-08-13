#!/usr/bin/env python3
"""
bizdoc_check.py — 公文與新聞稿 lint(唯讀;不改任何檔)

檢查三組:
  1. 硬性違規 —— 情緒詞、情感修辭、公文缺主旨、主旨或導語過長  → exit 1
  2. 結構     —— 主旨缺公文動詞;導語缺具體事實                 → 警告
  3. 語氣     —— 模糊指涉、成語密度                             → 警告

**這支與 writing 是正面衝突的**:writing 把「制度」「窗口」「予以」整類公文腔列為硬性
違規,而公文要的正是那套固定行文。同一個詞兩種文體判定相反——這就是拆成兩支的理由
(KN-003)。**不要拿 writing 的 lint 去量公文**,會滿江紅而且每一條都是錯的。

公文與新聞稿的硬規則相同(禁情感修辭、禁情緒詞),只差結構,所以是同一支的兩個 kind。

判不了的規則(倒金字塔的輕重排序、公文的正確格式階層、致意用語得不得體)不在本檔——
它們寫在 SKILL.md 並明標靠人判斷。空頭規則比沒有規則更糟(KN-001)。

用法:
  python3 skills/bizdoc/scripts/bizdoc_check.py 公文.md --kind gov
  python3 skills/bizdoc/scripts/bizdoc_check.py 新聞稿.md --kind press
  python3 skills/bizdoc/scripts/bizdoc_check.py 新聞稿.md --kind press --allow 令人震驚

退出碼:0 通過(可能有警告)| 1 有硬性違規 | 2 環境/參數錯誤
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_RULES = Path(__file__).resolve().parent.parent / "assets" / "bizdoc_rules.json"
PUNCT = set("，。、；:：？！「」『』（）()〈〉《》〔〕—…⋯·,.;?!-_*#>|[]`~/\\+=<>@$%^&{}\"'“”‘’【】")
HEADING_RE = re.compile(r"^\s*#{1,6}\s*")


def char_len(s: str) -> int:
    return sum(1 for ch in s if not ch.isspace() and ch not in PUNCT)


def parse(raw: str):
    """回傳 (內文段落, 全部可讀行)。段落 = 空行分隔;標題與程式碼區塊排除。"""
    paragraphs, lines, buf, start, in_fence = [], [], [], 0, False
    for i, line in enumerate(raw.split("\n"), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        text = line.replace("**", "").replace("`", "").strip()
        if not text:
            if buf:
                paragraphs.append((start, "".join(buf)))
                buf = []
            continue
        if HEADING_RE.match(line):
            lines.append((i, HEADING_RE.sub("", line).strip()))
            if buf:
                paragraphs.append((start, "".join(buf)))
                buf = []
            continue
        lines.append((i, text))
        if not buf:
            start = i
        buf.append(text)
    if buf:
        paragraphs.append((start, "".join(buf)))
    return paragraphs, lines


def find_terms(lines, entries, allow):
    hits = []
    for e in entries:
        if e["term"] in allow:
            continue
        for lineno, text in lines:
            if e["term"] in text:
                hits.append({"line": lineno, "term": e["term"], "fix": e["fix"]})
    hits.sort(key=lambda h: (h["line"], h["term"]))
    return hits


def analyse(path: Path, rules: dict, kind: str, allow: set) -> dict:
    raw = path.read_text(encoding="utf-8")
    paragraphs, lines = parse(raw)
    k = rules["kinds"][kind]
    joined = "".join(t for _, t in lines)
    total = char_len(joined)
    # 分母用真實字數(CHG-20260813-01 D-1)。原本 max(total,1000)/1000 讓所有短於 1000 字的
    # 稿件密度被系統性低報,而 repo 內 24/24 份夾具全部短於 1000 字。
    per_k = total / 1000 if total else 0.0
    density_verifiable = total >= rules.get("min_sample_chars", 300)

    res = {"file": str(path), "kind": kind, "chars": total,
           "paragraphs": len(paragraphs), "hard": [], "warnings": [], "metrics": {}}

    # 樣本過短時**明說未驗到**。規則檔的 min_sample_chars_reason 白紙黑字承諾了
    # 「並明說未驗到」,而初版只是靜默跳過——同一個逃生門在這裡沒堵(V5 審議)。
    if not density_verifiable:
        res["warnings"].append(
            f"樣本只有 {total} 字(低於 {rules.get('min_sample_chars', 300)} 字),密度類規則 **未驗到**"
            "——短樣本的密度沒有統計意義,不判定也不冒充判過")

    # ---- 1. 硬性:情緒詞(原文明寫「嚴禁情緒化」)
    for h in find_terms(lines, rules.get("emotion_words", []), allow):
        res["hard"].append({**h, "group": "情緒詞"})

    # ---- 1. 硬性:情感修辭(排比不禁,譬喻全禁)
    fig_rx = re.compile(rules["figurative_pattern"])
    figs = [(ln, m.group(0)) for ln, t in lines for m in fig_rx.finditer(t)]
    res["metrics"]["figurative_count"] = len(figs)
    for ln, matched in figs:
        res["hard"].append({"line": ln, "term": f"譬喻「{matched}」", "group": "情感修辭",
                            "fix": f"{k['label']}禁止情感修辭,只保留最基本的結構排比"})

    # ---- 1. 硬性:公文必須有主旨
    subject_text, subject_line = None, 0
    if k.get("require_subject"):
        sub_rx = re.compile(k["subject_pattern"])
        for ln, t in lines:
            if sub_rx.match(t):
                subject_line, subject_text = ln, t
                break
        res["metrics"]["has_subject"] = subject_text is not None
        if subject_text is None:
            res["hard"].append({"line": 0, "term": "缺主旨", "group": "格式",
                                "fix": "公文必須有「主旨:」。說明與辦法視需要,主旨沒有例外"})
        else:
            n = char_len(subject_text)
            res["metrics"]["subject_chars"] = n
            if n > k["max_subject_chars"]:
                res["hard"].append({"line": subject_line, "term": f"主旨過長({n} 字)", "group": "格式",
                                    "fix": f"上限 {k['max_subject_chars']} 字——主旨要一段講完,細節寫進說明"})
            verbs = rules.get("official_verbs", [])
            if not any(v in subject_text for v in verbs):
                res["warnings"].append(
                    f"主旨沒有公文動詞({'/'.join(verbs[:5])}⋯)——主旨要講清楚是請對方做什麼")

    # ---- 1. 硬性:新聞稿的導語(倒金字塔:第一段就要交代完事情)
    if k.get("max_lead_chars"):
        lead_line, lead = paragraphs[0] if paragraphs else (0, "")
        n = char_len(lead)
        res["metrics"]["lead_chars"] = n
        if n > k["max_lead_chars"]:
            res["hard"].append({"line": lead_line, "term": f"導語過長({n} 字)", "group": "倒金字塔",
                                "fix": f"上限 {k['max_lead_chars']} 字——導語是最重要的一段,不是鋪陳"})
        if k.get("require_lead_fact"):
            fact_rx = re.compile(rules["fact_pattern"])
            has_fact = bool(fact_rx.search(lead))
            res["metrics"]["lead_has_fact"] = has_fact
            if not has_fact:
                res["warnings"].append(
                    "導語沒有任何數字或日期——倒金字塔要第一段就交代得出何時、多少;"
                    "這是「有沒有具體事實」的可測代理,判不了 5W 是否齊全")

    # ---- 3. 語氣:模糊指涉
    vague = find_terms(lines, rules.get("vague_reference", []), allow)
    res["metrics"]["vague_count"] = len(vague)
    if vague:
        res["warnings"].append(
            "模糊指涉:" + "、".join(sorted({v["term"] for v in vague}))
            + "——公文與新聞稿要指名道姓、要給期限")

    # ---- 3. 語氣:成語密度
    idioms = rules.get("idioms", [])
    hit = [w for w in idioms if w in joined]
    n = sum(joined.count(w) for w in idioms)
    res["metrics"]["idiom_count"] = n
    res["metrics"]["idiom_per_1000"] = round(n / per_k, 2) if density_verifiable else None
    lo, hi = rules.get("idioms_per_1000", [0, 6])
    if density_verifiable and n / per_k > hi:
        res["warnings"].append(
            f"成語密度 {n / per_k:.1f}/千字,高於上限 {hi}:{'、'.join(hit[:6])}"
            "——成語用來快速概括規模,用多了就變成沒有事實的形容")

    res["ok"] = not res["hard"]
    return res


def report(res: dict) -> None:
    print(f"\n=== {res['file']} — {res['chars']} 字 / {res['paragraphs']} 段 · kind {res['kind']} ===")
    if res["hard"]:
        print(f"\n✗ 硬性違規 {len(res['hard'])} 處(必須改):")
        for h in res["hard"]:
            where = f"L{h['line']}" if h["line"] else "全篇"
            print(f"  {where}  [{h['group']}] {h['term']}  → {h['fix']}")
    else:
        print("\n✓ 硬性違規:無")

    m = res["metrics"]
    bits = [f"譬喻 {m.get('figurative_count')} 處", f"成語 {m.get('idiom_count')} 次"]
    if "subject_chars" in m:
        bits.append(f"主旨 {m['subject_chars']} 字")
    if "lead_chars" in m:
        bits.append(f"導語 {m['lead_chars']} 字(有事實 {m.get('lead_has_fact')})")
    print("\n指標:" + " · ".join(bits))

    if res["warnings"]:
        print(f"\n⚠ 提醒 {len(res['warnings'])} 則:")
        for w in res["warnings"]:
            print(f"  · {w}")
    else:
        print("\n✓ 無提醒")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="公文與新聞稿 lint")
    ap.add_argument("files", nargs="+", help="要檢查的文件(.md)")
    ap.add_argument("--rules", default=str(DEFAULT_RULES), help="規則檔路徑")
    ap.add_argument("--kind", required=True, help="gov(公文)| press(新聞稿)")
    ap.add_argument("--allow", default="", help="個案放行的詞,逗號分隔(限引述他人原話)")
    ap.add_argument("--json", action="store_true", help="輸出 JSON")
    args = ap.parse_args(argv)

    rules_path = Path(args.rules)
    if not rules_path.is_file():
        print(f"ERROR: 找不到規則檔 {rules_path}", file=sys.stderr)
        return 2
    try:
        rules = json.loads(rules_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: 規則檔不是合法 JSON — {e}", file=sys.stderr)
        return 2
    if args.kind not in rules.get("kinds", {}):
        print(f"ERROR: --kind 只接受 {'/'.join(rules.get('kinds', {}))}", file=sys.stderr)
        return 2

    allow = {a.strip() for a in args.allow.split(",") if a.strip()}
    results, failed = [], False
    for f in args.files:
        p = Path(f)
        if not p.is_file():
            print(f"ERROR: 找不到檔案 {p}", file=sys.stderr)
            return 2
        res = analyse(p, rules, args.kind, allow)
        results.append(res)
        failed = failed or not res["ok"]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for res in results:
            report(res)
        print("\n" + ("✗ 有硬性違規,回去改。" if failed else "✓ 過。剩下的提醒自己判斷。"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
