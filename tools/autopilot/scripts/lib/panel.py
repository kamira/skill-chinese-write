#!/usr/bin/env python3
"""程式碼審查面板:座位、否決權、信心降級(CHG-20260803-09)。

**本模組不發明新機制。** 治理層的 `ai-sdlc/references/review-panel.md` 已經定義了
座位制(一席一領域)、判定行文法、硬規則否決權、風險分級調用與無 spawn 降級;
這裡把那套機制擴到一個新階段——程式碼 diff 審查。座位不同(領域不同),機制相同。

其中最要緊的一條:review-panel 明寫**「分歧是調和或升級,絕不平均」**。
所以信心分數在這裡**只用來降級**(把沒把握的票變成「無法判定」),
永遠不參與任何平均或加權——一個有把握的反對票,不該被兩個沒去看那個角落的贊成票稀釋。

裁決算術一律在這裡(no-LLM)完成,不交給模型彙整:彙整者的盲點會蓋過所有座位,
而且那又是一次「模型轉述模型」的失真。
"""
from __future__ import annotations
import json
import re
from pathlib import Path

SEATS_TABLE = Path(__file__).resolve().parent.parent.parent / "assets" / "review_seats.json"

HEAD_RE = re.compile(r"\[task-review\]\s*(T\d+|branch)", re.IGNORECASE)
CONF_RE = re.compile(r"^conf(?:idence)?\s*[::]\s*(\d{1,3})\s*$", re.IGNORECASE)
SPEC_VALUES = ("pass", "fail", "cannot-verify")
QUALITY_VALUES = ("pass", "fail")

DEFAULT_THRESHOLD = 80          # 沿用官方 code-review 插件已驗證過的門檻,不憑空發明數字
# 風險分級決定席次:面板是為風險加的深度,不是對所有事情課的稅(review-panel 原話)。
SEATS_BY_RISK = {"low": 1, "medium": 3, "high": 3}


def parse_verdict(line):
    """解析一行判定。回 dict 或 None(壞輸入不崩潰)。

    新舊格式並存,`seat` / `model` / `confidence` 皆選填——舊格式的流水線
    不得因為升級而全炸(同 `--mutation` 保留為 no-op 的相容處置)。

    位置欄(座位、模型)只從 **`spec:` 之前**取,否則結尾的理由欄會被誤讀成座位。
    """
    if not line or not isinstance(line, str):
        return None
    m = HEAD_RE.search(line)
    if not m:
        return None
    start = line.rfind("\n", 0, m.start()) + 1
    end = line.find("\n", m.start())
    row = line[start:end if end != -1 else len(line)]
    parts = [p.strip() for p in row.split("|")]

    idx = next((i for i, p in enumerate(parts) if p.lower().startswith("spec")), None)
    if idx is None:
        return None
    fields = {}
    for p in parts[idx:]:
        low = p.lower()
        if low.startswith("spec"):
            fields["spec"] = p.split(":", 1)[-1].strip().lower()
        elif low.startswith("quality"):
            fields["quality"] = p.split(":", 1)[-1].strip().lower()
        else:
            cm = CONF_RE.match(p)
            if cm:
                fields["confidence"] = max(0, min(100, int(cm.group(1))))
    if fields.get("spec") not in SPEC_VALUES or fields.get("quality") not in QUALITY_VALUES:
        return None

    positional = [p for p in parts[1:idx] if p]
    return {"target": m.group(1),
            "seat": positional[0] if positional else None,
            "model": positional[1] if len(positional) > 1 else None,
            "spec": fields["spec"],
            "quality": fields["quality"],
            "confidence": fields.get("confidence"),
            "line": row.strip()}


def downgrade(verdict: dict, threshold: int = DEFAULT_THRESHOLD) -> tuple[dict, str | None]:
    """信心低於門檻 → spec 降級為 `cannot-verify`。回 (判定, 註記)。

    **降級,不是扣分**:沒把握的綠燈不算綠燈,但它也不會被拿去和別票平均。
    沒有信心欄位者不降級(舊格式相容),但註明「未提供信心」供稽核。
    """
    v = dict(verdict)
    conf = v.get("confidence")
    if conf is None:
        return v, f"{v.get('seat') or '(未具名席)'}:未提供信心分數(舊格式)"
    if conf < threshold:
        v["spec"] = "cannot-verify"
        v["downgraded"] = True
        return v, (f"{v.get('seat') or '(未具名席)'}:信心 {conf} < {threshold} "
                   f"→ 降級為 cannot-verify(沒把握的綠燈不算綠燈)")
    return v, None


def adjudicate(verdicts, threshold: int = DEFAULT_THRESHOLD) -> tuple[bool, str]:
    """面板裁決。回 (是否放行, 人讀訊息)。

    規則沿用 review-panel:
      · **spec fail = 否決**,裁決者不得推翻——規格不符是事實判斷,不是意見
      · quality fail 同樣擋下
      · 全體 cannot-verify → 擋下:「查不出來」不等於「沒問題」(KN-004)
      · 分歧**不平均**:任何一票有把握的反對即成立
    """
    if not verdicts:
        return False, "面板無任何判定行——沒有輸出不算通過"
    graded, notes = [], []
    for v in verdicts:
        g, note = downgrade(v, threshold)
        graded.append(g)
        if note:
            notes.append(f"    · {note}")
    prefix = ("信心降級紀錄:\n" + "\n".join(notes) + "\n") if notes else ""

    def who(v):
        return v.get("seat") or v.get("model") or "(未具名席)"

    vetoes = [v for v in graded if v["spec"] == "fail"]
    if vetoes:
        return False, (prefix + "面板裁決:**否決**——"
                       + "、".join(f"{who(v)} 判 spec: fail" for v in vetoes)
                       + "。規格不符是事實判斷,不是意見,裁決者不得以其他席的贊成票推翻。\n"
                       + "\n".join(f"    {v['line']}" for v in vetoes))
    quality_fail = [v for v in graded if v["quality"] == "fail"]
    if quality_fail:
        return False, (prefix + "面板裁決:擋下——"
                       + "、".join(f"{who(v)} 判 quality: fail" for v in quality_fail))
    if all(v["spec"] == "cannot-verify" for v in graded):
        return False, (prefix + "面板裁決:擋下——**全席皆無法判定**。"
                       "「查不出來」不等於「沒問題」:放行等於把未經判斷的變更往下游送。\n"
                       "    請補足證據(縮小 diff、補上下文)或降低門檻後重跑。")
    passed = [v for v in graded if v["spec"] == "pass"]
    return True, (prefix + f"面板裁決:放行({len(passed)}/{len(graded)} 席有把握地通過"
                  + (f",{len(graded) - len(passed)} 席無法判定)" if len(passed) != len(graded)
                     else ")"))


CROSS_RE = re.compile(
    r"\[cross\]\s*([^\s|]+)\s*(?:→|->)\s*([^\s|]+)\s*\|\s*(agree|disagree)\s*\|?\s*(.*)",
    re.IGNORECASE)


def parse_cross(text) -> list:
    """解析交叉讀階段的旗標行 `[cross] A→B | agree|disagree | 理由`。"""
    if not text or not isinstance(text, str):
        return []
    return [{"from": m.group(1), "to": m.group(2),
             "agree": m.group(3).lower() == "agree", "reason": (m.group(4) or "").strip()}
            for m in CROSS_RE.finditer(text)]


def cross_brief(verdicts, seat: str) -> str:
    """第二階段簡報:讓這一席讀其他席的判定並標記同意與否。

    第一階段刻意不給(防定錨:先讀到別人的結論,就會先同意它);
    第二階段才給,而且只求標記分歧,不求達成共識——
    **分歧是調和或升級,絕不平均**。
    """
    others = [v for v in verdicts if v.get("seat") != seat]
    lines = "\n".join(f"    {v['line']}" for v in others) or "    (無其他席判定)"
    return (f"交叉讀階段。你是 **{seat}** 席,已經給過自己的判定。\n"
            f"以下是其他席的判定,請逐一標記你是否同意——只標記,不要改自己的判定,\n"
            f"也不要為了一致而讓步:分歧會被升級處理,不會被平均掉。\n\n"
            f"{lines}\n\n"
            f"每一席輸出一行:\n[cross] {seat}→<對方席> | agree|disagree | 一句理由\n")


def adjudicate_cross(crosses) -> tuple[bool, str]:
    """交叉讀的裁決:有分歧就擋下並點名雙方,交人處理。

    review-panel:「A disagreement is reconciled or escalated — never averaged」。
    runner 不會替兩席做調和,那需要判斷;它只負責讓分歧無法被靜默吞掉。
    """
    dis = [c for c in (crosses or []) if not c["agree"]]
    if not dis:
        return True, f"交叉讀:{len(crosses or [])} 條旗標,無分歧"
    rows = "\n".join(f"    · {c['from']} → {c['to']}:{c['reason'] or '(未寫理由)'}"
                     for c in dis)
    return False, ("交叉讀:**席次之間有分歧**,升級交人——分歧是調和或升級,絕不平均。\n"
                   + rows)


def load_seats(path=None) -> dict:
    p = Path(path) if path else SEATS_TABLE
    return json.loads(p.read_text(encoding="utf-8-sig")).get("seats", {})


def seats_for(risk: str, override=None, seats=None) -> tuple[list, str | None]:
    """依風險分級決定開幾席。回 (座位清單, 註記)。

    覆寫可以往上加,不能往下減到分級下限以下——否則「面板」會變成
    一個可以隨手關掉的裝飾。
    """
    table = seats if seats is not None else load_seats()
    order = list(table.keys())
    floor = SEATS_BY_RISK.get((risk or "low").lower(), 1)
    n, note = floor, None
    if override:
        try:
            want = int(override)
        except (TypeError, ValueError):
            want = floor
        if want < floor:
            note = (f"--review-panel {want} 低於 {risk} 風險的下限 {floor} 席,"
                    f"已提升為 {floor}——面板是風險的深度,不是可隨手關掉的裝飾")
        n = max(floor, want)
    n = min(n, len(order)) if order else n
    return order[:n], note


def seat_brief(chg_text: str, task, seat: str, seats=None) -> str:
    """單一座位的簡報:**只含自己那一列**。

    review-panel:「the panel view belongs to the dispatcher」——
    給了整張表,座位就會開始揣測別人會怎麼投,而那正是獨立性的反面。
    """
    table = seats if seats is not None else load_seats()
    spec = table.get(seat, {})
    gc = chg_text[chg_text.find("### Global Constraints"):]
    gc = gc[:gc.find("### Tasks")] if "### Tasks" in gc else gc[:1500]
    tid = task["tid"] if isinstance(task, dict) else str(task)
    title = task.get("title", "") if isinstance(task, dict) else ""
    return (
        f"你是本次 diff 審查面板的其中一席:**{seat}**。唯讀審查,不修改任何檔案。\n"
        f"你的職責(只有這一條,其他席次的職責不歸你管,也不會告訴你):\n"
        f"  {spec.get('question', '(未定義)')}\n"
        f"你的判定必須引用證據:{spec.get('evidence', 'file:line')}。\n"
        f"沒把握就給低信心分數——**沒把握的綠燈不算綠燈**,低於門檻會被降級為無法判定,\n"
        f"那是正當的結果,不是失敗。不要為了給出結論而提高信心。\n\n"
        f"最後輸出一行判定:\n"
        f"[task-review] {tid} | {seat} | <你的模型名> | spec: pass|fail|cannot-verify | "
        f"quality: pass|fail | conf: 0-100 | 理由\n\n"
        f"{gc}\n\n## Task\n{tid}. {title}\n")
