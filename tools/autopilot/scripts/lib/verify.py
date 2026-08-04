#!/usr/bin/env python3
"""施工階段針對 **agent 產出程式碼** 的驗證閘(CHG-20260803-02)。

`--test-cmd` 全綠只證明「agent 寫的測試沒抓到 agent 寫的錯」——同一個模型寫程式又寫測試,
兩邊共享同一組盲點(見 ai-sdlc `independent-acceptance`)。變異閘把問句倒過來:
**種一個錯進去,那些測試會不會紅?** 殺不掉的變異體就是這個 task 的驗證缺口。

本模組維持 no-LLM:只跑 git、跑 mutation_harness、算數字、回報。
"""
from __future__ import annotations
import json
import platform
import subprocess
import sys
from pathlib import Path

from .exec_util import run_shell

HARNESS = Path(__file__).resolve().parent.parent / "mutation_harness.py"
# 目前只有 Python 有 AST 變異算子。其他語言不是「通過」,是「未涵蓋」——兩者必須可區分。
MUTATABLE_SUFFIXES = (".py",)


def _is_test_file(p: Path) -> bool:
    """測試檔本身不得作為變異對象。

    變異測試檔會讓 kill rate **虛高**:改壞一條斷言 → 測試紅 → 記為「殺死」,
    但那證明的是「測試檔會影響測試結果」這種同義反覆,不是「程式被保護著」。
    """
    n = p.name
    return (n.startswith("test_") or n.endswith("_test.py")
            or "tests" in p.parts or "test" in p.parts)


def changed_files(repo: Path) -> list[Path]:
    """本 task 尚未提交的變更檔(已追蹤的改動 + 未追蹤的新檔)。

    逐 task commit 的前提下,未提交的 diff 就是這個 task 的產出——變異的歸屬因此正確:
    這個 task 寫的碼,由這個 task 的測試負責。
    """
    out = []
    for args in ("diff --name-only", "diff --name-only --cached",
                 "ls-files --others --exclude-standard"):
        r = run_shell(f"git {args}", repo)
        if r.returncode == 0:
            out += [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
    seen, files = set(), []
    for rel in out:
        if rel in seen:
            continue
        seen.add(rel)
        p = Path(repo) / rel
        if p.is_file():
            files.append(p)
    return files


def mutation_gate(repo: Path, test_cmd: str, min_kill_rate: float,
                  mutation_max: int = 40) -> tuple[bool, str, dict]:
    """對本 task 變更的可變異檔跑變異測試。

    回 (通過, 人讀訊息, 明細)。**「未涵蓋」一律回通過=True 但訊息明講**——
    擋住非 Python 專案不是本閘的職責,但讓人以為驗過了才是真正的危害(KN-001)。
    """
    files = changed_files(repo)
    targets = [f for f in files if f.suffix in MUTATABLE_SUFFIXES and not _is_test_file(f)]
    # 先建區域變數再放進 detail:直接從異質 dict 取值會被推成 object,
    # 於是 join 與 append 都判不過——而那不是型別註記的問題,是取值方式的問題
    per_file: list[dict] = []
    skipped = sorted({f.suffix for f in files
                      if f.suffix not in MUTATABLE_SUFFIXES and f.suffix})
    detail = {"changed": len(files), "mutatable": len(targets), "per_file": per_file,
              "skipped_languages": skipped}

    if not files:
        return True, "變異閘:本 task 無檔案變更 → 未涵蓋(無可變異對象)", detail
    if not targets:
        langs = ", ".join(skipped) or "(無副檔名)"
        return True, (f"變異閘:**未涵蓋** — 本 task 變更的是 {langs},"
                      f"變異引擎目前僅支援 {', '.join(MUTATABLE_SUFFIXES)}。"
                      f"這不是『通過』,請在 ACC 的未涵蓋欄註明"), detail

    worst = 100.0
    lines = []
    for tgt in targets:
        cmd = [sys.executable, str(HARNESS), "--target", str(tgt),
               "--test", test_cmd, "--cwd", str(repo), "--json",
               "--min-kill-rate", str(min_kill_rate)]
        if mutation_max:
            cmd += ["--max-mutants", str(mutation_max)]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        try:
            res = json.loads(r.stdout)
        except json.JSONDecodeError:
            # 引擎中止(多半是基線護欄:未變異版本就跑不過測試)——這是**真問題**,不可放行
            msg = (r.stdout or r.stderr or "").strip().splitlines()
            per_file.append({"file": str(tgt), "error": msg[:3]})
            return False, (f"變異閘:{tgt.name} 無法評估 — {' / '.join(msg[:2])}\n"
                           f"  (基線護欄失敗通常代表測試指令本身在此 repo 跑不起來)"), detail
        per_file.append(res)
        worst = min(worst, res["kill_rate"])
        tag = "✓" if res["kill_rate"] >= min_kill_rate else "✗"
        lines.append(f"  {tag} {tgt.name}: kill rate {res['kill_rate']}% "
                     f"({res['killed']}/{res['mutants_run']})"
                     + (f",取樣丟棄 {res['dropped_by_cap']}" if res.get("dropped_by_cap") else ""))
        for s in res.get("survivors", []):
            lines.append(f"      [存活] {s}")

    detail["worst_kill_rate"] = worst
    body = "\n".join(lines)
    if worst < min_kill_rate:
        return False, (f"變異閘未達門檻({worst}% < {min_kill_rate}%)——"
                       f"agent 寫的測試殺不掉下列變異體,代表那些行改錯了也不會被發現:\n{body}"), detail
    return True, f"變異閘通過(最低 kill rate {worst}%):\n{body}", detail


# kill rate 的底線(CHG-20260803-02 T13)。低於此值等同關閉變異閘——
# 把門檻調到 0 再宣稱「變異測試通過」是最省事的偽造方式,故需 CHG 明文宣告。
KILL_RATE_FLOOR = 60.0
ESCAPE_DECLARE_RE = "Escape-hatch:"


def escape_hatches(args, chg_text: str) -> tuple[list[str], str | None]:
    """盤點本輪用了哪些逃生口;回 (使用清單, 阻擋理由或 None)。

    逃生口本身是必要的(純文件 task 不該被逼著寫測試),問題在於**用了沒人知道**。
    每一個都寫進 handshake 與收尾提醒;其中「把門檻調到底線以下」影響最大——
    那等於在保留「跑過變異測試」這個說法的同時把它關掉——故要求 CHG 明文宣告。
    """
    used = []
    if getattr(args, "allow_untested", False):
        used.append("--allow-untested(本輪未執行任何測試)")
    rate = getattr(args, "min_kill_rate", None)
    if getattr(args, "mutation", False) and rate is not None and rate < KILL_RATE_FLOOR:
        used.append(f"--min-kill-rate {rate}(低於底線 {KILL_RATE_FLOOR})")
        if ESCAPE_DECLARE_RE not in chg_text:
            return used, (f"kill rate 門檻 {rate} 低於底線 {KILL_RATE_FLOOR},"
                          f"等同關閉變異閘卻保留『已跑變異測試』的說法。"
                          f"請在 CHG 加一行 `Escape-hatch:` 說明為何必須調低")
    if getattr(args, "no_commit", False):
        used.append("--no-commit(變更未錨定到 commit)")
    return used, None


def platform_coverage(declared: str | None) -> tuple[str, list[str]]:
    """回 (本輪實際平台, 宣告了但本輪未涵蓋的平台)。

    runner 沒有跨平台執行能力,誠實的做法是**記錄差集**而不是假裝跑過。
    真正的跨平台由使用者的 CI 提供;這裡只確保差集不會消失在無人聞問處。
    """
    current = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}.get(
        platform.system(), platform.system().lower())
    if not declared:
        return current, []
    want = [p.strip().lower() for p in declared.split(",") if p.strip()]
    return current, [p for p in want if p != current]


# lib/verify.py → parents: [0]=lib [1]=scripts [2]=ai-sdlc-autopilot
# 治理層與執行層自 CHG-20260804-08 起同在一支 skill,static_check 就在隔壁,
# 不必再從 repo 根目錄繞回來——那個繞法也正是搬家時會斷掉的地方。
STATIC_CHECK = Path(__file__).resolve().parents[1] / "static_check.py"


def static_gate(repo: Path, allowlist: str | None = None) -> tuple[bool, str]:
    """對本 task 變更的檔案跑內建靜態/安全檢查(CHG-20260803-06)。

    與變異閘的差別:變異問「測試夠不夠強」,這裡問「程式本身有沒有已知形態的問題」。
    後者不需要執行程式,也不需要測試存在——所以它對**任何**變更都適用,
    包含那些「還沒寫測試」的 task。
    """
    files = [str(f.relative_to(repo)) for f in changed_files(repo)
             if f.suffix in (".py", ".sh", ".yml", ".yaml", ".json", ".md", ".toml")]
    if not files:
        return True, "靜態/安全檢查:本 task 無可檢查的變更檔"
    if not STATIC_CHECK.is_file():
        # 檢查器不見了不能當成通過——那正是它要防的失效形態
        return False, f"找不到靜態檢查器({STATIC_CHECK});缺少檢查器不等於沒有問題"
    cmd = [sys.executable, str(STATIC_CHECK), "--repo", str(repo), "--paths", *files]
    if allowlist:
        cmd += ["--allowlist", allowlist]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    body = (r.stdout or "") + (r.stderr or "")
    if r.returncode == 0:
        return True, f"靜態/安全檢查通過({len(files)} 個變更檔)"
    return False, "靜態/安全檢查未通過:\n" + body.strip()[:1500]
