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
| `skills/` | **24 支 skill**:5 支引擎(writing / fiction / techdoc / bizdoc + 跨文體的 zh-style)+ 19 支前門。分組見 [`docs/genres.md`](docs/genres.md) |
| `plugins/*/` | 21 個可安裝的 plugin(skill 副本為生成物;前門會把引擎一起打包) |
| `scripts/` | 治理腳本:install-hooks、chg_diagram_gate、skill_inventory_check |
| `docs/genres.md` | 文體對照表:誰有 lint、誰明標沒有 lint、為什麼 |
| `docs/writing/` | 帳本(CHG / ACC)+ 知識庫 |
| `tools/` | 隨身治理工具,來自 `kamira/skill-ai-sdlc-autopilot` |

## 一個文體一支 skill,但規則檔只有四份

判準分兩層(knowledge KN-003):

1. **拆不拆看觸發面。** 使用者會說「幫我寫一篇武俠」,所以武俠要有自己的 skill——skill 的第一個功能是**被找到**。
2. **規則檔共不共用看硬規則。** 武俠與科幻的硬規則相同(只差配比),共用 `fiction` 引擎;`writing` 與 `fiction` 的硬規則相反(第一人稱、結尾、刻意句三條全反),各自一份。

所以是 **24 支 skill、5 份規則檔**。其中 `zh-style` 是第三種情況:**規則不隨文體改變**(半形標點在散文與公文裡一樣是錯),所以它是共用引擎,由 21 個 plugin 全部打包。前門的 plugin 會把引擎一起打包,裝了就跑得動。

沒有任何可判定規則的文體(散文、詩歌、戲劇⋯)一樣有 skill,但 SKILL.md **明標「本支沒有 lint,規則靠人判斷」**——假裝有斷言比沒有更糟。

## 尚未有 lint 的文體

散文、詩歌、戲劇、記敘文、抒情文、說明文、賦駢文、史傳奏啟、企劃書——**它們都有 skill**,但沒有斷言,各自的 SKILL.md 寫明原因。見 [`docs/genres.md`](docs/genres.md)。

其中 `fu`(賦/駢文)最有機會補上:四六句對偶是字數對稱,恰好可判——但那份規則會與 `writing` 的對稱句配額完全相反,必須是獨立引擎。

## 授權

MIT(見 `LICENSE`)。
