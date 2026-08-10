# handshake — autopilot

機器區塊(`autopilot:begin/end`)由 runner 覆寫,人手交接寫在標記之外。

## 最近一次進場(人手)

- 時間:2026-08-10 08:18 (UTC+0)
- branch:`claude/ai-sdlc-autopilot-handshake-4a3f7a`(worktree;無 upstream,內容與 `main` 一致)
- worktree:clean;自 ACC-20260804-03 起無新 commit,歷史全部帶 CHG 編號
- 未收尾:無。CHG-20260727-01 ~ CHG-20260804-03 共 7 張全部已驗收,ACC 齊備
- 治理路徑:`docs/writing/`(非預設 `docs/`);knowledge 生效條目 KN-001、KN-002
- 已知缺口(CHG-20260804-03 明載):`build` / `review` 兩個角色只證明到停點正確(exit 3),**未接模型實跑**
- 本輪動作:僅進場握手 + 對齊本檔,未改任何受治理內容

## 這一輪發生過的停點(已解除,留紀錄)

**merge 閘曾因 CI 停擺卡住。** GitHub Actions 回報
`The job was not started because recent account payments have failed`——私有 repo 的帳務問題,
與程式碼無關,且**把 workflow 改小是無效解**(擋的是 job 啟動,不是步驟)。

解除方式:repo 改名 `skill-chinese-write` → 轉 public(Actions 對 public 免費)→ 同一份
`governance.yml` 一行未改即由紅轉綠。轉 public 是不可逆動作,由使用者在出示普查結果後拍板,
不走 DIR-001 的預先授權。

## 目前的停點(2026-08-10 12:40 UTC+0)

**PR #6(CHG-20260810-07)停在 merge 閘。** GitHub Actions 的 workflow 是 active、
Actions 權限正常、repo 是 public,但**完全沒有為 `claude/version-sync` 建立任何 run**——
開 PR、close/reopen、推空 commit 三種觸發都沒有。與 8/10 上午那次不同:那次有帳務訊息,
這次沒有任何錯誤,單純不啟動。

判定不出 CI 狀態 → 一律停(DIR-001 明文,不在預先授權內)。本機九步閘全綠,
**但本機綠不能當作 merge 的依據**。

續作:等 CI 恢復後 `gh run rerun` 或推一個新 commit,綠了再 merge。

## 下一棒要知道的事

- repo 已 public,舊名 `kamira/skill-write` 由 GitHub 轉址;marketplace id 也一併改名
- `core.hooksPath` 已指向 `.githooks/`,push 前會自動跑 `.github/ci_local.sh`;新機器要先跑 `scripts/install-hooks.sh`
- **本 repo 現在有 23 支 skill / 21 個 plugin / 4 份規則檔**。前門 + 引擎分層:
  前門管觸發與寫作指引,引擎管判定;前門的 plugin 會把引擎一起打包。舊說明(四支):`writing`(評論)、`fiction`(小說)、`techdoc`(規格書+架構說明)、`bizdoc`(公文+新聞稿)。
  拆分判準見 knowledge 的 **KN-003**:硬規則相反才拆,只差結構的用旗標,規格薄的先不拆
- 使用者定調:**different write should be different skill**,收斂為 KN-003
- **可拆的文體已用完**:剩下 9 個的核心指標都是修辭比例,量不出來,現在拆會生空頭規則(見 `docs/genres.md` 的難點欄)
- **治理規則本身也要有斷言**(KN-001 已擴及):`scripts/chg_diagram_gate.py` 管住
  「中/高風險 CHG 要有設計圖」。加新治理規則時,順手問它有沒有對應的閘

<!-- autopilot:begin -->
branch/role/scope: autopilot / CHG-20260810-08
doing: CHG-20260810-08 全 7 task 完成,已驗收(ACC-20260810-06)
next: 開 PR;**CI 自 11:36 起未再啟動**,merge 閘可能仍是停的
last-updated: 2026-08-10 13:30 (UTC+0)
<!-- autopilot:end -->
