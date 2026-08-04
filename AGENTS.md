# AGENTS.md — AI entry point(任何 agent、任何廠商 / any agent, any vendor)

本 repo 只收 **writing** 這一個 plugin。治理記錄在 `docs/writing/` 底下。

1. **動任何東西之前必讀**:`skills/writing/SKILL.md` → `docs/writing/CHANGELOG.md` →
   `docs/writing/knowledge/`(讀 INDEX)→ `docs/writing/changes/`(未收尾 CHG 先處理)。
2. **規則不是散文建議,是可跑的 lint**:`skills/writing/scripts/style_check.py`
   讀 `assets/style_rules.json`。動了規則就要動 fixture:
   `sample-good.md` / `sample-issue.md` 必須過,`sample-bad.md` 必須被擋——
   只驗「跑得動」等於沒驗。
3. **不可協商**:任何修改先開 CHG(`docs/writing/changes/CHG-YYYYMMDD-NN.md`)再動手;
   commit 帶 CHG 編號;同輪產出 ACC;時間一律 UTC+0。
4. **治理工具是隨身副本**:`tools/` 底下四支來自 `kamira/skill-ai-sdlc-autopilot`。
   **不要就地改**——改了 `tools/tools_drift_check.py` 會紅。要改就送回上游再同步下來。
