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
| `skills/techdoc/` | 技術文件 skill(規格書 + 架構說明):techdoc_check.py,以 `--kind` 切結構規則 |
| `plugins/*/` | 可安裝的 plugin(skill 副本為生成物) |
| `scripts/` | 治理腳本:`install-hooks.sh`、`chg_diagram_gate.py` |
| `docs/genres.md` | 文體對照表:哪些已是 skill,哪些還沒有任何機器在把關 |
| `docs/writing/` | 帳本(CHG / ACC)+ 知識庫 |
| `tools/` | 隨身治理工具,來自 `kamira/skill-ai-sdlc-autopilot` |

## 什麼時候拆成兩支 skill

判準是**硬規則互不互斥**,不是文體名字不同:

1. **硬規則相反 → 拆。** `writing` 要求第一人稱、禁短句收尾、限制刻意句配額,三條對小說全是反的(第三人稱限知是主流視角、斷頭台法則要的就是戛然而止、武打段落要的就是密集對偶)。共用會誤殺。
2. **只差結構 → 一支 + 旗標。** 規格書與架構說明的硬規則完全相同(修辭趨近零、禁模糊形容詞),差別只在編號條列 vs 圖文互補,所以是 `techdoc --kind spec|arch`。
3. **規格薄到落不成斷言 → 先不拆。** 用四五行的規格生一個 skill,產出的是空頭規則。

完整判準見 knowledge 的 KN-003。

## 尚未實作

散文、詩歌、劇本、記敘文、抒情文、說明文、公文與新聞稿、賦駢文、史傳奏啟。各自的規格、成語比例與**難點**見 [`docs/genres.md`](docs/genres.md)——那一欄就是挑下一支的依據。

## 授權

MIT(見 `LICENSE`)。
