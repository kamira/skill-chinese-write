# skill-chinese-write

`writing` 的獨立 repo:繁體中文寫作技能。目前只做**評論文章**——
第一人稱、口語、句長與段落刻意參差、刻意句(對稱/反差/明喻)限量,
禁 AI 腔與公文腔與句型殼。能寫也能改稿(去 AI 味,保存優先:不編造、不換作者的判斷)。

從 [`kamira/ai-skills`](https://github.com/kamira/ai-skills) 拆出,獨立治理與編輯。

## 安裝

```
/plugin marketplace add kamira/skill-chinese-write
/plugin install writing
```

舊名 `kamira/skill-write` 於 2026-08-10 改為現名。GitHub 會轉址,但 **marketplace id 也一起改了**——
先前用舊名加過的人要移除再重加一次;plugin 本身仍叫 `writing`,不受影響。

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
| `skills/writing/` | 評論 skill(單一真相):SKILL.md、四份 references、style_check.py、規則表與 fixture |
| `skills/fiction/` | 小說 skill:SKILL.md、三份 references、fiction_check.py、規則表與 fixture |
| `plugins/writing/`、`plugins/fiction/` | 可安裝的 plugin(skill 副本為生成物) |
| `docs/genres.md` | 文體對照表:哪些已是 skill,哪些還沒有任何機器在把關 |
| `docs/writing/` | 帳本(CHG / ACC)+ 知識庫 |
| `tools/` | 隨身治理工具,來自 `kamira/skill-ai-sdlc-autopilot` |

## 一種文體,一支 skill

不是為了整齊,是因為硬規則會互相誤殺:`writing` 要求第一人稱、禁止短句收尾、限制刻意句配額——三條對小說全是反的(第三人稱限知是主流視角、斷頭台法則要的就是短句戛然而止、武打段落要的就是密集對偶)。

## 尚未實作

散文、詩歌、劇本、技術文件、公文、古典文體。各自的規格與難點見 [`docs/genres.md`](docs/genres.md)。

## 授權

MIT(見 `LICENSE`)。
