#!/usr/bin/env python3
"""
techdoc_check.py — 規格書與架構說明 lint(唯讀;不改任何檔)

檢查三組:
  1. 硬性違規 —— 模糊形容詞、誇張詞、譬喻(超出該 kind 的配額)、架構說明缺圖 → exit 1
  2. 結構     —— 規格書的模組化編號與絕對動詞比例;架構說明的權衡節       → 警告
  3. 語氣     —— 文學性成語密度、被架空的動詞                            → 警告

**規格書與架構說明共用同一份規則檔**,因為兩者的硬規則相同(修辭 0-2%、禁模糊形容詞、
禁誇張),只差結構——規格書靠模組化編號與絕對動詞,架構說明靠圖與權衡分析。
硬規則相反的文體才拆成兩支 skill(見 knowledge KN-003);只差結構的用 --kind 切。

判不了的規則(圖畫得對不對、量化描述夠不夠、由大到小的邏輯遞進)不在本檔——
它們寫在 SKILL.md 並明標靠人判斷。空頭規則比沒有規則更糟(KN-001)。

用法:
  python3 skills/techdoc/scripts/techdoc_check.py 規格.md --kind spec
  python3 skills/techdoc/scripts/techdoc_check.py 架構.md --kind arch
  python3 skills/techdoc/scripts/techdoc_check.py 架構.md --kind arch --allow-no-diagram
  python3 skills/techdoc/scripts/techdoc_check.py 規格.md --kind spec --allow 彈性

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

DEFAULT_RULES = Path(__file__).resolve().parent.parent / "assets" / "techdoc_rules.json"
PUNCT = set("，。、；:：？！「」『』（）()〈〉《》〔〕—…⋯·,.;?!-_*#>|[]`~/\\+=<>@$%^&{}\"'“”‘’")
BULLET_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.、)]\s+)")
HEADING_RE = re.compile(r"^\s*#{1,6}\s*")


def char_len(s: str) -> int:
    return sum(1 for ch in s if not ch.isspace() and ch not in PUNCT)


def prepare(raw: str):
    """回傳 (內文行, 條列行, 標題行, 全部原始行)。程式碼區塊整段排除——
    範例程式裡出現「快速」不是文件在講模糊的話(KN-002:門檻要按文本類型分流)。"""
    body, bullets, headings, all_lines = [], [], [], raw.split("\n")
    in_fence = False
    for i, line in enumerate(all_lines, 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        text = line.replace("**", "").replace("`", "").strip()
        if not text:
            continue
        if HEADING_RE.match(line):
            headings.append((i, HEADING_RE.sub("", line).strip()))
            continue
        if BULLET_RE.match(line):
            bullets.append((i, text))
            continue
        body.append((i, text))
    return body, bullets, headings, all_lines


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


def has_diagram(all_lines, patterns) -> bool:
    rxs = [re.compile(p) for p in patterns]
    return any(rx.search(line) for line in all_lines for rx in rxs)


def analyse(path: Path, rules: dict, kind: str, allow: set, allow_no_diagram: bool) -> dict:
    raw = path.read_text(encoding="utf-8")
    body, bullets, headings, all_lines = prepare(raw)
    k = rules["kinds"][kind]
    text_lines = sorted(body + bullets + headings, key=lambda x: x[0])
    joined = "".join(t for _, t in text_lines)
    total = char_len(joined)
    per_k = max(total, 1000) / 1000

    res = {"file": str(path), "kind": kind, "chars": total,
           "hard": [], "warnings": [], "metrics": {}}

    # ---- 1. 硬性:模糊形容詞(原文語氣為絕對——「拒絕模糊形容詞,一律改用具體數據」)
    for h in find_terms(text_lines, rules.get("vague_adjectives", []), allow):
        res["hard"].append({**h, "group": "模糊形容詞"})

    # ---- 1. 硬性:誇張與情緒詞
    for h in find_terms(text_lines, rules.get("exaggeration", []), allow):
        res["hard"].append({**h, "group": "誇張"})

    # ---- 1. 硬性:譬喻(spec 全禁;arch 限量)
    fig_rx = re.compile(rules["figurative_pattern"])
    figs = [{"line": ln, "matched": m.group(0)}
            for ln, t in text_lines for m in fig_rx.finditer(t)]
    res["metrics"]["figurative_count"] = len(figs)
    quota = k.get("allow_figurative", 0)
    for f in figs[quota:]:
        res["hard"].append({
            "line": f["line"], "term": f"譬喻「{f['matched']}」", "group": "修辭",
            "fix": (f"{k['label']}的修辭配額是 {quota} 處" +
                    ("——技術文件不需要任何一句話被猜" if quota == 0
                     else "——類比只用來把抽象架構比成讀者已知的實物,超過就變裝飾"))})

    # ---- 1. 硬性:架構說明必須有圖
    diagram = has_diagram(all_lines, rules.get("diagram_patterns", []))
    res["metrics"]["has_diagram"] = diagram
    if k.get("require_diagram") and not diagram:
        if allow_no_diagram:
            res["warnings"].append("**已用 --allow-no-diagram 放行缺圖**——放行留痕,不是通過")
        else:
            res["hard"].append({
                "line": 0, "term": "缺架構圖", "group": "圖文互補",
                "fix": "架構說明的核心手法是圖文互補。認 mermaid 區塊、markdown 圖片、ASCII 方框三種;"
                       "用了認不出的畫法請加 --allow-no-diagram(會被記錄)"})

    # ---- 2. 結構:模組化編號(規格書)
    if k.get("require_numbering"):
        num_rx = re.compile(k["numbering_pattern"])
        numbered = [ln for ln, t in text_lines if num_rx.match(t)]
        res["metrics"]["numbered_lines"] = len(numbered)
        if not numbered:
            res["warnings"].append(
                "找不到任何模組化編號(1.1 / 1.1.1)——規格書要能被逐條引用,"
                "驗收時才指得出是哪一條沒做到")

    # ---- 2. 結構:絕對動詞比例(規格書)
    ratio_gate = k.get("min_absolute_verb_ratio", 0.0)
    if ratio_gate and bullets:
        verbs = k.get("absolute_verbs", [])
        with_verb = [ln for ln, t in bullets if any(v in t for v in verbs)]
        ratio = len(with_verb) / len(bullets)
        res["metrics"]["absolute_verb_ratio"] = round(ratio, 2)
        if ratio < ratio_gate:
            res["warnings"].append(
                f"條列中只有 {ratio:.0%} 含絕對動詞({'/'.join(verbs[:4])}⋯),低於 {ratio_gate:.0%}"
                "——需求句要講清楚是必須還是可選,否則驗收時各說各話")

    # ---- 2. 結構:權衡節(架構說明)
    want = k.get("require_sections", [])
    if want:
        found = any(any(w in h for w in want) for _, h in headings)
        res["metrics"]["has_tradeoff_section"] = found
        if not found:
            res["warnings"].append(
                f"找不到權衡/取捨/決策的段落(標題含 {'、'.join(want[:3])} 等字)"
                "——架構文件最有價值的是為什麼不選另一個")

    # ---- 3. 語氣:文學性成語
    idioms = rules.get("literary_idioms", [])
    hit = [w for w in idioms if w in joined]
    n = sum(joined.count(w) for w in idioms)
    res["metrics"]["idiom_count"] = n
    cap = rules.get("max_idioms_per_1000", 1)
    if n and n / per_k > cap:
        res["warnings"].append(
            f"文學性成語 {n} 次 / {total} 字(上限 {cap}/千字):{'、'.join(hit[:6])}"
            "——技術文件的成語比例趨近於零,它們讓句子聽起來有結論但沒有內容")

    # ---- 3. 語氣:被架空的動詞
    weak = find_terms(text_lines, rules.get("weak_verbs", []), allow)
    res["metrics"]["weak_verbs"] = len(weak)
    if weak:
        res["warnings"].append(
            "動詞被架空:" + "、".join(sorted({w['term'] for w in weak}))
            + "——原文要求主動語態,直接用後面那個動詞")

    res["ok"] = not res["hard"]
    return res


def report(res: dict) -> None:
    print(f"\n=== {res['file']} — {res['chars']} 字 · kind {res['kind']} ===")
    if res["hard"]:
        print(f"\n✗ 硬性違規 {len(res['hard'])} 處(必須改):")
        for h in res["hard"]:
            where = f"L{h['line']}" if h["line"] else "全篇"
            print(f"  {where}  [{h['group']}] {h['term']}  → {h['fix']}")
    else:
        print("\n✓ 硬性違規:無")

    m = res["metrics"]
    print(f"\n指標:譬喻 {m.get('figurative_count')} 處 · 文學性成語 {m.get('idiom_count')} 次"
          f" · 有圖 {m.get('has_diagram')}"
          + (f" · 絕對動詞比例 {m.get('absolute_verb_ratio')}" if "absolute_verb_ratio" in m else ""))

    if res["warnings"]:
        print(f"\n⚠ 提醒 {len(res['warnings'])} 則:")
        for w in res["warnings"]:
            print(f"  · {w}")
    else:
        print("\n✓ 無提醒")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="規格書與架構說明 lint")
    ap.add_argument("files", nargs="+", help="要檢查的文件(.md)")
    ap.add_argument("--rules", default=str(DEFAULT_RULES), help="規則檔路徑")
    ap.add_argument("--kind", required=True, help="spec(規格書)| arch(架構說明)")
    ap.add_argument("--allow", default="", help="個案放行的詞,逗號分隔")
    ap.add_argument("--allow-no-diagram", action="store_true",
                    help="架構說明用了認不出的畫法時放行(會被記錄)")
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
        res = analyse(p, rules, args.kind, allow, args.allow_no_diagram)
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
