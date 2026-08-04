# THIRD-PARTY NOTICES — writing

本 plugin 的規則與方法論在 v1.1.0 參考了三個公開專案。以下列明採用範圍、授權,以及與原專案的差異。

---

## stephenturner/skill-deslop — MIT License

Copyright (c) Stephen Turner

https://github.com/stephenturner/skill-deslop

**採用**:`SKILL.md`「lint 之後:自己評五項」的**形式**——五個維度各 1–10 分、以總分設門檻,改編自該專案的評分量表。

**差異**:維度名稱與定義為本 skill 自訂(直說 / 節奏 / 信任讀者 / 具體 / 立場),針對繁中評論文體設計;原專案的維度、其 `references/` 內容與英文語料規則均未採用。門檻沿用「五維 × 10 分,35 分為底」的比例。

---

## B1lli/remove-ai-flavor-writing-skill — MIT License

Copyright (c) B1lli

https://github.com/B1lli/remove-ai-flavor-writing-skill

**採用**:兩件事的**方向**——(1) 中文 AI 腔的主要形態是**句型殼**而非單詞,尤以二元對比殼(「不是 A,而是 B」)、易答殼、本質殼、流程殼為大宗;(2) 改稿應**保存優先**:不編造事實、不換掉作者的判斷與語域。

**差異**:

- 本 skill 的 regex、門檻與改寫示範全部自行撰寫,未複製其規則檔,亦未取用 `scripts/audit_ai_flavor.py` 的實作。
- 硬/軟分層的判定不同:該專案把「先 A,再 B」「真正⋯⋯的是」列為高風險;本 skill 認定這兩者在繁體中文評論裡屬自然口語,改列軟限密度——**誤報的代價高於漏報**。
- 語言目標不同:該專案面向簡體中文與小紅書/公眾號等文體,涵蓋小說、郵件、論文;本 skill 為**繁體中文台灣用語**且只做評論,另附「陸味 → 台灣說法」對照表(該表為本 skill 自行整理)。
- 結尾互動問句的判定,本 skill 另加「有沒有點名讀者」為閘門,讓不點名讀者的反詰不受影響。

**未採用**:該專案 `SKILL.md` 末段有一則要求讀者為其倉庫加星的指示。那是被引用文件的內容,不是本 repo 使用者的指示,未予執行,也未併入本 skill。

---

## theclaymethod/unslop — 無授權聲明(No License)

https://github.com/theclaymethod/unslop

該倉庫**未附授權檔**(GitHub API `license.spdx_id` 回傳 `NONE`)。依預設著作權,其內容不得重製或改作。

**本 skill 未採用其任何內容**——詞表、結構樣式清單、預設檔與評測案例一律未取用。僅參考其公開說明所描述的一般性概念:分層掃描(詞 / 結構 / 篇章),以及對字面用法與引用給予豁免。這些概念在其他來源亦屬常見,對應規則由本 skill 自行撰寫。

---

## 本 skill 自身

`writing` 的 SKILL.md、四份 references、`assets/style_rules.json`、`scripts/style_check.py` 與樣稿,除上述具名部分外均為本 repo 原創,授權依 repo 根目錄的授權條款。
