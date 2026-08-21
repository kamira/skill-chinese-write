# handshake — autopilot

機器區塊(`autopilot:begin/end`)由 runner 覆寫,人手交接寫在標記之外。

## 最近一次進場(人手)

- 時間:2026-08-21 (UTC+0)
- branch:`claude/ai-sdlc-handshake-c7b2a2`(worktree;**無 upstream**,但 tip == `origin/main` == `b8506dc`,基準最新)
- worktree:clean;無未提交變更可對帳
- commit 對帳:錨點 `ACC-20260820-02` 的 commit(`b8506dc`)即 HEAD,錨點後**零筆** commit,無未治理工作
- 未收尾:**無**。CHG 41 張 / ACC 36 份;差額 5 張全部有歸屬——
  `CHG-20260810-09`→`ACC-20260810-07`、`CHG-20260810-10`→`ACC-20260810-08`、
  `CHG-20260817-03/-04/-05`→`ACC-20260817-02`(三張合併驗收)。
  `doc_integrity_check.py --repo .` exit 0
- 治理路徑:`docs/writing/`(非預設 `docs/`);本 repo **沒有** `ai-guideline.md` / `coordination.md` / `structure/`,
  入口是 `AGENTS.md`,結構真相源是 `scripts/skill_inventory_check.py` 與 `docs/genres.md`
- knowledge INDEX 生效條目:KN-001 / KN-002 / KN-003 / KN-004 + DIR-001(低中風險預先授權)+ DIR-002(codex + fable 互審)
- skill 版本自檢:帳本記載 `Skill: ai-sdlc v1.35`,執行中的 skill 為 **v1.64.0** —— 記錄較舊,新規則只往後適用,**不需升級**

### 本輪查到、上一棒沒有記過的兩件事

**(1) 工具鏈探測回 `NOT_RUN`,而原因不是缺相依,是本 repo 沒有那個載具。**
`bash <plugin>/skills/ai-sdlc-autopilot/scripts/toolchain_probe.sh .` → 直譯器找到
(`python3` 3.11.9),但 `requirements-dev.txt` 不存在,判定 `NOT_RUN` / exit 4。
本 repo 的治理閘**只用標準庫**(`.github/workflows/governance.yml` 只 setup-python 3.12,
不跑任何 `pip install`),所以「沒有 requirements-dev.txt」是實情,不是缺件。
**但 `NOT_RUN` 不得自行升級成 `PASS`**——三態的意義正是「沒查成」與「沒問題」要分得開。
處置:本 repo 需要自己的探測載具(或在 repo 內宣告零第三方相依的等價聲明),
`tools/` 目前**沒有**把 `toolchain_probe.sh` 帶過來(`PROVENANCE.json` 的 42 支清單裡沒有它)。

**(2) 隨身工具落後上游,而漂移閘依設計查不出來。**
`tools/tools_drift_check.py` → 42 支與帶過來當下一致(來源 commit `88ac05a`)。
但握手協定要求的 `doc_integrity_check.py --repo . --check-baseline` 在本地副本
**不存在這個旗標**(argparse 直接 exit 2);上游同名檔第 986 行有。
上游 `skill-ai-sdlc-autopilot` 現在是 `e09d721` / skill v1.64.0,本地副本停在 v1.35 那一代。
基準對帳本輪改用等價的 `git fetch` + `git log --oneline HEAD..origin/main`(空 → 最新)。
這正是 `PROVENANCE.json` 自己寫明的盲區:「本檢查看不出上游是否已前進」。

## 已收尾:DIR-002 擴大案(2026-08-21)

使用者原話(2026-08-21 UTC+0):「所有及往後的修正項目全部交由 fable 和 codex 交叉決議達成共識」。
`CHG-20260821-01` / `ACC-20260821-01` 收尾。DIR-002 改寫為五款,並補上它生效八天以來
**一直沒有的斷言**(`scripts/chg_field_check.py` 判定三,掛 `ci_local.sh` 第 [9/19] 步)。

- **第 1~4 款**:兩席第三輪各自明示同意同一份文字
- **第 5 款**:三輪未收斂,依第 2 款主動上報,使用者裁決「兩者都要,但分階段」——
  本輪落 fable 版(單項免表),codex 的「一律附表」轉為 `BL-032`
- **風險評級**:codex 判高、fable 判中,使用者裁決以中風險路徑走到 merge
- 審議全文六份存於該 session 的 scratchpad(未進帳本);實質理由已抄進 CHG 與 ACC

**下一次有修正項目送審時,第一項議程**:覆核標頭第四種形狀 `使用者裁決(記於 <編號>)`——
它是主 agent 依第 2 款推導後新增的,兩席都沒審過(已記於 `BL-032`)。

## 目前的停點(2026-08-13,工具鏈)

進場時本機治理閘一步都跑不動,原因有兩個,**都不是程式碼缺陷,是前置條件缺席**。兩個都已解除。

**(1) `python3` 不在 PATH 上。** Python 3.11.9 其實**已經裝好**
(`AppData/Local/Programs/Python/Python311/python.exe`),但**該目錄底下沒有 `python3.exe`**;
而 `python3` 解析到 `WindowsApps/python3.exe`——那是一個指向
`AppInstallerPythonRedirector.exe` 的符號連結,Microsoft Store 的轉址殼,不是 Python。
後果:`.github/ci_local.sh` 在 `[1/13]` 就死。

已解除(使用者授權):在真目錄建 `python3.exe` 複本。PATH 順序上 `Python311` 排在
`WindowsApps` **前面**,所以真檔一存在就會贏。驗證:`bash .github/ci_local.sh`
**13 步全綠、exit 0,不掛任何 shim**。
(那是當時的步數。`CHG-20260816-01` 把兩個 CI 載體合一之後是 18 步——
上面兩個數字是**事故當時的紀錄**,不是現況;確切步數以實跑輸出為準。)

**(2) `core.hooksPath` 哪一層都沒設。** local / global / 主 repo 查下來全空——本檔先前寫
「已指向 `.githooks/`」是**錯的**。`scripts/install-hooks.sh` 自己的註解就講明原因:
core.hooksPath 是本機設定、不隨 clone 過來,這是撤掉 CI 之後留下的已知缺口。
後果:就算修好 python3,push 時仍然沒有任何閘。

已解除:跑過 `bash scripts/install-hooks.sh`,主 repo 與 worktree 皆生效。

**下一台新機器仍會同時踩到這兩個**——它們都不隨 repo 走。第 (2) 個尤其容易被誤判為
「已經設好了」,因為本檔曾經這樣寫。

## 這一輪發生過的停點(已解除,留紀錄)

**merge 閘曾因 CI 停擺卡住。** GitHub Actions 回報
`The job was not started because recent account payments have failed`——私有 repo 的帳務問題,
與程式碼無關,且**把 workflow 改小是無效解**(擋的是 job 啟動,不是步驟)。

解除方式:repo 改名 `skill-chinese-write` → 轉 public(Actions 對 public 免費)→ 同一份
`governance.yml` 一行未改即由紅轉綠。轉 public 是不可逆動作,由使用者在出示普查結果後拍板,
不走 DIR-001 的預先授權。

## 曾經的停點:PR #6 卡 merge 閘(已解除,留紀錄)

**PR #6(CHG-20260810-07)一度停在 merge 閘。** GitHub Actions 的 workflow 是 active、
Actions 權限正常、repo 是 public,但**完全沒有為 `claude/version-sync` 建立任何 run**——
開 PR、close/reopen、推空 commit 三種觸發都沒有。與 8/10 上午那次不同:那次有帳務訊息,
這次沒有任何錯誤,單純不啟動。

判定不出 CI 狀態 → 一律停(DIR-001 明文,不在預先授權內)。本機九步閘全綠,
**但本機綠不能當作 merge 的依據**。

**已解除**:PR #6 以 `1eecfcf` 進 `main`,其後 CHG-08 / -09 / -10 皆已 merge 並驗收。

## 待辦需求(已收到,尚未開 CHG)

1. **分類重構**——「skill 只分大類,細項寫作技巧與目標下放到 skill 底下的指令」。
   已拍板:大類軸=依規則引擎切(writing / fiction / techdoc / bizdoc)+ 第五類「無引擎文體」
   + zh-style 橫切引擎;指令形式=`references/` 與 `commands/` 雙軌,且必須配「薄殼不懸空」斷言。
   **高風險**(marketplace 21 個 entry 砍到 5、已發布 plugin id 消失),不走 DIR-001 自動 merge。
   推翻 CHG-20260810-08 與 KN-003 的觸發面優先結論,CHG 要寫明「這是第三次改寫」與憑什麼新證據。

2. **新增「自傳」文體**(2026-08-13 使用者提出)。尚未決定落點。
   關鍵判斷:台灣語境的自傳多半是**求職 / 升學自傳**,與 `historiography` 的史傳、人物傳記
   **不是同一種東西**(前者是應用文、有目的、有讀者;後者是紀實文學)。不要直接併進去。
   落點取決於第 1 項:若分類重構先做,它應該是某個大類底下的一份 reference + command,
   而不是第 24 支獨立 skill——現在單開一支,重構時會立刻被收掉。
   另需判斷它能不能配斷言(結構節次、字數、流水帳偵測看起來可判,禁忌用語可用詞表),
   若判不了就要照 KN-001 明標「本支沒有 lint」。

## 下一棒要知道的事

- repo 已 public,舊名 `kamira/skill-write` 由 GitHub 轉址;marketplace id 也一併改名
- `core.hooksPath` → `.githooks/`,push 前會自動跑 `.github/ci_local.sh`。**2026-08-13 實測本機根本沒設過**——新機器一定要跑 `scripts/install-hooks.sh`,而且要**實際 `git config core.hooksPath` 查一次**,不要相信這份 worklog 說已經設好了
- **本 repo 的結構是引擎 + 前門兩層 / 5 份規則檔**(確切數目以 `scripts/skill_inventory_check.py --repo .` 為準,寫死的計數會隨每次退役腐爛)(第五支 `zh-style` 是跨文體引擎,所有 plugin 打包)。前門 + 引擎分層:
  前門管觸發與寫作指引,引擎管判定;前門的 plugin 會把引擎一起打包。舊說明(四支):`writing`(評論)、`fiction`(小說)、`techdoc`(規格書+架構說明)、`bizdoc`(公文+新聞稿)。
  拆分判準見 knowledge 的 **KN-003**:硬規則相反才拆,只差結構的用旗標,規格薄的先不拆
- 使用者定調:**different write should be different skill**,收斂為 KN-003
- **可拆的文體已用完**:剩下 9 個的核心指標都是修辭比例,量不出來,現在拆會生空頭規則(見 `docs/genres.md` 的難點欄)
- **治理規則本身也要有斷言**(KN-001 已擴及):`scripts/chg_diagram_gate.py` 管住
  「中/高風險 CHG 要有設計圖」。加新治理規則時,順手問它有沒有對應的閘

<!-- autopilot:begin -->
branch/role/scope: build / claude/fixture-cross-review(23 commit,未 push)
doing: CHG-20260814-01 **已收尾**(ACC-20260814-01,單方)。CHG-20260813-01 已驗收但
  ACC 維持「驗收程序未完結」
review: 使用者已把決議、下一動、AI 味評分全部交審議席(DIR-002),並宣布不再人審。
  fable 跑完 V1-V6 分項審議 + 路線裁決 + 分歧裁決;codex 給四題判定後 MCP 斷線缺席
next(**兩件都等 codex 恢復**):
  1. codex 覆核 fable 推翻其一、二題的理由
  2. fable 對「V2-V6 之後十六處修正」的逐項具名複審 → 通過才准把 ACC-20260813-01 改記完成
  3. 之後才談 merge / PR——不可逆,不歸單席,也不歸審議席
known:
  - **BL-001/002/003** 三項後續已編號待做(--strict 正反例對、per_k helper、近似比對評估案)
  - 章法層同構機器判不了;R1/R2/R4 三篇議題型骨架完全同模
  - R5 五個指紋零命中,但它是唯一跑過 G-2 才交稿的,**不足以推論 skill 變好**
  - 閘上線後抓到主 agent 兩次(19 片段、8 片段),兩次都是「寫規則時把文字搬過去」
last-updated: 2026-08-14 (UTC+0)
<!-- autopilot:end -->
