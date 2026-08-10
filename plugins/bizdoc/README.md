# bizdoc — 公文與新聞稿

繁體中文的公務與商務應用文。管的是**規格化**:固定欄位、固定格式、沒有個人情緒。

```
/plugin marketplace add kamira/skill-chinese-write
/plugin install bizdoc
```

## 三條硬規範(兩種 kind 都適用)

1. **禁情緒詞**——令人震驚、深感痛心、可喜可賀、怵目驚心
2. **禁情感修辭**——譬喻全禁(像⋯一樣、彷彿、宛如);**結構排比不禁**
3. **開門見山有上限**——公文主旨、新聞稿導語都不超過 150 字

| | `--kind gov` | `--kind press` |
|---|---|---|
| 硬性 | 缺「主旨:」→ 擋;主旨過長 → 擋 | 導語過長 → 擋 |
| 警告 | 主旨沒有公文動詞 | 導語沒有數字或日期 |

```
python3 skills/bizdoc/scripts/bizdoc_check.py 公文.md --kind gov
python3 skills/bizdoc/scripts/bizdoc_check.py 新聞稿.md --kind press
```

## 絕對不要跟 writing 混用

`writing` 把「制度」「窗口」「予以」整類公文腔列為**硬性違規**,而公文要的正是那套固定行文。四條規則裡有四條相反,拿 writing 的 lint 去量公文會滿江紅,而且每一條都是錯的。
