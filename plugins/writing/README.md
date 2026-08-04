# writing — 中文寫作

讓 AI 寫出來的中文,讀起來像有人在講話,不像報告在自我介紹。

**目前只做一種文體:評論文章**(時事評論、觀點文、專欄、影評書評、現象評論)。小說與散文**未實作**——SKILL.md 明文要求模型直說沒有,不要拿評論的框架套上去假裝。

兩種工作都吃:**從零寫**一篇評論,或**接手改稿**把已經寫好的文章去掉 AI 味。兩者判準相反——寫作要有角度、敢講死;改稿保存優先,不編造、不換作者的判斷。

## 安裝(Claude Code)

```
/plugin marketplace add kamira/ai-skills
/plugin install writing@ai-skills
```

## 五條不可退讓

1. 第一人稱,用「我」——不用「筆者」、不用「本文」
2. 口語:唸出來像唸公文就重寫
3. 句長刻意參差,不要每句十五到二十字
4. 對稱句全篇最多三處,只放在真要敲一下的地方
5. 禁 AI 腔與公文腔(「制度」「窗口」「值得注意的是」「綜上所述」「賦能」⋯⋯)

## 內容物

| 元件 | 路徑 | 說明 |
|------|------|------|
| SKILL.md | `skills/writing/` | 文體派工(評論/議題型)+ 六條下限 + lint 入口(複本;單一真相在 repo 頂層 `skills/`) |
| references ×4 | `skills/writing/references/` | `commentary`(評論骨架:切入/主張/證據/讓步/收尾)、`voice`(第一人稱、句長與段落節奏、對稱句配額)、`ai-tells`(禁用詞、句型殼、助理路標 + 陸味→台灣用語)、`revise`(改稿:保存優先、掃描順序、何時該留著殼) |
| 規則單一真相 | `skills/writing/assets/style_rules.json` | hard/soft 詞表、節奏門檻、配額。加詞調門檻改這份,不要改腳本 |
| 風格 lint | `skills/writing/scripts/style_check.py` | 硬性違規 → exit 1;節奏/對稱/軟限 → 警告 |
| 對照樣稿 | `skills/writing/assets/sample-{good,bad}.md` | 一篇過、一篇滿江紅,兼作迴歸夾具 |
| 議題型範例 | `skills/writing/assets/sample-issue{,-en}.md` | 分節寫法(現象/省思/結語/後記)的繁中示範 + 英文對照範例(**lint 不支援英文**) |

## 為什麼要有 lint

風格規則寫成散文,實務上不會被執行(本 repo 的 `docs/ai-sdlc/knowledge` KN-001)。所以「句長要參差」落成句長變異係數門檻,「對稱句只用在零星重點」落成全篇三處的配額,「不要太 AI」落成一張命中即擋的詞表。

```
python3 skills/writing/scripts/style_check.py 稿件.md
python3 skills/writing/scripts/style_check.py 稿件.md --allow 制度   # 引用原文才個案放行
python3 skills/writing/scripts/style_check.py 稿件.md --json
```

退出碼:`0` 過(可能有警告)/ `1` 有硬性違規 / `2` 環境或參數錯誤。

lint 過了不等於文章好——它擋得住「像機器寫的」,擋不住「無聊」。

## 出處

v1.1.0 的句型殼與改稿方向參考了 `stephenturner/skill-deslop`(MIT)與 `B1lli/remove-ai-flavor-writing-skill`(MIT);`theclaymethod/unslop` 因無授權聲明,其內容一律未採用。逐項的採用範圍與差異見 [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md)。

## 治理

變更記錄在 `docs/writing/`(CHG / ACC / CHANGELOG / knowledge),流程走 `ai-sdlc`。
