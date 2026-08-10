#!/usr/bin/env python3
"""
fiction_check.py — 小說技術規範 lint(唯讀;不改任何檔)

檢查四組:
  1. 硬性違規 —— 段落過長、一段塞多輪對話、擬聲詞樣板          → exit 1
  2. 對話     —— 純對話連續輪數、無意義寒暄                     → 警告
  3. 節奏密度 —— 擬聲詞密度、成語密度(需 --genre)             → 警告
  4. 架構     —— 章節字數區間                                   → 警告

**這支不是 writing/style_check.py 的變體,兩者的硬規則互斥**:小說不要求第一人稱,
結尾短句是斷頭台法則要的效果,武打段的密集對偶是文體本身。共用一支 lint 會直接誤殺。

判不了的規則(斷頭台切章點、留白、伏筆、心理轉折獨立成段、各文體的修辭比例)
不在本檔——它們寫在 SKILL.md 並明標靠人判斷。空頭規則比沒有規則更糟(KN-001)。

規則的單一真相是 assets/fiction_rules.json;要調門檻或加詞改那份,不要改本腳本。

用法:
  python3 skills/fiction/scripts/fiction_check.py 稿件.md
  python3 skills/fiction/scripts/fiction_check.py 稿件.md --mode web
  python3 skills/fiction/scripts/fiction_check.py 稿件.md --genre wuxia
  python3 skills/fiction/scripts/fiction_check.py 稿件.md --json

退出碼:0 通過(可能有警告)| 1 有硬性違規 | 2 環境/參數錯誤
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

# 釘住輸出編碼:非 UTF-8 主控台(如 Windows cp932)印 CJK 會 UnicodeEncodeError。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_RULES = Path(__file__).resolve().parent.parent / "assets" / "fiction_rules.json"
PUNCT = set("，。、；：？！「」『』（）()〈〉《》〔〕—…⋯·,.;:?!-_*#>|[]`~/\\+=<>@$%^&{}\"'“”‘’")
QUOTE_RE = re.compile(r"[「『][^」』]*[」』]")
QUOTE_ONLY_RE = re.compile(r"^\s*[「『][^」』]*[」』]\s*$")


def char_len(s: str) -> int:
    """字數不含空白與標點——與 writing skill 同一套計法,兩支報表的『字』意思一致。"""
    return sum(1 for ch in s if not ch.isspace() and ch not in PUNCT)


def strip_md(line: str) -> str:
    line = re.sub(r"^\s*>\s?", "", line)          # 引用符號在小說裡多半是排版,不是結構
    return line.replace("**", "").replace("`", "").rstrip()


def parse(raw: str, chapter_re):
    """切出 (章節, 段落)。段落 = 空行分隔的連續非標題行,回傳 (起始行號, 行陣列)。"""
    chapters, paragraphs = [], []
    cur_title, cur_lines, cur_start = None, [], 0
    buf, buf_start, in_fence = [], 0, False

    def flush_para():
        nonlocal buf, buf_start
        if buf:
            paragraphs.append((buf_start, list(buf), cur_title))
            buf = []

    for i, line in enumerate(raw.split("\n"), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            flush_para()
            continue
        if in_fence:
            continue
        if chapter_re.match(line):
            flush_para()
            if cur_title is not None:
                chapters.append((cur_start, cur_title, list(cur_lines)))
            cur_title = line.strip().lstrip("#").strip()
            cur_start, cur_lines = i, []
            continue
        text = strip_md(line)
        if not text.strip():
            flush_para()
            continue
        if cur_title is not None:
            cur_lines.append(text)
        if not buf:
            buf_start = i
        buf.append(text)
    flush_para()
    if cur_title is not None:
        chapters.append((cur_start, cur_title, list(cur_lines)))
    return chapters, paragraphs


def analyse(path: Path, rules: dict, mode: str, genre: str | None) -> dict:
    raw = path.read_text(encoding="utf-8")
    m_cfg = rules["modes"][mode]
    d_cfg = rules.get("dialogue", {})
    o_cfg = rules.get("onomatopoeia", {})
    i_cfg = rules.get("idioms", {})
    chapter_re = re.compile(rules.get("chapter", {}).get("heading_pattern", r"^#{1,3}\s+"))

    chapters, paragraphs = parse(raw, chapter_re)
    body = "".join(t for _, lines, _ in paragraphs for t in lines)
    total = char_len(body)
    per_k = max(total, 1000) / 1000

    res = {"file": str(path), "mode": mode, "genre": genre, "chars": total,
           "paragraphs": len(paragraphs), "chapters": len(chapters),
           "hard": [], "warnings": [], "metrics": {}}

    # ---- 1. 硬性:段落長度(原文列為「分段鐵律」,且完全可判定)
    cap = m_cfg["max_paragraph_chars"]
    line_cap = m_cfg.get("max_paragraph_lines", 0)
    long_paras = []
    for start, lines, _ in paragraphs:
        n = char_len("".join(lines))
        if n > cap:
            long_paras.append({"line": start, "chars": n})
            res["hard"].append({
                "line": start, "term": "段落過長", "matched": f"{n} 字",
                "fix": f"上限 {cap} 字({m_cfg['label']})——切開它。大段描寫會把讀者推走"})
        elif line_cap and len(lines) > line_cap:
            res["hard"].append({
                "line": start, "term": "段落行數過多", "matched": f"{len(lines)} 行",
                "fix": f"上限 {line_cap} 行({m_cfg['label']})——手機閱讀的視覺切割"})
    res["metrics"]["long_paragraphs"] = len(long_paras)

    # ---- 1. 硬性:一段塞多輪對話
    q_cap = d_cfg.get("max_quotes_per_paragraph", 2)
    for start, lines, _ in paragraphs:
        n = len(QUOTE_RE.findall("".join(lines)))
        if n > q_cap:
            res["hard"].append({
                "line": start, "term": "一段塞多輪對話", "matched": f"{n} 處引號",
                "fix": f"同段最多 {q_cap} 處(夾敘夾議式的一開口、一接續)——換人說話就要獨立成段"})

    # ---- 1. 硬性:擬聲詞樣板「轟隆!」一聲
    tmpl = o_cfg.get("template_pattern")
    if tmpl:
        rx = re.compile(tmpl)
        for start, lines, _ in paragraphs:
            for mt in rx.finditer("".join(lines)):
                res["hard"].append({
                    "line": start, "term": "擬聲詞樣板", "matched": mt.group(0),
                    "fix": "用強動詞取代:「悶雷滾過天際」而不是「『轟隆!』一聲,天空打雷了」"})

    # ---- 2. 對話:純對話連續輪數
    run = best = 0
    run_at = flagged_at = 0
    for start, lines, _ in paragraphs:
        joined = "".join(lines)
        if QUOTE_ONLY_RE.match(joined):
            if run == 0:
                run_at = start
            run += 1
            if run > best:
                best, flagged_at = run, run_at
        else:
            run = 0
    res["metrics"]["max_pure_dialogue_run"] = best
    run_cap = d_cfg.get("max_pure_dialogue_run", 4)
    if best > run_cap:
        res["warnings"].append(
            f"第 {flagged_at} 行起連續 {best} 段純對話(上限 {run_cap})"
            "——插一個人名或特徵進去,否則讀者會搞不清誰在說話")

    # ---- 2. 對話:無意義寒暄
    smalltalk = [w for w in d_cfg.get("smalltalk", []) if w in body]
    res["metrics"]["smalltalk"] = smalltalk
    if smalltalk:
        res["warnings"].append(
            "對話裡有日常寒暄:" + "、".join(smalltalk)
            + "——對話要推劇情、露性格或洩線索,寒暄會把張力洩掉")

    # ---- 3. 擬聲詞密度
    ono_hits = [w for w in o_cfg.get("words", []) if w in body]
    ono_n = sum(body.count(w) for w in o_cfg.get("words", []))
    res["metrics"]["onomatopoeia_count"] = ono_n
    ono_cap = o_cfg.get("max_per_1000", 3)
    if ono_n >= 2 and ono_n / per_k > ono_cap:
        res["warnings"].append(
            f"擬聲詞 {ono_n} 次 / {total} 字(上限 {ono_cap}/千字):{'、'.join(ono_hits[:8])}"
            "——能不用就不用,滿篇「啪、轟、啊」會顯得幼稚")

    # ---- 3. 成語密度(需 --genre;沒指定就只報數,不判定)
    idiom_n = sum(body.count(w) for w in i_cfg.get("list", []))
    res["metrics"]["idiom_count"] = idiom_n
    res["metrics"]["idiom_per_1000"] = round(idiom_n / per_k, 2)
    genres = i_cfg.get("genres", {})
    if genre:
        band = genres.get(genre, {}).get("per_1000")
        if band:
            lo, hi = band
            d = idiom_n / per_k
            label = genres[genre]["label"]
            if d > hi:
                res["warnings"].append(
                    f"成語密度 {d:.1f}/千字,高於 {label} 的 {lo}-{hi}"
                    "——密集用典會把細節的獨特性抹掉")
            elif d < lo:
                res["warnings"].append(
                    f"成語密度 {d:.1f}/千字,低於 {label} 的 {lo}-{hi}"
                    "——這個流派靠成語撐氣勢與速度感,太素會失去節奏")
    else:
        res["warnings"].append(
            f"未指定 --genre,成語密度 {res['metrics']['idiom_per_1000']}/千字 **只報數不判定**"
            f"(可選:{'、'.join(genres)})")

    # ---- 4. 章節字數
    lo, hi = m_cfg["chapter_chars"]
    for start, title, lines in chapters:
        n = char_len("".join(lines))
        if n < lo:
            res["warnings"].append(f"第 {start} 行「{title}」只有 {n} 字(建議 {lo}-{hi},{m_cfg['label']})")
        elif n > hi:
            res["warnings"].append(f"第 {start} 行「{title}」有 {n} 字(建議 {lo}-{hi},{m_cfg['label']})")

    res["ok"] = not res["hard"]
    return res


def report(res: dict) -> None:
    print(f"\n=== {res['file']} — {res['chars']} 字 / {res['paragraphs']} 段 / "
          f"{res['chapters']} 章 · 模式 {res['mode']} ===")
    if res["hard"]:
        print(f"\n✗ 硬性違規 {len(res['hard'])} 處(必須改):")
        for h in res["hard"]:
            print(f"  L{h['line']}  {h['term']}「{h['matched']}」  → {h['fix']}")
    else:
        print("\n✓ 硬性違規:無")

    m = res["metrics"]
    print(f"\n密度:擬聲詞 {m.get('onomatopoeia_count')} 次 · 成語 {m.get('idiom_count')} 次"
          f"({m.get('idiom_per_1000')}/千字) · 最長純對話 {m.get('max_pure_dialogue_run')} 段")

    if res["warnings"]:
        print(f"\n⚠ 提醒 {len(res['warnings'])} 則:")
        for w in res["warnings"]:
            print(f"  · {w}")
    else:
        print("\n✓ 無提醒")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="小說技術規範 lint")
    ap.add_argument("files", nargs="+", help="要檢查的稿件(.md / .txt)")
    ap.add_argument("--rules", default=str(DEFAULT_RULES), help="規則檔路徑")
    ap.add_argument("--mode", default="print", help="print(實體出版)| web(網路連載)")
    ap.add_argument("--genre", default=None,
                    help="流派,用於成語密度判定:wuxia / scifi / mystery / romance / flash / long")
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
    if args.mode not in rules.get("modes", {}):
        print(f"ERROR: --mode 只接受 {'/'.join(rules.get('modes', {}))}", file=sys.stderr)
        return 2
    if args.genre and args.genre not in rules.get("idioms", {}).get("genres", {}):
        print(f"ERROR: --genre 只接受 {'/'.join(rules['idioms']['genres'])}", file=sys.stderr)
        return 2

    results, failed = [], False
    for f in args.files:
        p = Path(f)
        if not p.is_file():
            print(f"ERROR: 找不到檔案 {p}", file=sys.stderr)
            return 2
        res = analyse(p, rules, args.mode, args.genre)
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
