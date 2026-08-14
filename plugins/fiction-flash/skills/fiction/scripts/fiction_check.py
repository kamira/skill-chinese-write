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
    # 分母用**真實字數**。原本寫 max(total, 1000)/1000,任何短於 1000 字的稿件密度都被
    # 系統性低報——武俠 good 夾具 8 次 / 536 字(真實 14.9/千字,超過上限 14)被印成
    # 「8.0/千字」綠燈放行,而六份小說夾具全部短於 1000 字,於是成語密度這條規則
    # 從來沒有被任何輸入真正跑到過(CHG-20260813-01 D-1;KN-001 第九次)。
    # 樣本太短時**明說未驗到**,不拿一個扭曲的數字冒充判過。
    per_k = total / 1000 if total else 0.0
    # 兩個門檻**分開判**。初版用 min() 併成一個:日後把 idioms.min_sample_chars 調到 600
    # 而擬聲詞留 300,min() 取 300,成語密度照樣在 400 字樣本上判定——調高的旋鈕
    # 靜默無效;而且一則警告同時替兩個指標宣告未驗到,實際可能只有一個沒過(V5 審議)。
    idiom_min = i_cfg.get("min_sample_chars", 300)
    ono_min = o_cfg.get("min_sample_chars", 300)
    idiom_short = total < idiom_min
    ono_short = total < ono_min
    min_chars = min(idiom_min, ono_min)
    too_short = idiom_short

    res = {"file": str(path), "mode": mode, "genre": genre, "chars": total,
           "paragraphs": len(paragraphs), "chapters": len(chapters),
           "hard": [], "warnings": [], "notices": [], "metrics": {}}

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
    if ono_short:
        res["metrics"]["onomatopoeia_per_1000"] = None
    elif ono_n >= 2 and ono_n / per_k > ono_cap:
        res["warnings"].append(
            f"擬聲詞 {ono_n} 次 / {total} 字(上限 {ono_cap}/千字):{'、'.join(ono_hits[:8])}"
            "——能不用就不用,滿篇「啪、轟、啊」會顯得幼稚")

    # ---- 3. 成語密度(需 --genre;沒指定就只報數,不判定)
    idiom_n = sum(body.count(w) for w in i_cfg.get("list", []))
    res["metrics"]["idiom_count"] = idiom_n
    res["metrics"]["idiom_per_1000"] = None if too_short else round(idiom_n / per_k, 2)
    genres = i_cfg.get("genres", {})
    # 兩個指標**各自宣告**。先前只掛在 idiom_short 上,而且一則通知同時替兩者宣告未驗到——
    # 若日後 ono_min > idiom_min,擬聲詞未驗到會完全靜默(A 項複審抓到的潛伏缺口)。
    # 放 notices 不放 warnings:這是**通知**不是**提醒**——--strict 只該把
    # 「文章有問題」打紅,不該把「這項沒驗到」也打紅(V5 審議)。
    for _short, _min, _what in ((idiom_short, idiom_min, "成語"),
                                (ono_short, ono_min, "擬聲詞")):
        if _short:
            res["notices"].append(
                f"樣本只有 {total} 字(低於 {_min} 字),{_what}密度 **未驗到**"
                "——短樣本的密度沒有統計意義,不判定也不冒充判過")
    if too_short:
        pass
    elif genre:
        band = genres.get(genre, {}).get("per_1000")
        if band:
            lo, hi = band
            d = idiom_n / per_k
            label = genres[genre]["label"]
            # 只有上限。原文沒有任何流派說過「至少要幾個」,下限是自己發明的;
            # 而且下限的理由對科幻與懸疑是反的——它們寫到 0 個成語是做對了。
            if d > hi:
                res["warnings"].append(
                    f"成語密度 {d:.1f}/千字,高於 {label} 的上限 {hi}"
                    "——密集用典會把細節的獨特性抹掉")
    else:
        res["notices"].append(
            f"未指定 --genre,成語密度 {res['metrics']['idiom_per_1000']}/千字 **只報數不判定**"
            f"(可選:{'、'.join(genres)})")

    # ---- 3. markdown 強調記號(CHG-20260813-01 D-5)
    f_cfg = rules.get("formatting", {})
    emph = f_cfg.get("emphasis_pattern")
    if emph:
        # 注意用 raw 不用 body:parse() 會先 strip_md(),body 裡的記號早就被拿掉了。
        # 這正是這條規則以前抓不到東西的原因之一——它要查的東西在解析階段就被清掉。
        n_emph = len(re.findall(emph, raw))
        res["metrics"]["emphasis_marks"] = n_emph
        if n_emph:
            res["warnings"].append(
                f"敘事文裡有 {n_emph} 處 markdown 強調記號(**…** / __…__)"
                "——小說靠句子本身給重音,粗體是寫文件的殘留")

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
    # 樣本過短時 idiom_per_1000 是 None——印「未驗到」,不要印 None,更不要印一個假數字。
    per_k_txt = ("未驗到" if m.get("idiom_per_1000") is None
                 else f"{m.get('idiom_per_1000')}/千字")
    print(f"\n密度:擬聲詞 {m.get('onomatopoeia_count')} 次 · 成語 {m.get('idiom_count')} 次"
          f"({per_k_txt}) · 最長純對話 {m.get('max_pure_dialogue_run')} 段")

    # 通知與提醒分開印。notices 是「這項沒驗到」這類資訊,--strict 不打紅;
    # 先前只收集不印,等於「明說未驗到」這件事對使用者完全不可見(A 項複審後補)。
    if res.get("notices"):
        print(f"\nℹ 通知 {len(res['notices'])} 則(不影響判定,--strict 也不打紅):")
        for nt in res["notices"]:
            print(f"  · {nt}")

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
    ap.add_argument("--strict", action="store_true",
                    help="把提醒也當成失敗(exit 1)。CI 用:密度這類規則只出提醒,"
                         "沒有這個旗標就沒有任何辦法讓它在 CI 裡變成紅燈——"
                         "規則存在但閘不可達,等於沒有(CHG-20260813-01 D-1)")
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
        res["strict_failed"] = args.strict and bool(res["warnings"])
        failed = failed or not res["ok"] or res["strict_failed"]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for res in results:
            report(res)
        if failed and args.strict and all(r["ok"] for r in results):
            print("\n✗ --strict:有提醒即視為失敗。")
        else:
            print("\n" + ("✗ 有硬性違規,回去改。" if failed else "✓ 過。剩下的提醒自己判斷。"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
