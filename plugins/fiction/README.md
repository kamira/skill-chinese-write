# fiction — 中文小說寫作

繁體中文小說。管的是**小說怎麼被讀進去**:對話怎麼排、段落多長、章在哪裡切。

```
/plugin marketplace add kamira/skill-chinese-write
/plugin install fiction
```

## 四條硬規範(lint 會擋)

1. 換人說話就獨立成段——同段最多兩處引號
2. 段落字數上限:實體出版 150 字;網路連載 80 字且不超過 3 行
3. 擬聲詞樣板「轟隆!」一聲 → 改用強動詞:悶雷滾過天際
4. 擬聲詞每千字不超過 3 次

```
python3 skills/fiction/scripts/fiction_check.py 稿件.md --genre wuxia --mode web
```

## 四條靠人判斷(明說沒有斷言)

斷頭台切章點、心理活動獨立成段、留白與伏筆、各流派的修辭比例。寫成規則的樣子卻沒有人執行,比沒有規則更糟。

## 不要跟 writing 混用

`writing` 管評論,它要求第一人稱、禁止短句收尾、限制刻意句配額——三條對小說全是反的。兩支是不同的 skill,不是同一支的兩個模式。
