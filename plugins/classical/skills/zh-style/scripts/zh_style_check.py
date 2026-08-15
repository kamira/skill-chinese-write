#!/usr/bin/env python3
"""
zh_style_check.py — 中文正字法與收尾(唯讀;不改任何檔)

**這是引擎,不是前門。**沒有人會說「幫我寫一篇正字法」,所以它沒有自己的 plugin;
所有 plugin 全部把它打包帶入。它收的是**不隨文體改變**的規則:

  1. 硬性 —— 中文脈絡下的半形標點(, : ; ? ! 括號)    → exit 1
  2. 警告 —— 最後一段的總結殼(有些X是這樣 / 不是A是B / 說到底 …)
  3. 警告 —— 最後一段兩句光禿的短陳述並排,第二句沒有連接詞

為什麼不塞進四支文體引擎:半形標點在散文與公文裡的判定**完全相同**,複製四份必然分岔
(KN-003:規則不隨文體改變就放共用引擎)。

**判不了的**:一段結尾「有沒有總結全文」需要語意理解,本檔只判**殼的形狀**;
哪一句是反轉句也判不了,所以那條只列警告——警告可以無視,硬性不行。

用法:
  python3 skills/zh-style/scripts/zh_style_check.py 稿件.md
  python3 skills/zh-style/scripts/zh_style_check.py 稿件.md --fix-preview
  python3 skills/zh-style/scripts/zh_style_check.py --self-test

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

DEFAULT_RULES = Path(__file__).resolve().parent.parent / "assets" / "zh_style_rules.json"
CJK = re.compile("[　-〿一-鿿＀-￯—…]")
FENCE = re.compile(r"^```", re.M)
INLINE_CODE = re.compile(r"`[^`\n]*`")
MD_LINK = re.compile(r"\[[^\]\n]*\]\([^)\n]*\)")
URL = re.compile(r"https?://\S+")
DIALOGUE_TAIL = re.compile(r"[」』]\s*[^。\n]{0,8}[說問答道]。?$")


def mask(text: str) -> str:
    """把半形本來就正確的區域換成同長度的空白:程式碼、連結、URL。
    用等長遮蔽而不是刪除,行號與位移才不會跑掉。"""
    def blank(m):
        return " " * (m.end() - m.start())
    out, in_fence = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(" " * len(line))
            continue
        if in_fence:
            out.append(" " * len(line))
            continue
        line = MD_LINK.sub(blank, line)
        line = URL.sub(blank, line)
        line = INLINE_CODE.sub(blank, line)
        out.append(line)
    return "\n".join(out)


def paragraphs(text: str):
    out, buf, start = [], [], 0
    in_fence = False
    for i, line in enumerate(text.split("\n"), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        s = line.strip()
        if not s or s.startswith(("#", "|", ">")):
            if buf:
                out.append((start, " ".join(buf)))
                buf = []
            continue
        if not buf:
            start = i
        buf.append(s.replace("**", "").replace("`", ""))
    if buf:
        out.append((start, " ".join(buf)))
    return out


def char_len(s: str) -> int:
    return len(re.sub(r"[，。、；：？！「」『』（）\s—…]", "", s))


def find_halfwidth(text: str, mapping: dict):
    """回傳 [(行號, 欄, 半形字元, 建議)]。只在中文相鄰時算違規。"""
    masked = mask(text)
    hits = []
    line_no, col = 1, 0
    for i, ch in enumerate(masked):
        if ch == "\n":
            line_no += 1
            col = 0
            continue
        col += 1
        if ch in mapping:
            prev = masked[i - 1] if i else ""
            nxt = masked[i + 1] if i + 1 < len(masked) else ""
            if CJK.match(prev) or CJK.match(nxt):
                hits.append((line_no, col, ch, mapping[ch]))
    return hits


def analyse(path: Path, rules: dict) -> dict:
    raw = path.read_text(encoding="utf-8")
    res = {"file": str(path), "hard": [], "warnings": [], "metrics": {}}

    hw = find_halfwidth(raw, rules["halfwidth"]["map"])
    res["metrics"]["halfwidth_count"] = len(hw)
    for line_no, col, ch, want in hw:
        res["hard"].append({"line": line_no, "col": col, "term": f"半形「{ch}」",
                            "fix": f"改成全形「{want}」"})

    paras = paragraphs(raw)
    if paras:
        last_line, last = paras[-1]
        res["metrics"]["last_paragraph_chars"] = char_len(last)

        es = rules["ending_shell"]
        for rule in es["patterns"]:
            if re.search(rule["pattern"], last):
                res["warnings"].append(
                    f"最後一段有總結殼「{rule['label']}」(第 {last_line} 行起)"
                    "——那是替讀者把意思講出來。改成具體的動作或事實,結論留給讀者自己得")

        fe = rules["flat_ending"]
        sents = [s.strip() for s in re.split(r"(?<=。)", last) if s.strip()]
        if len(sents) >= 2 and not DIALOGUE_TAIL.search(sents[-1]):
            a, b = sents[-2], sents[-1]
            cap = fe["max_chars"]
            if (char_len(a) <= cap and char_len(b) <= cap
                    and "，" not in b
                    and not any(b.startswith(c) for c in fe["connectives"])):
                res["warnings"].append(
                    f"結尾兩句都是光禿的短陳述,第二句沒有連接詞:「{a}{b}」"
                    "——加一個時間錨點把它接回前面(「這次,他沒有動。」),"
                    "或改用書面語的動詞。**反轉句可以無視這一條**")

    res["ok"] = not res["hard"]
    return res


def report(res: dict) -> None:
    print(f"\n=== {res['file']} ===")
    if res["hard"]:
        n = len(res["hard"])
        print(f"\n✗ 硬性違規 {n} 處(必須改):")
        for h in res["hard"][:12]:
            print(f"  L{h['line']}:{h['col']}  {h['term']}  → {h['fix']}")
        if n > 12:
            print(f"  (共 {n} 處,只列前 12)")
    else:
        print("\n✓ 硬性違規:無")

    if res["warnings"]:
        print(f"\n⚠ 提醒 {len(res['warnings'])} 則:")
        for w in res["warnings"]:
            print(f"  · {w}")
    else:
        print("\n✓ 無提醒")


# self-test 的字串必須是**自己造的**,不能借任何一份夾具的句子。
# 原本這一行與 skills/prose/assets/sample-good.md 的結尾逐字相同——引擎拿夾具的句子
# 當標準答案,等於用考古題驗考生;那份夾具因此永遠不可能在這支引擎上失敗
# (CHG-20260813-01 D-4)。
GOOD = "他站在門口，沒有說話。\n\n後來那把鑰匙一直放在鞋櫃上，誰也沒有再提起過它。\n"
BAD_HW = "他站在門口, 沒有說話。\n"
BAD_SHELL = "他站在門口，沒有說話。\n\n有些東西是這樣走的。真正重要的是你有沒有回頭。\n"


def self_test(rules) -> int:
    import tempfile
    fails = []
    for name, text, want_hard, want_warn in [
        ("good", GOOD, False, False),
        ("半形", BAD_HW, True, False),
        ("總結殼", BAD_SHELL, False, True),
    ]:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                         encoding="utf-8") as f:
            f.write(text)
            p = Path(f.name)
        r = analyse(p, rules)
        p.unlink()
        if bool(r["hard"]) != want_hard:
            fails.append(f"{name}: 硬性判定應為 {want_hard},實得 {bool(r['hard'])}")
        if want_warn and not r["warnings"]:
            fails.append(f"{name}: 應該要有警告,實得零——**紅燈不可達**")
    if fails:
        for f in fails:
            print(f"  ❌ {f}")
        return 1
    print("✅ self-test:半形硬性、總結殼警告、好樣本無事,三端皆可達")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="中文正字法與收尾")
    ap.add_argument("files", nargs="*", help="要檢查的稿件(.md)")
    ap.add_argument("--rules", default=str(DEFAULT_RULES))
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    rp = Path(args.rules)
    if not rp.is_file():
        print(f"ERROR: 找不到規則檔 {rp}", file=sys.stderr)
        return 2
    try:
        rules = json.loads(rp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: 規則檔不是合法 JSON — {e}", file=sys.stderr)
        return 2

    if args.self_test:
        return self_test(rules)
    if not args.files:
        print("ERROR: 沒有給檔案(或用 --self-test)", file=sys.stderr)
        return 2

    results, failed = [], False
    for f in args.files:
        p = Path(f)
        if not p.is_file():
            print(f"ERROR: 找不到檔案 {p}", file=sys.stderr)
            return 2
        r = analyse(p, rules)
        results.append(r)
        failed = failed or not r["ok"]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            report(r)
        print("\n" + ("✗ 有硬性違規,回去改。" if failed else "✓ 過。剩下的提醒自己判斷。"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
