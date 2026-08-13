#!/usr/bin/env python3
"""
style_check.py — 評論文章風格 lint(唯讀;不改任何檔)

檢查五組:
  1. 硬性違規 —— 禁用詞句、缺第一人稱「我」、結尾討拍、短句收尾  → exit 1
  2. 節奏     —— 句長變異係數、平板連段、超長句、缺短句、段落輕重 → 警告
  3. 刻意句   —— 對稱/明喻/反差的總量、間隔、段末密度            → 警告
  4. 軟性     —— 軟限詞密度、陸味用語、模板形狀                  → 警告
  5. 版面     —— 條列佔比與單項長度、小標、破折號、粗體          → 警告

條列與標題不進句子層級的統計(它們本來就短而齊,拿散文標準量必然誤報),
但禁用詞與密度類仍全文適用。引號內的命中不計入刻意句(use/mention)。
規則只支援中文——英文請當範例看,勿據以判定。

規則的單一真相是 assets/style_rules.json;要加詞或調門檻改那份,不要改本腳本。

用法:
  python3 skills/writing/scripts/style_check.py 稿件.md
  python3 skills/writing/scripts/style_check.py 稿件.md --allow 制度,窗口
  python3 skills/writing/scripts/style_check.py 稿件.md --json
  python3 skills/writing/scripts/style_check.py a.md b.md --rules /path/to/style_rules.json

退出碼:0 通過(可能有警告)| 1 有硬性違規 | 2 環境/參數錯誤
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

# 釘住輸出編碼(CHG-20260803-01 T1):不依賴主控台/locale 的 ambient 編碼。
# 非 UTF-8 主控台(如 Windows cp932)印 CJK/emoji 會 UnicodeEncodeError;
# 釘住後同一份程式在任何平台的輸出行為一致。errors="replace" 確保永不因輸出而崩潰。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_RULES = Path(__file__).resolve().parent.parent / "assets" / "style_rules.json"
PUNCT = set("，。、；：？！「」『』（）()〈〉《》〔〕—…⋯·,.;:?!-_*#>|[]`~/\\+=<>@$%^&{}\"'“”‘’")
SENT_END = "。！？!?"
CLAUSE_SEP = "，,、；;：:"
BULLET_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.、)]\s+)")
HEADING_RE = re.compile(r"^\s*(?:#{1,6}\s*|>\s*)")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")


def char_len(s: str) -> int:
    return sum(1 for ch in s if not ch.isspace() and ch not in PUNCT)


def strip_md(line: str) -> str:
    line = LINK_RE.sub(r"\1", line)
    line = HEADING_RE.sub("", line)
    line = BULLET_RE.sub("", line)
    return line.replace("**", "").replace("`", "").strip()


def prepare(raw: str):
    """回傳 (prose_lines, all_lines, fenced_removed) —— prose_lines 為 (行號, 已去 markdown 的文字)。"""
    all_lines = raw.split("\n")
    prose, bullets, headings, in_fence = [], [], [], False
    for i, line in enumerate(all_lines, 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.lstrip().startswith("|"):      # 表格屬結構,不入散文統計
            continue
        text = strip_md(line)
        if not text:
            continue
        if HEADING_RE.match(line):             # 標題自有檢查,不混進句子統計
            headings.append((i, text))
            continue
        if BULLET_RE.match(line):              # 條列本來就短而齊,拿散文標準量必然誤報
            bullets.append((i, text))
            continue
        prose.append((i, text))
    return prose, all_lines, bullets, headings


def split_sentences(prose):
    out = []
    for lineno, text in prose:
        buf = ""
        for ch in text:
            buf += ch
            if ch in SENT_END:
                if char_len(buf) > 0:
                    out.append((lineno, buf.strip()))
                buf = ""
        if char_len(buf) > 0:
            out.append((lineno, buf.strip()))
    return out


def strip_quoted(text: str) -> str:
    """挖掉引號內的內容。討論「像」這個字時不該被算成明喻——use/mention 之分。"""
    for a, b in (("「", "」"), ("『", "』"), ("“", "”"), ('"', '"')):
        text = re.sub(re.escape(a) + "[^" + re.escape(b) + "]*" + re.escape(b), a + b, text)
    return text


def heading_check(headings, cfg):
    """小標本身要有內容。議題型的三個必要節屬功能名,放行。"""
    allow = set(cfg.get("issue_sections", []))
    bad = []
    for lineno, text in headings:
        t = text.strip()
        if t in allow:
            continue
        for w in cfg.get("discouraged", []):
            if t == w or t.rstrip("::") == w:
                bad.append({"line": lineno, "text": t})
                break
    return bad


def stats(nums):
    n = len(nums)
    if n == 0:
        return 0.0, 0.0, 0.0
    mean = sum(nums) / n
    var = sum((x - mean) ** 2 for x in nums) / n
    sd = var ** 0.5
    return mean, sd, (sd / mean if mean else 0.0)


def find_hard(prose, rules, allow):
    hits = []
    for rule in rules.get("hard_bans", []):
        label = rule.get("label") or rule.get("term", "")
        if label in allow:
            continue
        rx = re.compile(rule["pattern"]) if "pattern" in rule else re.compile(re.escape(rule["term"]))
        for lineno, text in prose:
            for m in rx.finditer(text):
                hits.append({"line": lineno, "term": label, "matched": m.group(0),
                             "group": rule.get("group", ""), "fix": rule.get("fix", "")})
    hits.sort(key=lambda h: (h["line"], h["term"]))
    return hits


def count_term(prose, term):
    return sum(text.count(term) for _, text in prose)


def count_rule(prose, rule):
    """soft_limits 條目:字面詞用 count,regex 用 findall。回傳 (顯示名, 次數)。"""
    if "pattern" in rule:
        rx = re.compile(rule["pattern"])
        return rule.get("label", rule["pattern"]), sum(len(rx.findall(t)) for _, t in prose)
    return rule["term"], count_term(prose, rule["term"])


def paragraphs_of(raw: str):
    """實質段落(去標題/條列/表格/程式碼/引用),回傳 [(起始行號, 純文字)]。"""
    out, in_fence, buf, start = [], False, [], 0
    for i, line in enumerate(raw.split("\n"), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        s = line.strip()
        if not s or s.startswith(("|", "#", ">")) or BULLET_RE.match(line):
            if buf:
                out.append((start, "".join(buf)))
                buf = []
            continue
        if not buf:
            start = i
        buf.append(strip_md(line))
    if buf:
        out.append((start, "".join(buf)))
    return out


def symmetric_sentences(sentences, cfg):
    """對稱句 = 同一句內存在相鄰兩個分句字數相同(且長度達門檻)。"""
    found = []
    min_c = cfg.get("min_clause_chars", 4)
    for idx, (lineno, sent) in enumerate(sentences):
        clauses = [c for c in re.split(f"[{CLAUSE_SEP}]", sent) if char_len(c) > 0]
        if len(clauses) < 2:
            continue
        lens = [char_len(c) for c in clauses]
        for a, b in zip(lens, lens[1:]):
            if a == b and a >= min_c:
                found.append({"index": idx, "line": lineno, "clause_chars": a,
                              "text": sent[:40]})
                break
    return found


def matched_sentences(sentences, pattern):
    """回傳命中 pattern 的句子。用於明喻(帶「像」的比喻)與工整反差(擋得住⋯,擋不住⋯)。
    隱喻不收——它跟一般敘述沒辦法機器區分。"""
    if not pattern:
        return []
    rx = re.compile(pattern)
    return [{"index": i, "line": ln, "text": s[:40]}
            for i, (ln, s) in enumerate(sentences) if rx.search(s)]


def analyse(path: Path, rules: dict, allow: set) -> dict:
    raw = path.read_text(encoding="utf-8")
    prose, all_lines, bullets, headings = prepare(raw)
    # 句子層級的統計只吃散文;禁用詞與密度類必須全文適用,條列與標題也算
    all_text = sorted(prose + bullets + headings, key=lambda x: x[0])
    sentences = split_sentences(prose)
    lengths = [char_len(s) for _, s in sentences]
    total_chars = sum(lengths)
    # 短稿不放大密度:1000 字以下,「每千字上限」直接當絕對次數上限。否則一篇 400 字的稿子
    # 出現一次軟限詞就會被判超標,警告變雜訊。
    # 分母用真實字數。原本是 max(total_chars, 1000)/1000——實測 repo 內 24/24 份夾具
    # 全部短於 1000 字,於是每一條 per_1000 規則都被系統性低報(129 字的稿被除以 1000,
    # 低報近 8 倍),密度類規則從來沒有一次用對過分母(CHG-20260813-01 D-1)。
    per_k = total_chars / 1000 if total_chars else 0.0
    density_verifiable = total_chars >= rules.get("min_sample_chars", 300)

    r = rules.get("rhythm", {})
    sym_cfg = rules.get("symmetry", {})
    p_cfg = rules.get("person", {})
    l_cfg = rules.get("layout", {})

    res = {"file": str(path), "chars": total_chars, "sentences": len(sentences),
           "hard": [], "warnings": [], "metrics": {}}

    # 樣本過短時**明說未驗到**。規則檔的 min_sample_chars_reason 白紙黑字承諾了
    # 「並明說未驗到」,而初版只是靜默跳過——同一個逃生門在這裡沒堵(V5 審議)。
    if not density_verifiable:
        res["warnings"].append(
            f"樣本只有 {total_chars} 字(低於 {rules.get('min_sample_chars', 300)} 字),密度類規則 **未驗到**"
            "——短樣本的密度沒有統計意義,不判定也不冒充判過")

    # 1. 硬性:禁用詞
    res["hard"] = find_hard(all_text, rules, allow)

    # 1. 硬性:第一人稱
    joined = "".join(t for _, t in all_text)
    me = len(re.findall(r"我(?!們)", joined))
    first_at = None
    m = re.search(r"我(?!們)", joined)
    if m:
        first_at = char_len(joined[:m.start()])
    res["metrics"]["first_person_count"] = me
    res["metrics"]["first_person_at"] = first_at
    if p_cfg.get("require_first_person", True):
        if me == 0:
            res["hard"].append({"line": 0, "term": "(缺第一人稱)", "matched": "",
                                "group": "第一人稱", "fix": "全篇找不到「我」——評論要有人站出來"})
        elif first_at is not None and first_at > p_cfg.get("first_hit_within_chars", 200):
            res["warnings"].append(f"第一人稱出現太晚:第 {first_at} 字才看到「我」"
                                   f"(門檻 {p_cfg.get('first_hit_within_chars', 200)})")

    hedge_n = sum(joined.count(h) for h in p_cfg.get("hedges", []))
    if density_verifiable and hedge_n / per_k > p_cfg.get("max_hedge_per_1000", 3):
        res["warnings"].append(f"「我認為/我覺得」太密({hedge_n} 次 / {total_chars} 字)——判斷句直接講就好")

    # 2. 節奏
    mean, sd, cv = stats(lengths)
    res["metrics"].update({"mean_len": round(mean, 1), "sd_len": round(sd, 1), "cv": round(cv, 3),
                           "min_len": min(lengths) if lengths else 0,
                           "max_len": max(lengths) if lengths else 0})
    if len(lengths) >= 3:
        if cv < r.get("min_cv", 0.35):
            res["warnings"].append(f"節奏平板:句長變異係數 {cv:.2f} < {r.get('min_cv', 0.35)}"
                                   f"(健康值 {r.get('healthy_cv', 0.45)} 以上)——長句之後補短句")
        run_len = r.get("flat_run_len", 3)
        tol = r.get("flat_run_tolerance", 2)
        flat = []
        for i in range(len(lengths) - run_len + 1):
            window = lengths[i:i + run_len]
            if max(window) - min(window) <= tol:
                flat.append({"line": sentences[i][0], "lens": window})
        res["metrics"]["flat_runs"] = len(flat)
        for f in flat[:5]:
            res["warnings"].append(f"第 {f['line']} 行起連續 {run_len} 句長度接近 {f['lens']}——打散它")
        if flat and len(flat) > 5:
            res["warnings"].append(f"(平板連段共 {len(flat)} 處,只列前 5)")
        long_s = [(ln, L) for (ln, _), L in zip(sentences, lengths) if L > r.get("max_sentence_chars", 60)]
        for ln, L in long_s[:5]:
            res["warnings"].append(f"第 {ln} 行有 {L} 字的長句(上限 {r.get('max_sentence_chars', 60)})——斷開")
        short_gate = r.get("require_short_sentence_under", 8)
        if lengths and min(lengths) > short_gate:
            res["warnings"].append(f"全篇最短的句子有 {min(lengths)} 字——至少放一句 {short_gate} 字以內的重擊")

    # 2b. 節奏:段落層級(句子參差但每段一樣重,讀起來一樣平)
    p_r = r.get("paragraph", {})
    paras = [(ln, t) for ln, t in paragraphs_of(raw) if char_len(t) >= p_r.get("min_chars", 20)]
    plens = [char_len(t) for _, t in paras]
    res["metrics"]["para_count"] = len(plens)
    if len(plens) >= p_r.get("min_count", 4):
        _, _, pcv = stats(plens)
        res["metrics"]["para_cv"] = round(pcv, 3)
        if max(plens) - min(plens) <= p_r.get("max_flat_range", 25):
            res["warnings"].append(f"{len(plens)} 個段落長度全擠在 {min(plens)}–{max(plens)} 字之間"
                                   "——每段一樣重,讀者會先覺得順、再覺得假。插一個短段進去")
        elif pcv < p_r.get("min_cv", 0.25):
            res["warnings"].append(f"段落節奏偏平:段長變異係數 {pcv:.2f} < {p_r.get('min_cv', 0.25)}"
                                   "——短拍、中段、厚段、短落地,輪著來")

    # 2c. 結尾:互動問句(純反詰不算——閘門是有沒有點名讀者)
    e_cfg = rules.get("ending", {})
    if e_cfg.get("forbid_engagement_question", True) and sentences:
        for lineno, sent in sentences[-max(1, e_cfg.get("tail_sentences", 1)):]:
            if sent.rstrip().endswith(("?", "?")) and any(
                    m in sent for m in e_cfg.get("person_markers", ["你", "大家"])):
                res["hard"].append({"line": lineno, "term": "(結尾互動問句)", "matched": sent[:30],
                                    "group": "結尾互動",
                                    "fix": "刪掉。評論的結尾要往前推半步,不是回頭討拍;不點名讀者的反詰不受此限"})

    # 2d. 結尾:不准拿一句短話當總結
    min_fin = e_cfg.get("min_final_sentence_chars", 0)
    if min_fin and sentences:
        fin_line, fin_text = sentences[-1]
        fin_len = char_len(fin_text)
        res["metrics"]["final_sentence_chars"] = fin_len
        if fin_len < min_fin:
            res["hard"].append({"line": fin_line, "term": "(短句收尾)", "matched": fin_text[:30],
                                "group": "結尾",
                                "fix": f"最後一句只有 {fin_len} 字(下限 {min_fin})——不要拿一句短話作總結。"
                                       "把它併進前一句,或往後多寫一層,讓文章停在還開著的狀態"})

    # 3. 對稱句
    sym = symmetric_sentences(sentences, sym_cfg)
    res["metrics"]["symmetry_count"] = len(sym)
    cap = sym_cfg.get("max_total", 3)
    if len(sym) > cap:
        res["warnings"].append(f"對稱句 {len(sym)} 處,超過配額 {cap}——只留最該敲的那幾下"
                               f"(行:{[s['line'] for s in sym][:8]})")
    gap = sym_cfg.get("min_gap_sentences", 3)
    for a, b in zip(sym, sym[1:]):
        if b["index"] - a["index"] < gap:
            res["warnings"].append(f"第 {a['line']} 與 {b['line']} 行的對稱句挨太近(需隔 {gap} 句)——連用會變順口溜")

    # 3b. 刻意句總量:明喻 + 對稱句。偶爾可以,不能是常態
    a_cfg = rules.get("aphorism", {})
    unquoted = [(ln, strip_quoted(s)) for ln, s in sentences]
    sim = matched_sentences(unquoted, a_cfg.get("simile_pattern"))
    anti = matched_sentences(unquoted, a_cfg.get("antithesis_pattern"))
    res["metrics"]["simile_count"] = len(sim)
    res["metrics"]["antithesis_count"] = len(anti)
    crafted = sorted({s["index"]: s for s in sim + anti + sym}.values(), key=lambda s: s["index"])
    res["metrics"]["crafted_count"] = len(crafted)
    a_cap = a_cfg.get("crafted_max", 3)
    if len(crafted) > a_cap:
        res["warnings"].append(f"刻意句 {len(crafted)} 處(明喻 {len(sim)} + 反差 {len(anti)} + 對稱 {len(sym)}),超過總量 {a_cap}"
                               f"(行:{[c['line'] for c in crafted][:8]})"
                               "——雕過的句子偶爾可以,不能是常態;留最該敲的那幾下,其餘拆成平話")
    a_gap = a_cfg.get("min_gap_sentences", 3)
    for a, b in zip(crafted, crafted[1:]):
        if b["index"] - a["index"] < a_gap:
            res["warnings"].append(f"第 {a['line']} 與 {b['line']} 行的刻意句挨太近(需隔 {a_gap} 句)")
            break

    # 3c. 段末斷語:刻意句落在段落收尾的位置最容易堆積
    para_ends = set()
    for _, ptext in paragraphs_of(raw):
        tail = [s for s in re.split(r"(?<=[。!?！？])", ptext) if char_len(s) > 0]
        if tail:
            para_ends.add(tail[-1].strip())
    closers = [c for c in crafted if any(c["text"][:12] and c["text"][:12] in e for e in para_ends)]
    res["metrics"]["crafted_closers"] = len(closers)
    c_cap = a_cfg.get("closer_max", 2)
    if len(closers) > c_cap:
        res["warnings"].append(f"落在段末的刻意句有 {len(closers)} 處(上限 {c_cap})"
                               "——每段都用一句金句收尾,讀起來就是在擺姿勢")

    # 4. 軟性:詞密度
    soft_over = []
    for rule in rules.get("soft_limits", []):
        label, n = count_rule(all_text, rule)
        # min_count 預設 2:字面詞出現一次不算問題(KN-002 防誤報)。
        # 句型殼不一樣——出現一次就是那個殼,所以那類條目自己設 min_count: 1。
        if (density_verifiable and n >= rule.get("min_count", 2)
                and n / per_k > rule["per_1000"]):
            soft_over.append(f"{label}×{n}(上限 {rule['per_1000']}/千字)")
    res["metrics"]["soft_over"] = soft_over
    if soft_over:
        res["warnings"].append("軟限詞超標:" + "、".join(soft_over))

    # 4b. 模板形狀:「X 很 X」連發與「標籤:解釋」冒號行
    s_cfg = rules.get("shape", {})
    hen = [ln for ln, s in sentences if re.search(r"[^，,。!?\n]{1,12}很[^，,。!?\n]{1,8}[。!]$", s)]
    res["metrics"]["hen_judgments"] = len(hen)
    if len(hen) > s_cfg.get("hen_judgment_max", 2):
        res["warnings"].append(f"「X 很 X」判斷句 {len(hen)} 句(行:{hen[:6]})"
                               "——併掉一句、縮短一句、把一句換成具體的東西")
    lab = s_cfg.get("colon_label_max_chars", 12)
    colon = [ln for ln, t in prose if re.match(rf"^[^：:\n]{{2,{lab}}}[：:]\S", t)]
    res["metrics"]["colon_lines"] = len(colon)
    if len(colon) > s_cfg.get("colon_template_max", 2):
        res["warnings"].append(f"「標籤:解釋」式的行有 {len(colon)} 行(行:{colon[:6]})"
                               "——冒號只在句子自然要它的時候用,不然整篇會像投影片")

    # 4. 軟性:陸味用語
    locale = []
    for rule in rules.get("locale_swaps", []):
        n = count_term(all_text, rule["cn"])
        if n:
            locale.append(f"{rule['cn']}×{n} → {rule['tw']}")
    res["metrics"]["locale_hits"] = locale
    if locale:
        res["warnings"].append("陸味用語:" + "、".join(locale))

    # 4. 軟性:排版
    body = [ln for ln in all_lines if ln.strip()]
    bullet_lines = [ln for ln in body if BULLET_RE.match(ln)]
    ratio = len(bullet_lines) / len(body) if body else 0.0
    res["metrics"]["bullet_ratio"] = round(ratio, 3)
    if ratio > l_cfg.get("max_bullet_ratio", 0.15):
        res["warnings"].append(f"條列佔 {ratio:.0%},超過 {l_cfg.get('max_bullet_ratio', 0.15):.0%}"
                               "——評論是散文,論證用文字推")
    dashes = raw.count("——")
    res["metrics"]["em_dash"] = dashes
    if density_verifiable and dashes / per_k > l_cfg.get("max_em_dash_per_1000", 4):
        res["warnings"].append(f"破折號 {dashes} 個 / {total_chars} 字——太多代表你不會用句號")
    # 4c. 條列:只放扼要重點,禁止完整說明
    b_cfg = rules.get("bullets", {})
    res["metrics"]["bullet_count"] = len(bullets)
    b_max = b_cfg.get("max_chars", 0)
    long_b = [(ln, char_len(tx)) for ln, tx in bullets if b_max and char_len(tx) > b_max]
    res["metrics"]["long_bullets"] = len(long_b)
    for ln, n in long_b[:5]:
        res["warnings"].append(f"第 {ln} 行的條列有 {n} 字(上限 {b_max})"
                               "——條列只放扼要重點,完整說明寫進段落裡")

    # 4d. 小標:本身要有內容
    h_cfg = rules.get("headings", {})
    res["metrics"]["heading_count"] = len(headings)
    for h in heading_check(headings, h_cfg)[:5]:
        res["warnings"].append(f"第 {h['line']} 行的小標「{h['text']}」是結構標籤"
                               "——小標本身要有內容,最好就是一個判斷或一個具體問題")

    for para in re.split(r"\n\s*\n", raw):
        body = "\n".join(ln for ln in para.split("\n") if not BULLET_RE.match(ln))
        if len(BOLD_RE.findall(body)) > l_cfg.get("max_bold_per_paragraph", 1):
            res["warnings"].append("有段落粗體超過一處——粗體是重音,不是螢光筆")
            break

    res["ok"] = not res["hard"]
    return res


def report(res: dict) -> None:
    print(f"\n=== {res['file']} — {res['chars']} 字 / {res['sentences']} 句 ===")
    if res["hard"]:
        print(f"\n✗ 硬性違規 {len(res['hard'])} 處(必須改):")
        for h in res["hard"]:
            where = f"L{h['line']}" if h["line"] else "全篇"
            print(f"  {where}  {h['term']}" + (f"「{h['matched']}」" if h["matched"] else "")
                  + (f"  → {h['fix']}" if h["fix"] else ""))
    else:
        print("\n✓ 硬性違規:無")

    m = res["metrics"]
    print(f"\n節奏:平均 {m.get('mean_len')} 字 / 最短 {m.get('min_len')} / 最長 {m.get('max_len')}"
          f" / CV {m.get('cv')} · 刻意句 {m.get('crafted_count')} 處"
          f"(對稱 {m.get('symmetry_count')} / 明喻 {m.get('simile_count')} / 反差 {m.get('antithesis_count')}"
          f",段末 {m.get('crafted_closers')})"
          f" · 我×{m.get('first_person_count')}")

    if res["warnings"]:
        print(f"\n⚠ 提醒 {len(res['warnings'])} 則:")
        for w in res["warnings"]:
            print(f"  · {w}")
    else:
        print("\n✓ 無提醒")


# 句型殼規則的紅綠端測資。**這一組是使用者實測給的反例。**
# 「生造的帶勁口語」這條腳本判不準,斷言只抓最有把握的形狀;收窄之後如果有人把
# regex 放寬,下面五個合法句會重新被誤殺——所以把它們釘成 self-test,
# 誤殺即紅。收窄本身也要有斷言,否則它就是一次沒人守得住的修正(KN-001)。
SHELL_CASES = [
    # (句子, 該不該被抓, 為什麼)
    ("鑽石是自然界最硬的礦物", False, "物性比較,「硬」是字面義"),
    ("這是我遇過最硬的材質", False, "同上"),
    ("他不想把話講死", False, "台灣口語,意思是不留餘地"),
    ("我不想把話講這麼死", False, "同上"),
    ("這件事還不能說死", False, "同上"),
    ("我知道最硬的反駁在哪裡", True, "拿強度詞修飾論述性名詞"),
    ("最狠的批評來自他自己", True, "同上"),
    ("還有一件事我想講死", True, "拿它當「最重要的是」在用"),
]
SHELL_LABELS = ("生造強度形容", "生造動詞加碼")

# 條列長度的紅綠端測資。**左欄是 agent 實際產出、被使用者指為 AI 味的寫法,
# 右欄是使用者給的改法。** 規則檔的 _doc 早就寫著「禁止完整說明」,而斷言原本
# 只查長度、門檻 16 字——左欄 9/10/10 字全部合法通過(KN-001:規則說一件事,
# 斷言查另一件)。門檻收到 8 字才切得開,這組測資把它釘住。
BULLET_CASES = [
    # 只驗**明顯過長**的兜底。一度把「一餐的成本壓得下來」(9 字)也釘成該擋,
    # 依據只有單一實例;使用者指出那是過度一般化——不同文章的條列該多長不一樣。
    # 「壓縮夠不夠」現在靠人讀,不在這裡假裝有閘(見 style_rules.bullets)。
    ("這一項寫得又臭又長還把整段說明全部塞進來當作條列", True),
    ("降低成本", False),
    ("單一稽核單位", False),
    ("校方不需廚工", False),
    ("一餐的成本壓得下來", False),   # 寫成句子,但不由機器判——靠人
]


def self_test(rules) -> int:
    """句型殼規則的紅綠端可達自檢。"""
    pats = [re.compile(e["pattern"]) for e in rules.get("soft_limits", [])
            if any(e.get("label", "").startswith(x) for x in SHELL_LABELS)]
    if not pats:
        print("  ❌ 找不到句型殼規則——規則被刪掉了,這道自檢等於沒跑")
        return 1
    fails = []
    for s, want, why in SHELL_CASES:
        hit = any(rx.search(s) for rx in pats)
        if hit != want:
            fails.append(f"「{s}」預期{'該抓' if want else '不該抓'}、實際"
                         f"{'抓到' if hit else '沒抓'}({why})")
    if fails:
        for f in fails:
            print(f"  ❌ {f}")
        print("\n✗ self-test 未通過:句型殼規則誤殺了合法用法,或漏掉了該抓的形狀。")
        return 1
    b_max = rules.get("bullets", {}).get("max_chars", 0)
    if not b_max:
        fails.append("條列長度上限沒有設定——這條規則等於沒有")
    for s, want in BULLET_CASES:
        hit = b_max and char_len(s) > b_max
        if bool(hit) != want:
            fails.append(f"條列「{s}」({char_len(s)} 字)預期"
                         f"{'該擋' if want else '該過'}、實際"
                         f"{'擋下' if hit else '放行'}(上限 {b_max})")
    if fails:
        for f in fails:
            print(f"  ❌ {f}")
        print("\n✗ self-test 未通過。")
        return 1
    print(f"✅ self-test:句型殼 {len(SHELL_CASES)} 個測資全對"
          f"(5 個合法用法不誤殺、3 個生造形狀抓得到);"
          f"條列 {len(BULLET_CASES)} 個測資全對(兜底 {b_max} 字;壓縮夠不夠靠人讀)。")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="評論文章風格 lint")
    ap.add_argument("files", nargs="+", help="要檢查的稿件(.md / .txt)")
    ap.add_argument("--rules", default=str(DEFAULT_RULES), help="規則檔路徑")
    ap.add_argument("--allow", default="", help="個案放行的禁用詞,逗號分隔(限引用原文)")
    ap.add_argument("--json", action="store_true", help="輸出 JSON")
    ap.add_argument("--self-test", action="store_true",
                    help="句型殼規則的紅綠端自檢(使用者實測給的合法用法不得被誤殺)")
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

    if args.self_test:
        return self_test(rules)

    allow = {a.strip() for a in args.allow.split(",") if a.strip()}
    results, failed = [], False
    for f in args.files:
        p = Path(f)
        if not p.is_file():
            print(f"ERROR: 找不到檔案 {p}", file=sys.stderr)
            return 2
        res = analyse(p, rules, allow)
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
