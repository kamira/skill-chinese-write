#!/usr/bin/env python3
"""執行輔助:shell/agent 呼叫、簡報組裝、live handshake、退出碼訊息。"""
from __future__ import annotations
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def die(msg: str, code: int) -> int:
    print(f"{'HALT' if code == 3 else 'ERROR' if code == 1 else 'INVALID-PLAN'}: {msg}")
    return code


def run_shell(cmd: str, cwd: Path):
    # encoding 明示(CHG-20260803-01 T2):text=True 不帶 encoding 會用 locale 編碼,
    # 非 UTF-8 locale(如 Windows cp932)讀到 CJK 輸出會 UnicodeDecodeError。
    return subprocess.run(cmd, shell=True, cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def agent_call(tmpl: str, brief: str, cwd: Path):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(brief)
        brief_path = f.name
    return run_shell(tmpl.replace("{brief}", brief_path), cwd)


# ── 回修迴圈(CHG-20260803-07)────────────────────────────────────────────
# 回修那一輪必須看得到上一輪為什麼失敗,否則它只是再擲一次骰子。
# 回饋一律**原文擷取**:runner 是 no-LLM 狀態機,這條界線不為了回饋而破——
# 讓模型摘要上一輪會遺失決定性細節,還多一層「模型轉述模型」的失真。
# ratchet / flaky 自 CHG-20260803-08 起加入:兩道閘的失敗同樣要能回送給下一輪,
# 否則「測試被刪掉」與「重跑不一致」只會得到一句沒有下文的 halt。
FAILURE_SOURCES = ("test", "ratchet", "static", "flaky", "mutation", "review")
NOTE_LIMIT = 800
# 實際操作驗收時發現:Python 3.13+ 的彩色 traceback 會把 ANSI 逃脫序列一起送進回饋。
# 那是給終端機看的,不是給讀 brief 的人或模型看的——而且它會吃掉截斷上限的額度。
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def failure_note(source: str, payload: str, limit: int = NOTE_LIMIT) -> str:
    """把一次閘失敗擷取成帶來源標籤的段落。原文,不轉述(僅去除 ANSI 色碼)。"""
    if source not in FAILURE_SOURCES:
        raise ValueError(f"未知的失敗來源:{source!r}(可用:{', '.join(FAILURE_SOURCES)})")
    body = ANSI_RE.sub("", payload or "").strip()
    if not body:
        # 沒有輸出也是一種證據,但**不能**寫成任何像「通過」的字眼——
        # 回饋若誤導下一輪,比沒有回饋更糟。
        body = "(該閘失敗但未產生任何輸出)"
    tail = ""
    if len(body) > limit:
        body, tail = body[:limit], "\n…(已截斷,完整輸出見執行紀錄)"
    return f"[failed-gate: {source}]\n{body}{tail}"


def compose_extra(notes) -> str:
    """把上一輪的 failure notes 組成 brief 的附加段;第一輪(無 notes)為空字串。"""
    kept = [n for n in (notes or []) if n]
    if not kept:
        return ""
    return ("\n## 上一輪失敗原因(原文擷取,請逐項修正後再交)\n\n"
            + "\n\n".join(kept) + "\n")


def compose_review_extra(notes) -> str:
    """複審用的附加段:把上一輪的 findings 交給審查者逐項確認(scoped re-review)。"""
    kept = [n for n in (notes or []) if n]
    if not kept:
        return ""
    return ("\n## 本輪須確認的 findings(上一輪的失敗,請逐項回覆已解 / 未解)\n\n"
            + "\n\n".join(kept) + "\n")


def mutation_enabled(args) -> tuple[bool, str | None]:
    """變異閘是否執行。回 (是否執行, 留痕訊息 or None)。

    自 v1.10.0 起**預設開啟**:缺 `--test-cmd` 會 halt(存在性是強制的),
    而唯一檢驗「測試夠不夠強」的閘卻是選配的——這個排序反了。
    `--mutation` 保留為相容 no-op,`--no-mutation` 是明示且留痕的逃生口。
    """
    if getattr(args, "no_mutation", False):
        return False, ("⚠️ 變異閘已以 --no-mutation 明示關閉:本輪未驗測試強度,"
                       "須記入 ACC 的未涵蓋欄")
    return True, None


MAX_FIX_ROUNDS = 3


def next_round(round_idx: int, max_rounds: int) -> tuple[bool, str]:
    """這一輪失敗後還有沒有下一輪。回 (是否續作, 裁決 ∈ {'retry','halt'})。

    達上限一律 halt,不得靜默放行——build 迴圈的失敗代價是把壞碼往下游送(KN-004)。
    """
    if round_idx < max_rounds:
        return True, "retry"
    return False, "halt"


def agent_for_round(round_idx: int, max_rounds: int, agent_cmd: str,
                    escalate_cmd: str | None) -> tuple[str, str | None]:
    """這一輪要用哪個施工指令。回 (指令, 警語 or None)。

    最後一輪改用升階指令。未給升階指令時**沿用原指令而不是 halt**:
    硬性要求第二個模型會讓沒有多模型配置的人完全跑不動。但沿用必須說出來——
    同模型升階只換提示、不換盲點,那是折扣不是等價。
    """
    if round_idx < max_rounds:
        return agent_cmd, None
    if escalate_cmd:
        return escalate_cmd, None
    return agent_cmd, ("⚠️ 最後一輪未給 --escalate-cmd:沿用 --agent-cmd。"
                       "同模型升階=只換提示不換盲點,獨立性有折扣。")


def unresolved_report(entries) -> str:
    """達上限時的未解項清單。entries: [(輪次, 來源, 摘要)]。

    只印最後一行會讓人以為問題只有一個;debug 需要的正是
    「這幾輪各卡在哪、有沒有在收斂」。
    """
    # 同樣清掉 ANSI:這份是印給人看的,夾帶逃脫序列會讓輪次之間的界線讀不出來
    rows = [f"  · 第 {rnd} 輪 [{src}] {ANSI_RE.sub('', summary or '').strip()[:200]}"
            for rnd, src, summary in (entries or [])]
    if not rows:
        return "(無未解項紀錄)"
    return f"回修 {len(rows)} 輪仍未通過,各輪未解項:\n" + "\n".join(rows)


def build_brief(chg_text: str, task, mode: str, extra: str = "") -> str:
    gc = chg_text[chg_text.find("### Global Constraints"):]
    gc = gc[:gc.find("### Tasks")] if "### Tasks" in gc else gc[:1500]
    head = ("依 TDD(紅→綠→重構)完成以下 task;先寫失敗測試。" if mode == "build"
            else "唯讀審查以下 task 的 diff;輸出一行判定:[task-review] %s | spec: ... | quality: ... | 理由" % task["tid"])
    return f"{head}\n\n{gc}\n\n## Task\n{task['tid']}. {task['title']}\n{extra}\n"


# 交接文件是**人與機器共寫**的一份檔:機器寫進度,人寫交接判斷。
# 原本的實作整份覆寫,會把人寫的交接內容清掉——而那正是 handshake 協定
# 要求下一棒先讀的東西。改為標記包夾的區塊,機器只覆寫自己那一段。
HANDSHAKE_BEGIN = "<!-- autopilot:begin -->"
HANDSHAKE_END = "<!-- autopilot:end -->"


def handshake_block(existing: str, body: str) -> str:
    """把機器區塊寫進既有內容:有標記換內容,無標記則附加,既有內容一字不動。"""
    block = f"{HANDSHAKE_BEGIN}\n{body}\n{HANDSHAKE_END}"
    if HANDSHAKE_BEGIN in existing and HANDSHAKE_END in existing:
        pre = existing[:existing.index(HANDSHAKE_BEGIN)]
        post = existing[existing.index(HANDSHAKE_END) + len(HANDSHAKE_END):]
        return pre + block + post
    if existing.strip():
        # 無標記代表這是人手寫的交接文件。為了機器格式而擋住整條流程,
        # 代價方向錯了(KN-004)——最壞情況只是多一個區塊,不會遺失內容。
        return existing.rstrip("\n") + "\n\n" + block + "\n"
    return block + "\n"


def write_handshake(repo: Path, chg_id: str, doing: str, nxt: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    wl = Path(repo) / "docs" / "worklog"
    wl.mkdir(parents=True, exist_ok=True)
    target = wl / "handshake-autopilot.md"
    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    body = (f"branch/role/scope: autopilot / {chg_id}\ndoing: {doing}\nnext: {nxt}\n"
            f"last-updated: {ts} (UTC+0)")
    target.write_text(handshake_block(existing, body), encoding="utf-8")
