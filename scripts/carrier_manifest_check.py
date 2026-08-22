#!/usr/bin/env python3
"""載體宣告閘 — CI 載體上的每一步都要具名附理由,兩個方向都嚴格。

## 為什麼判準不是「兩個載體的腳本集合相等」

那是我(主 agent)的原提案,**審議席駁回,理由是它抓不到觸發它的那隻 bug**。

事故的真實形狀:夾具搬家只改了 `ci_local.sh`,而 `governance.yml` 有自己一份
同樣的迴圈。那段在兩個載體**都是 inline bash,不是腳本呼叫**——
腳本集合當時完全一致,分岔的是內容。集合比對對它全盲。

而且範圍也錯:`[3b]` 成語 strict 紅端、`[10c]` 空輸入、`[10d]` 未驗到名單
這三道也是 inline,同樣不在任何「腳本集合」裡。

## 真正的判準:宣告完整

`CHG-20260816-01` 把兩個載體合一之後,`governance.yml` 只剩三步
(checkout / setup-python / 呼叫 `ci_local.sh`)。於是斷言塌縮成一條
**不必解析 bash 語意**的規則:

    workflow 裡的每一步都必須在 MANIFEST 具名並附理由。

新增一道「只在 CI 跑」的閘,就必須在這裡寫下它是什麼、為什麼不能進 ci_local。
寫不出理由,就是不該有那一步。

## 雙向嚴格(比照 [10d] 的 EXPECT_UNVERIFIED)

- 實際有、MANIFEST 沒有 → 紅(新步驟偷渡)
- MANIFEST 有、實際沒有 → 紅(**否則 MANIFEST 會腐爛成裝飾**)

一多一少都轉紅。單向的名單活不過三次改動。

## 掃描面是全部 workflow 檔,不是只有 governance.yml

否則開第二個 workflow 檔就是免費旁路。

## 為什麼還要掃 ci_local.sh 與 verify.sh

載體合一之後,載體條件會**遷徙**:有人在 ci_local 裡寫
`if [ "$GITHUB_EVENT_NAME" = "pull_request" ]; then ...`,
那道閘就又變成只在一個載體跑,而只掃 workflow 的斷言看不見。

所以跨界的環境變數要具名,允許名單只有 `CI_SINCE_REF`。

## 誠實極限

**這是文字層斷言,刻意的間接引用繞得過**——把變數名拼起來、從檔案讀、
用 `env` 轉一手,都不會被抓到。本 repo 的威脅模型是「未來的自己忘記」,
不是對抗者;為後者加固會把這道閘變成它自己拒絕成為的東西(關鍵字遊戲)。

**不用 PyYAML。** `setup-python` 給的是乾淨環境,而本 repo 所有的閘都只用標準庫;
為一道閘引入外部依賴,等於給它裝一顆隨時會炸的引信,而炸的時候長得像規則失效。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# **十支閘裡只有本檔漏了這一行。**(CHG-20260816-02 二讀,審議席實測)
# cp950 主控台下,`✅` 與 `✗` 都不是可編碼字元——成功與失敗兩條路徑都會
# UnicodeEncodeError,於是本閘在那個環境**永遠 rc=1**。一個恆紅、且紅得
# 與程式碼無關的閘,教會人的是忽略它(KN-002)。而它崩在 print 上,
# 訊息長得像規則失效,不像環境問題。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# ── MANIFEST:workflow 裡每一步的具名與理由 ─────────────────────────────
# key = (workflow 檔名, 步驟識別)  value = 為什麼這一步必須在載體上,而不能進 ci_local
MANIFEST: dict[tuple[str, str], str] = {
    ("governance.yml", "actions/checkout@v4"):
        "載體啟動最小集:取得原始碼。fetch-depth 0 是 diff 式閘取 merge-base 的前提,"
        "淺 clone 取不到分岔點時訊息會長得跟「沒 fetch」一樣。",
    ("governance.yml", "actions/setup-python@v5"):
        "載體啟動最小集:Python 執行環境。ci_local 只做 python3/python 的 fallback,"
        "不負責安裝直譯器。",
    ("governance.yml", "governance gates (single source of truth)"):
        "唯一真相源的呼叫點。CI_SINCE_REF 只在 push 事件傳 github.event.before——"
        "那是這次 push 之前的 tip,不依賴 merge 策略;pull_request 不傳,"
        "ci_local 自己退回 origin/main。",
}

# ── 允許跨載體邊界的環境變數 ────────────────────────────────────────────
# 每多一個,ci_local 就多知道一點「自己跑在哪裡」,而載體不可知正是合一的前提。
#
# **誠實極限(兩席共記,CHG-20260822-01)**:「ci_local 不得因環境而變更判定行為」
# 對**任意命名**的環境變數沒有機器斷言——`ENV_TOKEN` 只掃 `GITHUB_/RUNNER_/CI_` 三族,
# 族外名字全盲。這是既有的、`BL-017` 型的極限,不是施工模式那一案新開的洞;
# 施工模式本身走命令列,不經環境,所以它的守衛在 `APPROVED_CALL` 那一段,不在這裡。
CARRIER_ENV: dict[str, str] = {
    "CI_SINCE_REF":
        "diff 式閘的基準。push 事件下 origin/main 就是 HEAD 自己,REF..HEAD 恆空,"
        "規則對每個檔案都判「沒變」而輸出與真通過一字不差。",
}

# 掃這些檔有沒有偷讀載體身分。ci_local 是唯一真相源,verify.sh 被它呼叫。
CARRIER_AWARE_SCRIPTS = (".github/ci_local.sh", ".github/verify.sh")

# `CI` 本身不列入:它在 shell 裡太常見於別的語意(檔名、註解),
# 而真正會造成載體分歧的是 GITHUB_/RUNNER_ 這兩族。誠實極限已在 docstring 寫明。
ENV_TOKEN = re.compile(r"\b(GITHUB_[A-Z_]+|RUNNER_[A-Z_]+|CI_[A-Z_]+)\b")

_STEP_HEAD = re.compile(r"^(\s*)-\s+(name|uses):\s*(.+?)\s*$")
_KEY = re.compile(r"^(\s*)([A-Za-z_][\w-]*):\s*(.*)$")


def steps_of(text: str) -> list[str]:
    """抽出每一步的識別:有 `name:` 用 name,否則用 `uses:`。

    刻意不解析整棵 YAML:本 repo 的 workflow 是自己寫的、很小,而引入 PyYAML
    會讓這道閘依賴一個 CI 上不保證存在的套件——閘因為缺套件而炸,
    輸出長得像規則失效,那是 KN-002 的溫床。

    註解要先剝掉,否則 docstring 或註解裡提到的 `- uses:` 會被當成真步驟
    (施工時就踩到:本檔自己的說明文字被算成一步)。
    """
    out: list[str] = []
    pending_uses: str | None = None
    step_indent: int | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if not line.strip():
            continue
        m = _STEP_HEAD.match(line)
        if m:
            if pending_uses is not None:
                out.append(pending_uses)
                pending_uses = None
            indent, key, val = len(m.group(1)), m.group(2), m.group(3).strip()
            step_indent = indent
            if key == "name":
                out.append(val)
                step_indent = None          # 已定名,本步之後的 uses 不再算
            else:
                pending_uses = val
            continue
        k = _KEY.match(line)
        if k and pending_uses is not None and step_indent is not None:
            # 同一步之內後來才出現 name:,以 name 為準
            if k.group(2) == "name" and len(k.group(1)) > step_indent:
                out.append(k.group(3).strip())
                pending_uses = None
    if pending_uses is not None:
        out.append(pending_uses)
    return out


# ── 唯一真相源的呼叫必須是核准的字面值(CHG-20260822-01 / BL-030)──────
#
# `ci_local.sh` 新增了施工模式參數 `--allow-wip`,它放行「施工中且對應 ACC 尚不存在」的 CHG。
# **正式 workflow 絕不可以帶它**——帶了就等於把收尾閘長期關掉,而失效型態是靜默綠。
#
# 為什麼守衛放在這裡而不是 `CARRIER_ENV`:第一版設計把意圖走環境變數 `CI_ALLOW_WIP`,
# 理由是「取 `CI_` 前綴才落在 `ENV_TOKEN` 的掃描域內」。審議席(fable)第三輪推翻了它——
# **環境是可寫的通道**:GitHub Actions 的 `GITHUB_ENV` 允許前置步驟
# `echo "NAME=value" >> "$GITHUB_ENV"`,而那行字串**可以拼接構造**,
# 變數名不必完整出現在 workflow 檔的任何地方,文字層掃描**必然全盲**。
# 改走命令列之後,守衛從「掃 token」升級成**結構釘死**。
#
# **整段字面值比對,不解析 YAML。** 抽出該步的 `run:` 純量、與核准字串逐字比對即可,
# 不需要理解多行區塊語義,也就不引入 `steps_of` 刻意迴避的 PyYAML 依賴(理由 KN-002)。
# 代價誠實寫明:改用 `|` / `>` 多行區塊寫同一道指令會**紅**——那是刻意的,
# 想改呼叫形式就得同步改這裡的核准值並在 CHG 說明。
APPROVED_CALL = "bash .github/ci_local.sh"
_RUN_LINE = re.compile(r"^\s*run:\s*(.+?)\s*$")
_TTS_STEP = "governance gates (single source of truth)"


def run_of_step(text: str, step_name: str) -> str | None:
    """抽出某一步的單行 `run:` 純量。多行區塊或找不到都回 None(呼叫端判紅)。"""
    lines = text.splitlines()
    for i, raw in enumerate(lines):
        if raw.strip() == f"- name: {step_name}" or raw.strip() == f"name: {step_name}":
            for nxt in lines[i + 1:]:
                st = nxt.strip()
                if st.startswith("- ") or (st.startswith("name:") and "run:" not in st):
                    break                      # 進到下一步了
                m = _RUN_LINE.match(nxt)
                if m:
                    v = m.group(1)
                    return None if v in ("|", ">", "|-", ">-") else v
            return None
    return None


def check(workflows: dict[str, str], scripts: dict[str, str],
          manifest: dict[tuple[str, str], str],
          carrier_env: dict[str, str]) -> list[str]:
    """純函式:吃文字、吐問題。**吃文字是為了讓 self-test 打得到每一端。**"""
    bad: list[str] = []

    declared = set(manifest)
    actual: set[tuple[str, str]] = set()
    for fname, text in workflows.items():
        for s in steps_of(text):
            actual.add((fname, s))

    for key in sorted(actual - declared):
        bad.append(f"workflow 步驟未具名:{key[0]} 的「{key[1]}」"
                   "——新增只在 CI 跑的東西,就要在 MANIFEST 寫下它是什麼、"
                   "以及為什麼不能進 ci_local.sh")
    for key in sorted(declared - actual):
        bad.append(f"MANIFEST 具名了不存在的步驟:{key[0]} 的「{key[1]}」"
                   "——名單腐爛成裝飾,雙向嚴格才擋得住")
    for key, reason in sorted(manifest.items()):
        if not reason.strip():
            bad.append(f"MANIFEST 的「{key[1]}」沒有理由——具名而不附理由等於沒具名")

    # 唯一真相源的呼叫必須精確等於核准字面值——附加參數、改寫形式、多行區塊都紅。
    for fname, text in workflows.items():
        if (fname, _TTS_STEP) not in manifest:
            continue                            # 這份 workflow 沒有唯一真相源那一步
        got = run_of_step(text, _TTS_STEP)
        if got is None:
            bad.append(f"{fname}:抽不出「{_TTS_STEP}」的單行 `run:`"
                       "——唯一真相源的呼叫必須是可逐字比對的單行,"
                       "改成多行區塊就沒有東西守得住「不得帶施工參數」")
        elif got != APPROVED_CALL:
            bad.append(f"{fname}:唯一真相源的呼叫不是核准字面值。"
                       f"核准「{APPROVED_CALL}」,實得「{got}」"
                       "——正式 CI 不得帶 `--allow-wip` 或任何施工模式參數,"
                       "帶了就是把收尾閘長期關掉,而失效型態是靜默綠")

    for path, text in scripts.items():
        for line_no, raw in enumerate(text.splitlines(), 1):
            line = raw.split("#", 1)[0]
            for tok in ENV_TOKEN.findall(line):
                if tok not in carrier_env:
                    bad.append(f"{path}:{line_no} 讀了載體變數「{tok}」而未具名"
                               "——載體條件遷徙進唯一真相源,只掃 workflow 的斷言看不見它")
    return bad


# ── self-test ──────────────────────────────────────────────────────────

_WF_OK = """name: governance
on: { pull_request: }
jobs:
  governance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: gates
        run: bash .github/ci_local.sh
"""

_MAN_OK = {("governance.yml", "actions/checkout@v4"): "載體啟動最小集",
           ("governance.yml", "gates"): "唯一真相源的呼叫點"}


def self_test() -> int:
    fails: list[str] = []
    ran: list[str] = []

    def case(label: str, wf, sc, man, env, want: str | None):
        ran.append(label)
        got = check(wf, sc, man, env)
        if want is None:
            if got:
                fails.append(f"{label} 應綠卻紅:{got}")
        elif not any(want in g for g in got):
            fails.append(f"{label} 應紅於「{want}」,實得:{got or '全綠'}")

    # r1:workflow 多一步未具名
    wf_extra = _WF_OK.replace("      - name: gates",
                              "      - name: sneaky lint\n        run: python3 x.py\n      - name: gates")
    case("r1 未具名的 workflow 步驟",
         {"governance.yml": wf_extra}, {}, _MAN_OK, CARRIER_ENV, "未具名")

    # r2:ci_local 偷讀載體身分
    case("r2 唯一真相源偷讀 GITHUB_*",
         {"governance.yml": _WF_OK},
         {".github/ci_local.sh": 'if [ "$GITHUB_EVENT_NAME" = "push" ]; then :; fi\n'},
         _MAN_OK, CARRIER_ENV, "未具名")

    # g:兩者都具名附理由
    case("g 具名附理由", {"governance.yml": _WF_OK},
         {".github/ci_local.sh": 'SINCE_REF="${CI_SINCE_REF:-origin/main}"\n'},
         _MAN_OK, CARRIER_ENV, None)

    # ── 唯一真相源的呼叫必須是核准字面值(CHG-20260822-01 / BL-030)──
    # 綠端用**真實步驟名**,紅端全部由它單一突變產生。
    _WF_TTS = _WF_OK.replace("      - name: gates" + chr(10) +
                             "        run: bash .github/ci_local.sh",
                             "      - name: " + _TTS_STEP + chr(10) +
                             "        run: " + APPROVED_CALL)
    _MAN_TTS = {("governance.yml", "actions/checkout@v4"): "載體啟動最小集",
                ("governance.yml", _TTS_STEP): "唯一真相源的呼叫點"}
    case("g2 唯一真相源呼叫為核准字面值",
         {"governance.yml": _WF_TTS}, {}, _MAN_TTS, CARRIER_ENV, None)

    # **本案的核心紅端**:workflow 帶施工參數 → 收尾閘被長期關掉,失效型態是靜默綠。
    case("r3 workflow 帶 --allow-wip",
         {"governance.yml": _WF_TTS.replace(APPROVED_CALL, APPROVED_CALL + " --allow-wip")},
         {}, _MAN_TTS, CARRIER_ENV, "不是核准字面值")
    # 換一個入口繞過去也要紅(不是只擋那一個字串)
    case("r4 workflow 改呼叫別的入口",
         {"governance.yml": _WF_TTS.replace(APPROVED_CALL, "bash .github/dev_check.sh")},
         {}, _MAN_TTS, CARRIER_ENV, "不是核准字面值")
    # 改成多行區塊就沒有東西守得住 → 也要紅,不能靜默放行
    case("r5 唯一真相源改成多行 run 區塊",
         {"governance.yml": _WF_TTS.replace("run: " + APPROVED_CALL,
                                            "run: |" + chr(10) + "          " + APPROVED_CALL)},
         {}, _MAN_TTS, CARRIER_ENV, "抽不出")

    # 基準判別性:同一個綠端案,在空 MANIFEST 這個**錯的基準**下必須紅。
    # 沒有這一案,「綠端會綠」可能只是因為斷言根本沒在看 workflow。
    case("基準 空 MANIFEST 下綠端必紅", {"governance.yml": _WF_OK},
         {}, {}, CARRIER_ENV, "未具名")

    # 反腐:MANIFEST 具名了不存在的步驟
    case("反腐 具名了不存在的步驟", {"governance.yml": _WF_OK}, {},
         {**_MAN_OK, ("governance.yml", "早就刪掉的步驟"): "理由"},
         CARRIER_ENV, "不存在的步驟")

    # 具名但理由空白
    case("具名而無理由", {"governance.yml": _WF_OK}, {},
         {**_MAN_OK, ("governance.yml", "actions/checkout@v4"): "  "},
         CARRIER_ENV, "沒有理由")

    # 允許名單內的變數不得誤紅(規則對正確輸入恆假的第 N 次防線)
    case("綠 允許名單內的 CI_SINCE_REF", {"governance.yml": _WF_OK},
         {".github/ci_local.sh": 'echo "$CI_SINCE_REF"\n'}, _MAN_OK, CARRIER_ENV, None)

    # 註解裡的 GITHUB_ 不算(否則本檔自己的說明文字就會讓閘紅)
    case("綠 註解裡提到 GITHUB_ 不算",
         {"governance.yml": _WF_OK},
         {".github/ci_local.sh": '# 本檔不得讀 GITHUB_EVENT_NAME\necho hi\n'},
         _MAN_OK, CARRIER_ENV, None)

    if fails:
        for f in fails:
            print(f"  ❌ {f}")
        print("\n✗ self-test 未通過:載體宣告閘的紅綠端不可達。")
        return 1
    print(f"✅ self-test:{len(ran)} 案全過(" + "、".join(ran) + ")")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    repo = Path(".").resolve()
    if "--repo" in argv:
        repo = Path(argv[argv.index("--repo") + 1]).resolve()

    wf_dir = repo / ".github" / "workflows"
    workflows = {p.name: p.read_text(encoding="utf-8") for p in sorted(wf_dir.glob("*.yml"))}
    workflows.update({p.name: p.read_text(encoding="utf-8") for p in sorted(wf_dir.glob("*.yaml"))})
    if not workflows:
        print("✗ 找不到任何 workflow 檔——掃描面是空的,這道閘等於不存在")
        return 1

    scripts = {}
    for rel in CARRIER_AWARE_SCRIPTS:
        p = repo / rel
        if not p.exists():
            print(f"✗ 找不到 {rel}——唯一真相源不見了,或路徑變了(autopilot runner "
                  "的 local-gate 探測也寫死這個路徑)")
            return 1
        scripts[rel] = p.read_text(encoding="utf-8")

    bad = check(workflows, scripts, MANIFEST, CARRIER_ENV)
    if bad:
        print("✗ 載體宣告閘:")
        for b in bad:
            print("  - " + b)
        return 1
    print(f"✅ 載體宣告閘:{len(workflows)} 個 workflow 檔、{len(MANIFEST)} 步全部具名附理由;"
          f"唯一真相源與 verify.sh 未讀取允許名單以外的載體變數"
          f"(允許:{'、'.join(CARRIER_ENV)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
