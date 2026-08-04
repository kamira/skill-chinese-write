# skill-write

`writing` 的獨立 repo:繁體中文寫作技能。目前只做**評論文章**——
第一人稱、口語、句長與段落刻意參差、刻意句(對稱/反差/明喻)限量,
禁 AI 腔與公文腔與句型殼。能寫也能改稿(去 AI 味,保存優先:不編造、不換作者的判斷)。

從 [`kamira/ai-skills`](https://github.com/kamira/ai-skills) 拆出,獨立治理與編輯。

## 安裝

```
/plugin marketplace add kamira/skill-write
/plugin install writing
```

## 規則是可跑的 lint,不是散文建議

```
python3 skills/writing/scripts/style_check.py <你的稿子.md>
```

硬性違規 exit 1。規則表在 `skills/writing/assets/style_rules.json`。

改了規則就要動 fixture:`sample-good.md` / `sample-issue.md` 必須過,
`sample-bad.md` 必須被擋。CI 兩個方向都驗——只驗「跑得動」等於沒驗。

## 這個 repo 有什麼

| 路徑 | 內容 |
|------|------|
| `skills/writing/` | skill 本體(單一真相):SKILL.md、四份 references、style_check.py、規則表與 fixture |
| `plugins/writing/` | 可安裝的 plugin(skill 副本為生成物) |
| `docs/writing/` | 帳本(CHG / ACC)+ 知識庫 |
| `tools/` | 隨身治理工具,來自 `kamira/skill-ai-sdlc-autopilot` |

## 尚未實作

小說與散文。SKILL.md 只涵蓋評論文章。

## 授權

MIT(見 `LICENSE`)。
