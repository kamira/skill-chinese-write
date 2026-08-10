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

## 下一棒要知道的事

- repo 已 public,舊名 `kamira/skill-write` 由 GitHub 轉址;marketplace id 也一併改名
- `core.hooksPath` 已指向 `.githooks/`,push 前會自動跑 `.github/ci_local.sh`;新機器要先跑 `scripts/install-hooks.sh`
- **本 repo 現在有三支 skill**:`writing`(評論)、`fiction`(小說)、`techdoc`(規格書+架構說明)。
  拆分判準見 knowledge 的 **KN-003**:硬規則相反才拆,只差結構的用旗標,規格薄的先不拆
- 使用者定調:**different write should be different skill**。下一支要拆哪個文體,
  依 `docs/genres.md` 的「難點」欄判斷——規格厚到能落成斷言的才值得拆

<!-- autopilot:begin -->
branch/role/scope: autopilot / CHG-20260810-04
doing: CHG-20260810-04 全 7 task 完成,已驗收(ACC-20260810-03)
next: 開 PR → CI 綠 → merge;下一支文體依 docs/genres.md 的難點欄挑
last-updated: 2026-08-10 10:30 (UTC+0)
<!-- autopilot:end -->
