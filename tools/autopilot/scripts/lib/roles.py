#!/usr/bin/env python3
"""角色單元:plan / build / review / verify / accept。

每個角色可**單獨呼叫**,但都走同一 halt policy 與同一帳本——拆指令**不是治理繞道**:
前置條件缺失一律 halt(exit 3)。`run` 由這些單元組合而成(單一實作,不重複邏輯)。
"""
from __future__ import annotations
import shutil
from pathlib import Path

from . import plan as P
from . import policy as POL
from .exec_util import (MAX_FIX_ROUNDS, agent_call, agent_for_round, build_brief,
                        compose_extra, compose_review_extra, die, failure_note,
                        mutation_enabled, next_round, run_shell, unresolved_report,
                        write_handshake)
from . import ci_gate as CI
from . import profile as PRO
from . import quality as Q
from . import interaction as INT
from . import panel as PAN
from . import quality_judge as QJ
from .ratchet import flaky_gate, ratchet_gate
from .verify import escape_hatches, mutation_gate, platform_coverage, static_gate


class Ctx:
    """一次角色呼叫的共用脈絡(解析一次,重用)。"""

    def __init__(self, args):
        self.args = args
        self.chg_path = Path(args.chg)
        self.repo = Path(getattr(args, "repo", ".")).resolve()
        self.text = P.read_chg(self.chg_path)
        self.chg_id = P.chg_id_of(self.text, self.chg_path.stem)
        self.problems, self.tasks = P.parse_tasks(self.text)
        self.risk = P.risk_of(self.text)
        self.matrix = POL.load_policy(getattr(args, "policy", None))

    def reload(self):
        self.text = P.read_chg(self.chg_path)
        self.problems, self.tasks = P.parse_tasks(self.text)

    def action(self, stage: str) -> str:
        return POL.stage_action(self.matrix, self.risk, stage, self.text)

    @property
    def todo(self):
        return [t for t in self.tasks if not t["ticked"]]

    @property
    def done(self):
        return [t for t in self.tasks if t["ticked"]]


# ---------- 前置條件斷言(治理護欄;缺失=halt,不得繞道) ----------

def require_valid_plan(ctx) -> int | None:
    if ctx.problems:
        print("❌ plan-check 未通過:")
        for p in ctx.problems:
            print(f"  - {p}")
        return 2
    return None


def require_no_permanent_halt(ctx) -> int | None:
    perm = P.PERM_RE.findall(ctx.text)
    if perm:
        return die(f"永遠停點標記 {perm}:該動作必須由人執行/在場,autopilot 不代行", 3)
    return None


def require_confirm_gate(ctx) -> int | None:
    act = ctx.action("confirm_gate")
    if act != "auto" and not getattr(ctx.args, "confirmed", False):
        return die(f"確認閘({ctx.risk} 風險 → {act}):請人審閱 CHG 後以 --confirmed 重跑(或依 knowledge 預授權)", 3)
    return None


def require_all_built(ctx, who: str) -> int | None:
    if ctx.todo:
        ids = ", ".join(t["tid"] for t in ctx.todo)
        return die(f"{who} 前置條件不足:仍有未完成 task({ids})——先跑 build/review 打勾(拆指令非治理繞道)", 3)
    return None


def require_test_command(ctx) -> int | None:
    """agent 寫出來的程式碼不得在「一行測試都沒跑過」的狀態下被打勾(CHG-20260803-02 T1)。

    原本 `if a.test_cmd:` 讓沒給指令時整段跳過且無任何輸出——task 照樣打勾、照樣 commit,
    而 review 是唯讀看 diff、跑不到程式。這是本流程對 AI 產出程式碼最大的靜默漏洞。
    """
    a = ctx.args
    if getattr(a, "dry_run", False) or not getattr(a, "agent_cmd", None):
        return None                      # 沒有真的施工:dry-run,或人在迴圈模式(另有 brief 停點)
    if getattr(a, "test_cmd", None):
        return None
    if getattr(a, "allow_untested", False):
        print("⚠️ --allow-untested:本輪不執行任何測試——agent 寫出的程式碼將**未經執行**即打勾。"
              "僅適用純文件 task;請在 ACC 證據欄註明本輪未執行測試。")
        return None
    return die("無 --test-cmd:agent 寫出的程式碼會在一行測試都沒跑過的情況下被打勾並 commit。"
               "請給 --test-cmd;純文件變更請明示 --allow-untested(會留痕)", 3)


def require_escape_hatch_declared(ctx) -> int | None:
    """逃生口用了就要留痕;把門檻調到底線以下需 CHG 明文宣告(CHG-20260803-02 T13)。"""
    used, blocked = escape_hatches(ctx.args, ctx.text)
    if used:
        print("🔓 本輪使用的逃生口(須記入 ACC 證據欄):")
        for u in used:
            print(f"   · {u}")
        write_handshake(ctx.repo, ctx.chg_id, f"{ctx.chg_id} 使用逃生口:{'; '.join(used)}",
                        "收尾時須於 ACC 說明每個逃生口的理由")
    if blocked:
        return die(blocked, 3)
    return None


def require_operational_declared(ctx) -> int | None:
    if P.DOCS_ONLY_RE.search(ctx.text) and not P.AOP_RE.search(ctx.text):
        return None  # docs-only 合法豁免
    if not P.AOP_RE.search(ctx.text):
        return die("缺實際操作驗收:程式類變更不得只憑 task 級測試收尾——請在 CHG 補「### Acceptance operation」"
                   "(operate/observe/pass)或標記「Acceptance-operation: n/a (docs-only)」", 3)
    return None


# ---------- 角色 ----------

def require_bspec_declared(ctx) -> int | None:
    """程式類 CHG(Skill ≥ v1.5.0)必須宣告行為規格(CHG-20260803-02 T5)。

    使用者故事自 ai-sdlc v1.19 起是驗收條件的第一順位來源,但一直只是散文——
    沒有任何東西保證「故事」與「實際跑過的斷言」講的是同一件事。本節要求把故事
    對應到 .feature,讓驗收是對著故事跑,而不是對著散文人工判讀。
    """
    if not P.bspec_required(ctx.text):
        return None
    paths = P.bspec_paths(ctx.text)
    if not paths:
        return die("缺「### Behaviour spec」節:程式類變更(Skill ≥ ai-sdlc-autopilot v1.5.0)"
                   "須把 CHG 的使用者故事對應到可執行的 .feature——"
                   "格式:`### Behaviour spec` 下一行 `- feature: <路徑>`;"
                   "純文件變更請標「Acceptance-operation: n/a (docs-only)」", 2)
    # 路徑解析要同時試 repo 根目錄與 **CHG 所在目錄**(CHG-20260803-03 施工中發現)。
    # `plan` 角色沒有 `--repo`,ctx.repo 會退成 cwd——對不在 cwd 的 CHG 檢查檔案存在性
    # 必然誤判為「宣告了但不存在」。這個洞在 CHG-20260803-02 T5 就存在,
    # 只有在對別處的 CHG 跑 plan-check 時才現形。
    chg_dir = Path(ctx.chg_path).resolve().parent
    missing = [p for p in paths
               if not (ctx.repo / p).exists() and not (chg_dir / p).exists()]
    if missing:
        return die(f"行為規格宣告了但檔案不存在:{', '.join(missing)}"
                   f"(宣告一個不存在的規格,與沒有規格等價)", 2)
    return None


def require_interaction_declared(ctx) -> int | None:
    """會被重複使用的產物必須宣告互動驗證(CHG-20260803-03 T3)。

    預設強制、明示豁免——而**豁免必須帶理由**。空豁免與沒寫等價,
    但看起來像有交代,那是最糟的狀態:它讓漏寫變得不可見。
    """
    if not INT.required(ctx.text):
        return None
    exempted, reason = INT.exemption(ctx.text)
    if exempted and reason:
        print(f"🔓 互動驗證已豁免:{reason}(須記入 ACC)")
        return None
    if exempted and not reason:
        return die("`Interaction-spec: n/a` 沒有寫理由——空豁免與沒宣告等價。"
                   "請寫成 `Interaction-spec: n/a(<為何這份產出不會被重複使用>)`", 2)
    if not INT.parse_spec(ctx.text):
        kinds = INT.load_kinds(getattr(ctx.args, "interaction_kinds", None))
        return die("缺「### Interaction spec」節:程式類變更(Skill ≥ ai-sdlc-autopilot v1.6.0)"
                   "須宣告互動驗證——會被重複使用的產物,其使用面必須被真的用過一次。\n"
                   + INT.choices_message(kinds), 2)
    return None


def role_plan(ctx) -> int:
    bad = (require_valid_plan(ctx) or require_bspec_declared(ctx)
           or require_interaction_declared(ctx))
    if bad is not None:
        return bad
    if not P.AOP_RE.search(ctx.text) and not P.DOCS_ONLY_RE.search(ctx.text):
        print("  (提示:無「### Acceptance operation」——收尾將要求實際操作驗收;純文件變更請標"
              "「Acceptance-operation: n/a (docs-only)」。此為非阻斷提示。)")
    print(f"✅ plan-check 通過({len(ctx.tasks)} 個 task,格式完整)。")
    return 0


def role_build(ctx, single: bool = False) -> int:
    """施工(TDD)+ 逐 task review + 打勾 + commit。single=只做下一個 task。"""
    for check in (require_valid_plan, require_no_permanent_halt, require_confirm_gate,
                  require_test_command, require_escape_hatch_declared):
        bad = check(ctx)
        if bad is not None:
            return bad
    a = ctx.args
    if not ctx.todo:
        print("✅ 無未完成 task(全數已勾)——build 無事可做")
        return 0
    ran = 0
    for t in list(ctx.todo):
        if single and ran >= 1:
            break
        if getattr(a, "max_tasks", 0) and ran >= a.max_tasks:
            print(f"⏸ --max-tasks {a.max_tasks} 已達,暫停(續作點=checkbox)")
            write_handshake(ctx.repo, ctx.chg_id, f"{ctx.chg_id} 暫停於 {t['tid']} 之前", t["tid"])
            return 0
        write_handshake(ctx.repo, ctx.chg_id, f"{ctx.chg_id} task {t['tid']}/{len(ctx.tasks)}", "施工→測試→審查")
        if a.dry_run:
            print(f"[dry-run] {t['tid']} 施工=模擬 ok;測試=模擬綠;review=模擬 [task-review] {t['tid']} | spec: pass | quality: pass")
        elif a.agent_cmd:
            bad = _build_one(ctx, t)
            if bad is not None:
                return bad
        else:
            print(build_brief(ctx.text, t, "build"))
            return die(f"{t['tid']}:無 --agent-cmd(人在迴圈模式)——請依上方簡報人工完成後打勾重跑", 3)
        P.tick_task(ctx.chg_path, t["tid"])
        ctx.reload()
        if not (a.no_commit or a.dry_run):
            run_shell("git add -A", ctx.repo)
            run_shell(f'git commit -m "{ctx.chg_id}: {t["tid"]} {t["title"]}"', ctx.repo)
        else:
            print(f"[skip-commit] 等效訊息:{ctx.chg_id}: {t['tid']} {t['title']}")
        ran += 1
    # 平台涵蓋差集(CHG-20260803-02 T7):runner 沒有跨平台執行能力,
    # 誠實的做法是把「宣告要涵蓋 vs 本輪實際跑過」的差集講出來,而不是讓它消失。
    current, missing = platform_coverage(getattr(a, "test_platforms", None))
    if missing:
        print(f"⚠️ 平台涵蓋:本輪僅在 **{current}** 執行;宣告的 {', '.join(missing)} "
              f"**未涵蓋** — 請在 ACC 標注,或於 CI 補跑")
        write_handshake(ctx.repo, ctx.chg_id, f"{ctx.chg_id} 施工完成(平台 {current})",
                        f"未涵蓋平台:{', '.join(missing)} → 待 CI 或人工補跑")
    return 0


def _review_cmd(ctx) -> str:
    """審查用的指令:優先 --review-cmd,未給則回退 --agent-cmd。

    回退代表施工與審查跑在同一個模型上——同模型共享同一組訓練偏誤與盲點,某些錯會系統性地
    一起看不到(見 ai-sdlc independent-acceptance / agent-hierarchy 派工模型選用)。故回退時
    **明示限制**、不靜默,讓人知道該輪審查的獨立性有折扣。每次執行只印一次。
    """
    rc = getattr(ctx.args, "review_cmd", None)
    if rc:
        return rc
    if not getattr(ctx, "_review_fallback_noted", False):
        print("⚠️ 未給 --review-cmd:審查回退為 --agent-cmd,施工與審查為**同模型**"
              "(共享盲點;獨立性有折扣)。要跨模型審查請給 --review-cmd。")
        ctx._review_fallback_noted = True
    return ctx.args.agent_cmd


def _seat_cmd(ctx, seat: str) -> str:
    """這一席用哪個指令。`--seat-cmd spec=<cmd>` 可逐席指定不同模型。

    未逐席指定時全席沿用同一個指令,並**明講**——review-panel 要求同模型面板
    註明限制,而三席同模型的「多視角」是幻覺:它們共享同一組盲點。
    """
    for item in (getattr(ctx.args, "seat_cmd", None) or []):
        name, _, cmd = str(item).partition("=")
        if name.strip() == seat and cmd.strip():
            return cmd.strip()
    if not getattr(ctx, "_panel_same_model_noted", False):
        print("⚠️ 未以 --seat-cmd 逐席指定指令:全席沿用同一個審查指令。"
              "同模型面板共享同一組盲點,「多視角」在這種配置下是幻覺——"
              "判定行的模型欄仍會留下紀錄供稽核。")
        ctx._panel_same_model_noted = True
    return _review_cmd(ctx)


def _review_panel(ctx, t, extra: str = "") -> tuple[bool, str]:
    """跑一次審查:低風險單席(快速路徑),中/高風險開面板。

    裁決算術在這裡(no-LLM)完成,不交給模型彙整——彙整者的盲點會蓋過所有座位。
    """
    seats, seat_note = PAN.seats_for(ctx.risk, getattr(ctx.args, "review_panel", None))
    if seat_note:
        print(seat_note)
    threshold = int(getattr(ctx.args, "confidence_threshold", None) or PAN.DEFAULT_THRESHOLD)

    if len(seats) <= 1:
        # 快速路徑:維持既有單一審查者的簡報與行為,升級不擾動低風險流水線
        rv = agent_call(_review_cmd(ctx), build_brief(ctx.text, t, "review", extra), ctx.repo)
        v = PAN.parse_verdict(rv.stdout or "")
        if not v:
            return False, f"審查無判定行:{(rv.stdout or '').strip()[:200] or '(無輸出)'}"
        return PAN.adjudicate([v], threshold)

    verdicts = []
    for seat in seats:
        brief = PAN.seat_brief(ctx.text, t, seat) + extra
        rv = agent_call(_seat_cmd(ctx, seat), brief, ctx.repo)
        v = PAN.parse_verdict(rv.stdout or "")
        if v is None:
            # 沒有判定行的席次不算棄權,算「無法判定」——沒有輸出不算通過
            v = {"target": t["tid"], "seat": seat, "model": None,
                 "spec": "cannot-verify", "quality": "pass", "confidence": None,
                 "line": f"[task-review] {t['tid']} | {seat} | (無判定行)"}
        else:
            v["seat"] = v.get("seat") or seat
        verdicts.append(v)

    ok, msg = PAN.adjudicate(verdicts, threshold)
    if not ok or ctx.risk != "high":
        return ok, msg

    # 高風險才跑第二階段:先獨立(防定錨),再交叉讀(讓分歧無法被靜默吞掉)
    crosses = []
    for seat in seats:
        rv = agent_call(_seat_cmd(ctx, seat), PAN.cross_brief(verdicts, seat), ctx.repo)
        crosses += PAN.parse_cross(rv.stdout or "")
    ok2, msg2 = PAN.adjudicate_cross(crosses)
    return ok2, f"{msg}\n{msg2}"


def _build_one(ctx, t) -> int | None:
    """單 task:施工→測試→靜態→變異→唯讀 review;失敗**帶回饋**重試,最後一輪升階。

    CHG-20260803-07:原本的「一次回修機會」兩輪都用同一份 brief,沒有帶上一輪
    失敗的原因——那不是回修,是再擲一次骰子。現在每一輪都把上一輪的失敗**原文**
    帶進 brief,複審也拿到 findings 清單逐項確認。
    """
    a = ctx.args
    max_rounds = max(1, int(getattr(a, "max_fix_rounds", None) or MAX_FIX_ROUNDS))
    notes: list[str] = []            # 上一輪的失敗擷取,回送給下一輪
    unresolved: list[tuple] = []     # (輪次, 來源, 摘要):達上限時逐項列出

    for rnd in range(1, max_rounds + 1):
        cmd, warn = agent_for_round(rnd, max_rounds, a.agent_cmd,
                                    getattr(a, "escalate_cmd", None))
        if warn and not getattr(ctx, "_escalate_noted", False):
            print(warn)
            ctx._escalate_noted = True

        r = agent_call(cmd, build_brief(ctx.text, t, "build", compose_extra(notes)), ctx.repo)
        if r.returncode != 0:
            return die(f"{t['tid']} agent 施工失敗:{r.stderr.strip()[:200]}", 1)

        failed: tuple[str, str] | None = None
        if a.test_cmd:
            tr = run_shell(a.test_cmd, ctx.repo)
            if tr.returncode != 0:
                failed = ("test", f"{tr.stdout or ''}\n{tr.stderr or ''}")
            # 閘序沿用「先擋便宜的」(CHG-20260803-06):
            #   棘輪 = 純 AST + git,最便宜 → 靜態 = AST,便宜
            #   → flaky = 重跑測試,昂貴 → 變異 = 最昂貴
            if failed is None:
                # 測試棘輪(CHG-20260803-08):單元閘只問「測試指令有沒有回 0」,
                # 而刪掉那支紅的測試,它就回 0 了。這道閘問的是「測試還在不在」。
                ok, msg, _ = ratchet_gate(ctx.repo, getattr(a, "allow_test_reduction", False))
                print(f"{t['tid']} {msg}")
                if not ok:
                    failed = ("ratchet", msg)
            if failed is None:
                # 內建靜態/安全檢查(CHG-20260803-06):對**本 task 變更的檔案**跑。
                # 排在變異之前——它快得多,而且抓的是變異照不到的東西
                # (未使用 import、eval、注入形態、寫死的金鑰)。
                ok, msg = static_gate(ctx.repo, getattr(a, "static_allowlist", None))
                print(f"{t['tid']} {msg}")
                if not ok:
                    failed = ("static", msg)
            if failed is None:
                # 不穩定測試偵測(CHG-20260803-08):在**同一份程式碼**上重跑。
                # 跑一次剛好綠不算通過——不穩定的綠燈與恆真的綠燈是同一個問題(KN-001)。
                ok, msg, _ = flaky_gate(ctx.repo, a.test_cmd, getattr(a, "flaky_runs", None))
                print(f"{t['tid']} {msg}")
                if not ok:
                    failed = ("flaky", msg)
            if failed is None:
                # 變異閘(CHG-20260803-02 T3):單元綠之後、review 之前。
                # 擺在這個位置的理由——review 是唯讀看 diff,看不出「測試寫得太鬆」;
                # 而測試太鬆正是同一個模型既寫程式又寫測試時的系統性失效模式。
                run_mut, mut_note = mutation_enabled(a)
                if mut_note and not getattr(ctx, "_mutation_noted", False):
                    print(mut_note)
                    ctx._mutation_noted = True
                if run_mut:
                    ok, msg, _ = mutation_gate(ctx.repo, a.test_cmd, a.min_kill_rate,
                                               getattr(a, "mutation_max", 40))
                    print(f"{t['tid']} {msg}")
                    if not ok:
                        failed = ("mutation", msg)

        if failed is None:
            # 審查面板(CHG-20260803-09):席次由風險分級決定,低風險維持單席快速路徑。
            # scoped 複審:上一輪的 findings 一併交給審查者逐項確認,
            # 否則複審只看得到「現在的 diff」,看不到「原本錯在哪、修掉了沒」。
            ok, msg = _review_panel(ctx, t, compose_review_extra(notes))
            print(f"{t['tid']} {msg}")
            if ok:
                return None
            failed = ("review", msg)

        src, payload = failed
        notes = [failure_note(src, payload)]   # 只帶最近一輪,避免 brief 無限長大
        unresolved.append((rnd, src, payload))
        cont, _verdict = next_round(rnd, max_rounds)
        if not cont:
            return die(f"{t['tid']} 回修 {max_rounds} 輪未通過。\n"
                       f"{unresolved_report(unresolved)}", 3)
    return die(f"{t['tid']} 未通過施工/審查迴圈", 1)


def role_review(ctx) -> int:
    """整支 branch review(逐 task review 內含於 build)。"""
    bad = require_valid_plan(ctx) or require_all_built(ctx, "整支 review")
    if bad is not None:
        return bad
    if ctx.args.dry_run:
        print("[stage] 整支 review:[dry-run] 模擬 [task-review] branch | spec: pass | quality: pass")
        return 0
    # 這一段原本只印一行字就 return 0——停點矩陣列了一整欄的關卡,程式上是 no-op。
    # 現在真的呼叫審查指令並解析判定行(CHG-20260803-02 T6)。
    cmd = getattr(ctx.args, "review_cmd", None) or getattr(ctx.args, "agent_cmd", None)
    if not cmd:
        return die("整支 review 需要 --review-cmd(或 --agent-cmd):此關卡不再是 no-op,"
                   "必須真的有人/有模型看過整條 branch diff", 3)
    brief = ("唯讀審查整條 branch 的 diff(不是單一 task)。逐項對照 CHG 的使用者故事與全域約束。\n"
             "最後輸出一行判定:[task-review] branch | spec: pass|fail|cannot-verify | "
             "quality: pass|fail | 理由\n\n" + ctx.text[:4000])
    print("[stage] 整支 review:對整條 branch diff 實際審查中")
    rv = agent_call(cmd, brief, ctx.repo)
    m = P.VERDICT_RE.search(rv.stdout or "")
    if not m:
        return die("整支 review 無判定行——無輸出不得視為通過(綠燈必須是掙來的)。"
                   f"審查指令輸出:{(rv.stdout or rv.stderr or '').strip()[:200]}", 3)
    if m.group(1).lower() == "fail" or m.group(2).lower() != "pass":
        return die(f"整支 review 未通過:{m.group(0)}", 3)
    print(f"整支 review 判定:{m.group(0)}(請入 ACC 證據欄)")
    return 0


def role_verify(ctx) -> int:
    """實際操作驗收:把整個變更真的跑一次。"""
    bad = (require_valid_plan(ctx) or require_all_built(ctx, "實際操作驗收")
           or require_operational_declared(ctx))
    if bad is not None:
        return bad
    a = ctx.args
    # 委派型驗證(CHG-20260803-06):型別 / 覆蓋率 / SAST / 相依漏洞。
    if Q.required(ctx.text):
        qexempt, qreason = Q.exemption(ctx.text)
        if qexempt and qreason:
            print(f"[stage] 委派驗證:已豁免({qreason})——須記入 ACC")
        elif qexempt:
            return die("`Quality-checks: n/a` 沒有寫理由——空豁免與沒宣告等價", 3)
        else:
            qkinds = Q.load_kinds(getattr(a, "quality_kinds", None))
            qbase, qberr = QJ.load_baseline(
                getattr(a, "quality_baseline", None) or QJ.DEFAULT_BASELINE)
            if qberr:
                return die(f"委派驗證的基線無法使用:{qberr}", 3)
            qstatus, qmsg = Q.run_gate(ctx.repo, ctx.text, qkinds,
                                       getattr(a, "trust_chg_commands", False), qbase)
            if qstatus == "ok":
                print(f"[stage] {qmsg}")
            elif qstatus == "halt":
                return die(qmsg, 3)
            elif ctx.risk == "low":
                print(f"⚠️ {qmsg}(低風險 → 放行,須記入 ACC 的未涵蓋欄)")
            else:
                return die(qmsg + f"\n  {ctx.risk} 風險不接受「工具不存在」作為放行理由。", 3)

    op_act = ctx.action("operational_verify")
    if P.DOCS_ONLY_RE.search(ctx.text) and not P.AOP_RE.search(ctx.text):
        print("[stage] 實際操作驗收:docs-only 宣告,略過")
        return 0
    # Gherkin 閘(CHG-20260803-02 T5):CHG 宣告了行為規格就必須真的跑過。
    # 缺 behave 時 **halt 並指出安裝方式**,不靜默略過——「沒跑」與「通過」若都是綠,這層等於不存在。
    for spec in P.bspec_paths(ctx.text):
        gcmd = getattr(a, "gherkin_cmd", None) or "behave --strict"
        gr = run_shell(f"{gcmd} {spec}", ctx.repo)
        if gr.returncode != 0:
            tail = (gr.stdout or gr.stderr or "").strip().splitlines()[-6:]
            hint = ("\n  (找不到 behave? pip install behave)"
                    if "not recognized" in (gr.stderr or "") or gr.returncode in (1, 9009, 127)
                    and not tail else "")
            return die(f"行為規格未通過:{spec}\n  " + "\n  ".join(tail) + hint, 3)
        print(f"[stage] 行為規格通過:{spec}")

    # 非功能性驗證閘(CHG-20260804-02):效能 / 負載 / 併發 / 資源 / 可重現 /
    # 授權 / API 合約 / 視覺回歸 / 屬性測試——**依專案型態調用**。
    # 對一個 CLI/library repo 課負載測試的稅,會讓人把整套關掉;
    # 所以這裡有第三種狀態「不適用」,而它與「未涵蓋」和「通過」都不同。
    if PRO.required(ctx.text):
        nprofiles, nperr = PRO.load_profile(ctx.repo)
        if nperr:
            return die(f"專案型態宣告無法使用:{nperr}", 3)
        nkinds = PRO.load_kinds(getattr(a, "nonfunctional_kinds", None))
        nbase, nberr = QJ.load_baseline(
            getattr(a, "quality_baseline", None) or QJ.DEFAULT_BASELINE)
        if nberr:
            return die(f"委派驗證的基線無法使用:{nberr}", 3)
        nstatus, nmsg = PRO.run_gate(ctx.repo, ctx.text, nkinds, nprofiles,
                                     getattr(a, "trust_chg_commands", False), nbase)
        if nstatus == "ok":
            print(f"[stage] {nmsg}")
        elif nstatus == "not-applicable":
            # 不適用是永久結論,不是通過——訊息刻意不含肯定式的通過措辭
            print(f"[stage] {nmsg}")
        elif nstatus == "halt":
            return die(nmsg, 3)
        elif ctx.risk == "low":
            print(f"⚠️ {nmsg}(低風險 → 放行,須記入 ACC 的未涵蓋欄)")
        else:
            return die(f"非功能性驗證未涵蓋,而本變更為 {ctx.risk} 風險 → 停下交人。\n{nmsg}", 3)

    # 互動驗證閘(CHG-20260803-03 T4-T6):行為規格之後、操作驗收之前。
    # 放在 verify 而非 build 的理由——互動驗證要整個系統跑起來,
    # 逐 task 起一次瀏覽器既慢又沒有意義。
    if INT.required(ctx.text):
        exempted, reason = INT.exemption(ctx.text)
        if exempted and reason:
            print(f"[stage] 互動驗證:已豁免({reason})——須記入 ACC")
        else:
            kinds = INT.load_kinds(getattr(a, "interaction_kinds", None))
            status, msg = INT.run_gate(ctx.repo, ctx.text, kinds,
                                       getattr(a, "interaction_cmd", None),
                                       getattr(a, "trust_chg_commands", False))
            if status == "ok":
                print(f"[stage] {msg}")
            elif status == "halt":
                return die(msg, 3)
            else:
                # 驅動不存在:依風險分級處置(使用者裁示 Q4c)。
                # 環境限制是真的(CI 無頭、伺服器無 GUI),硬擋會讓 skill 在那些環境不可用;
                # 但「會被重複使用」本身意味著錯誤被放大 —— 故用既有風險分級分派,不發明新判準。
                if ctx.risk == "low":
                    print(f"⚠️ 互動驗證**未涵蓋**(低風險 → 放行,須記入 ACC 的未涵蓋欄):\n{msg}")
                    write_handshake(ctx.repo, ctx.chg_id, f"{ctx.chg_id} 互動驗證未涵蓋",
                                    "收尾時於 ACC 註明未涵蓋原因與補驗計畫")
                else:
                    return die(f"互動驗證無法執行,而本變更為 {ctx.risk} 風險 → 停下交人。\n{msg}\n"
                               f"  低風險才允許以「未涵蓋」放行;會被重複使用的中/高風險產出不行。", 3)
    if a.dry_run:
        print(f"[dry-run] 實際操作驗收=模擬 operate/observe/pass 通過(op_act={op_act})")
        return 0
    if op_act == "auto" and getattr(a, "verify_cmd", None):
        vr = run_shell(a.verify_cmd, ctx.repo)
        if vr.returncode != 0:
            return die(f"實際操作驗收失敗(--verify-cmd 非零):{vr.stderr.strip()[:200] or vr.stdout.strip()[:200]}", 3)
        print(f"[stage] 實際操作驗收:--verify-cmd 通過\n{vr.stdout.strip()[:300]}")
        return 0
    m = P.AOP_RE.search(ctx.text)
    if m is not None:
        # 不變式:走到這裡代表 require_operational_declared 已通過,AOP 節必然存在。
        # 但那條不變式只寫在別的函式裡——把它在這裡表達出來,否則型別上仍是 None 可達,
        # 而「不可達」與「忘了處理」在程式碼上長得一模一樣。
        print(ctx.text[m.start():m.start() + 600])
    reason = "高風險:操作簽核須由人執行" if op_act == "halt" else "無 --verify-cmd(人在迴圈)"
    return die(f"實際操作驗收({reason}):請依上方 operate/observe/pass 實際操作、記錄證據入 ACC,再續 merge", 3)


def role_accept(ctx) -> int:
    """驗收 + PR/merge 閘。前置:全 task 完成 + 操作驗收已過(--verified 或本輪 verify 成功)。"""
    bad = require_valid_plan(ctx) or require_all_built(ctx, "驗收")
    if bad is not None:
        return bad
    a = ctx.args
    if not (getattr(a, "verified", False) or a.dry_run):
        return die("驗收前置條件不足:未見操作驗收通過——先跑 `verify`(或以 --verified 聲明已人工完成並記錄證據入 ACC)。"
                   "拆指令非治理繞道。", 3)
    act = ctx.action("acceptance")
    if act == "halt_independent":
        return die("驗收(高風險):需獨立驗收者(≠實作者)產 ACC——autopilot 停,交人/獨立 agent", 3)
    print("[stage] 驗收:依 acceptance-verification 產 ACC(task 判定行=證據欄)")
    act = ctx.action("merge")
    if act != "auto":
        return die(f"merge({ctx.risk} 風險 → {act}):PR 已備,合併由人執行", 3)
    # CI 閘(CHG-20260803-04):合併前 CI 必須**全數完成且為綠**。
    # 實際踩過:windows job 還 pending 時就按了合併——其他三項已打勾,看起來就像好了。
    # 這裡 fail-closed(與哨兵的 fail-open 相反):合併難以回收,查不到狀態即不准合併。
    if not a.dry_run:
        ok, msg = CI.check(ctx.repo, getattr(a, "pr", None),
                           getattr(a, "ci_cmd", None), getattr(a, "allow_no_ci", False))
        print(f"[stage] {msg}" if ok else "")
        if not ok:
            return die(msg, 3)
        if getattr(a, "allow_no_ci", False):
            write_handshake(ctx.repo, ctx.chg_id, f"{ctx.chg_id} 以 --allow-no-ci 合併",
                            "收尾時於 ACC 說明為何此專案無 CI")
    if a.dry_run:
        print("[dry-run] PR+merge=模擬完成")
    elif shutil.which("gh"):
        print("[stage] PR/merge:gh 可用且 CI 全綠——可執行 gh pr merge(帶 CHG 編號)")
    else:
        return die("無 gh CLI:請人工開 PR 並 merge(commit 已帶 CHG 編號)", 3)
    write_handshake(ctx.repo, ctx.chg_id, f"{ctx.chg_id} 全 task 完成", "收尾:ACC/Commit-PR 回填/重複性檢查/knowledge")
    print(f"✅ {ctx.chg_id}:{len(ctx.tasks)} task 全數完成;收尾提醒=CHG 狀態+Commit/PR+重複性檢查欄+knowledge。")
    return 0


def role_run(ctx) -> int:
    """組合:build(全 task)→ 整支 review → 操作驗收 → 驗收/PR/merge。"""
    for step in (role_build, role_review, role_verify):
        rc = step(ctx)
        if rc != 0:
            return rc
        ctx.reload()
    ctx.args.verified = True  # 本輪 verify 已通過(組合流程內部授權,非繞道)
    return role_accept(ctx)


def role_status(ctx) -> int:
    print(f"CHG:{ctx.chg_id} | 風險:{ctx.risk}")
    nxt = ctx.todo[0]["tid"] + ". " + ctx.todo[0]["title"] if ctx.todo else "(無——進入收尾)"
    print(f"已完成 {len(ctx.done)}/{len(ctx.tasks)};下一個:{nxt}")
    return 0
