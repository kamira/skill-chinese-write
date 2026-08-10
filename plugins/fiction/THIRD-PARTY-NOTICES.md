# THIRD-PARTY NOTICES — fiction

---

## stephenturner/skill-deslop — MIT License

Copyright (c) Stephen Turner

https://github.com/stephenturner/skill-deslop

**採用**:`SKILL.md`「lint 之後:自己問五件事」的**形式**——五個維度各 1–10 分、以總分 35 為門檻,與 `writing` plugin 同源,改編自該專案的評分量表。

**差異**:維度名稱與定義為本 skill 自訂(推進 / 人物 / 具體 / 懸念 / 克制),針對繁中小說設計;原專案的維度、其 `references/` 內容與英文語料規則均未採用。

---

## 使用者提供的 `chinese.md`

本 skill 的規範內容來自 repo 擁有者提供的中文文體指南(第二部分「各類型小說深度寫作指南」與第三部分「小說技術規範」),非公開第三方作品,由擁有者授權使用。

**與原文的差異(明列)**:

1. **修辭比例未實作為斷言**。原文給各流派 15%-45% 不等的修辭比例,但沒有程式量得出一段文字有幾成是譬喻。這些數字保留在 `references/genres.md` 作為手感校準,並明標靠人判斷。
2. **成語比例改為自訂密度指標**。原文的百分比未定義分母,故不冒充實作;改用「成語次數/千字」,區間依原文各流派的相對高低自訂。
3. **純對話輪數門檻放寬一級**。原文寫「超過 3 輪必須插入人名」,但其自身示範正好是 4 輪;門檻設在 5 輪才報,避免規格的示範被自己的規則判違規。

---

## 本 skill 自身

`fiction` 的 SKILL.md、三份 references、`assets/fiction_rules.json`、`scripts/fiction_check.py` 與樣稿,除上述具名部分外均為本 repo 原創,授權依 repo 根目錄的授權條款。
