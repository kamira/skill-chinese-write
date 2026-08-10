# THIRD-PARTY NOTICES — techdoc

---

## stephenturner/skill-deslop — MIT License

Copyright (c) Stephen Turner

https://github.com/stephenturner/skill-deslop

**採用**:`SKILL.md`「lint 之後:自己問五件事」的**形式**——五個維度各 1–10 分、以總分 35 為門檻,與本 repo 的 `writing`、`fiction` 兩個 plugin 同源,改編自該專案的評分量表。

**差異**:維度名稱與定義為本 skill 自訂(可驗收 / 可引用 / 邊界 / 為什麼 / 失效),針對繁中技術文件設計。

---

## 使用者提供的 `chinese.md`

本 skill 的規範內容來自 repo 擁有者提供的中文文體指南(第一部分「技術與工程應用文體」的規格書與架構說明兩節),非公開第三方作品,由擁有者授權使用。

**與原文的差異(明列)**:

1. **成語比例改為文學性成語密度。** 原文給「趨近於 0%」「1%-3%」等百分比但未定義分母。本 skill 改用可計算的「文學性成語次數/千字」(上限 1),並另立約 28 條的小表——沿用 `fiction` 那份 140 條的全成語表會把「一氣呵成」以外的中性用語也算進來,判準會失焦。
2. **絕對動詞刻意不收單字的「應」與「需」。** 原文列的絕對動詞包含「應」,但中文沒有詞界,子字串比對會讓「回應時間」「需求」都算成絕對動詞,把比例灌水成假的通過。只收無歧義的多字動詞。
3. **架構說明「缺圖」升級為硬性違規。** 原文把「圖文互補」列為核心手法,未言明強制。本 skill 列硬性,理由與 ai-sdlc 的設計圖規則同源:讀不了的確認材料換不到確認。提供 `--allow-no-diagram` 逃生口,且放行會被印在報表上。

---

## 本 skill 自身

`techdoc` 的 SKILL.md、兩份 references、`assets/techdoc_rules.json`、`scripts/techdoc_check.py` 與三份樣稿,除上述具名部分外均為本 repo 原創,授權依 repo 根目錄的授權條款。
