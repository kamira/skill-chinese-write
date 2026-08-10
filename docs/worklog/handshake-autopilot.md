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

## 目前停在哪(2026-08-10 08:35 UTC+0)

**CHG-20260810-01 停在 merge 閘前。** PR #1 已開、本機驗收全綠,但 GitHub Actions
**沒有啟動**——`The job was not started because recent account payments have failed`。
帳務問題,與程式碼無關。

merge 是單向門,這道閘 fail-closed:CI 判定不出狀態一律停(DIR-001 明載,不在預先授權內)。

續作點二選一:

1. 修好 GitHub 帳務 → `gh run rerun 31370062149` → 綠了再 merge
2. 使用者明示放行(等同 `--allow-no-ci`),以本機 `.github/verify.sh` 全綠為據 merge

<!-- autopilot:begin -->
branch/role/scope: autopilot / CHG-20260810-01
doing: CHG-20260810-01 已 commit + PR #1,停在 merge 閘
next: 等 CI 可用或使用者放行;merge 後刪 branch
last-updated: 2026-08-10 08:35 (UTC+0)
<!-- autopilot:end -->
