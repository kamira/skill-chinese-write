# handshake — autopilot

機器區塊(`autopilot:begin/end`)由 runner 覆寫,人手交接寫在標記之外。

## 最近一次進場(人手)

- 時間:2026-08-13 (UTC+0)
- branch:`claude/ai-sdlc-handshake-ae9a3d`(worktree;無 upstream,但 tip == `origin/main` == `main` = `46331e8`,**基準最新**)
- worktree:clean;無未提交變更可對帳
- commit 對帳:自 `06f0e89` 至 HEAD **每一筆都帶 CHG 編號**,無未治理 commit
- 未收尾:**無**。CHG-20260727-01 ~ CHG-20260810-10 共 17 張全部收尾;ACC 15 份 + `CHG-20260810-07` 走 CHG-lite(低風險 + 內嵌自驗,依 modification-guide 免獨立 ACC)。`doc_integrity_check.py --repo .` exit 0
- 治理路徑:`docs/writing/`(非預設 `docs/`);knowledge INDEX 生效條目 KN-001 / KN-002 / KN-003 + DIR-001(預先授權)
- skill 版本自檢:帳本記載 `Skill: ai-sdlc v1.22`,執行中的 skill 為 **v1.35.0** —— 記錄較舊,新規則只往後適用,**不需升級**
- 本輪動作:僅進場握手 + 對齊本檔,未改任何受治理內容

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
- **本 repo 現在有 24 支 skill / 21 個 plugin / 5 份規則檔**(第五支 `zh-style` 是跨文體引擎,所有 plugin 打包)。前門 + 引擎分層:
  前門管觸發與寫作指引,引擎管判定;前門的 plugin 會把引擎一起打包。舊說明(四支):`writing`(評論)、`fiction`(小說)、`techdoc`(規格書+架構說明)、`bizdoc`(公文+新聞稿)。
  拆分判準見 knowledge 的 **KN-003**:硬規則相反才拆,只差結構的用旗標,規格薄的先不拆
- 使用者定調:**different write should be different skill**,收斂為 KN-003
- **可拆的文體已用完**:剩下 9 個的核心指標都是修辭比例,量不出來,現在拆會生空頭規則(見 `docs/genres.md` 的難點欄)
- **治理規則本身也要有斷言**(KN-001 已擴及):`scripts/chg_diagram_gate.py` 管住
  「中/高風險 CHG 要有設計圖」。加新治理規則時,順手問它有沒有對應的閘

<!-- autopilot:begin -->
branch/role/scope: build / claude/fixture-cross-review
doing: CHG-20260813-01 **已驗收**(ACC-20260813-01,通過有保留);5 個 commit,ci_local 16 步全綠
next: (a) 開 PR → merge(中風險,DIR-001 涵蓋)→ (b) 分類重構那張(高風險,merge 前要人拍板)→ (c) 自傳文體
known:
  - **fable 兩度 API 529 中斷,DIR-002 只執行了 codex 一方**——fable 沒看過施工結果,不是「兩邊都同意」
  - codex 三條意見有兩條對但未做:逐體裁密度門檻、每條提醒規則要有 --strict 正反例對、per_k 收成 helper
  - D-7 上游 doc_integrity 兩個洞(草稿分支不可達、「暫停」誤觸即豁免)**尚未送回上游**
last-updated: 2026-08-13 (UTC+0)
last-updated: 2026-08-13 (UTC+0)
<!-- autopilot:end -->
