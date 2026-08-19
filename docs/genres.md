# 文體對照表 — 哪些已經是 skill,哪些還不是

本 repo 的立場是**不同文體就是不同 skill**:評論靠論證推進、小說靠場景與人物推進,它們的硬規則會互相誤殺(具體例子見 `skills/fiction/SKILL.md` 的對照)。

這份表是骨架,用途有二:決定下一支要拆哪個文體;以及讓人一眼看出**哪些文體目前沒有任何機器在把關**。

## 全部 skill,依家族分組

判準見 knowledge 的 **KN-003**:**拆不拆看觸發面**(使用者會不會用這個名字找它),**規則檔共不共用看硬規則是否互斥**。

### 不屬於任何文體的引擎

<!-- genres-table:universal -->
| 規則 | skill | lint |
|------|-------|------|
| 中文正字法(半形標點)+ 收尾(總結殼、光禿短句) | `zh-style` | `zh_style_check.py` |

`zh-style` 沒有前門也沒有 plugin——沒有人會說「幫我寫一篇正字法」。它由**所有 plugin 全部打包**,因為它的兩條規則在每個文體的判定完全相同。

### 有自己引擎的(硬規則與其他文體互斥)

<!-- genres-table:engine -->
| 文體 | skill | lint |
|------|-------|------|
| 評論、議論文、專欄、影評書評 | `writing` | `style_check.py` |
| 小說主層(對話、分段、分章) | `fiction` | `fiction_check.py` |
| 技術文件(引擎,不單獨安裝) | `techdoc` | `techdoc_check.py` |
| 近體詩(絕句・律詩) | `regulated-verse` | `verse_check.py` |
| 詞(宋詞) | `ci-poetry` | `ci_check.py` |
| 商務公務文(引擎,不單獨安裝) | `bizdoc` | `bizdoc_check.py` |

### 指回引擎的前門(硬規則與引擎相同,只差配比或結構)

<!-- genres-table:frontdoor -->
| 文體 | skill | 跑什麼 |
|------|-------|--------|
| 微型小說 | `/fiction:fiction-flash` | `fiction_check.py --genre flash` |
| 中／長篇 | `/fiction:fiction-long` | `fiction_check.py --genre long` |
| 武俠 / 仙俠 | `/fiction:fiction-wuxia` | `fiction_check.py --genre wuxia` |
| 科幻 | `/fiction:fiction-scifi` | `fiction_check.py --genre scifi` |
| 懸疑 / 推理 / 驚悚 | `/fiction:fiction-mystery` | `fiction_check.py --genre mystery` |
| 言情 / 都市愛情 | `/fiction:fiction-romance` | `fiction_check.py --genre romance` |
| 規格書 | `spec` | `techdoc_check.py --kind spec` |
| 架構說明 / 設計文件 | `architecture` | `--kind arch` |
| 公文(函、簽、通知、公告) | `official` | `bizdoc_check.py --kind gov` |
| 新聞稿 / 對外聲明 | `press` | `--kind press` |

每個前門的 plugin 都把引擎一起打包,裝了就跑得動。
六支小說流派已於 `CHG-20260814-10` 從獨立 skill 退役,前門改為 `fiction` plugin 底下的命令。

### 明標「本支沒有 lint」的前門

這些文體的核心指標是修辭比例,而沒有程式量得出一段文字有幾成是譬喻。它們有完整的寫作指引,但**沒有任何斷言**,SKILL.md 各自寫明原因——這是 KN-001 的第二條路,不是空頭規則。

<!-- genres-table:nolint -->
| 文體 | skill | 為什麼沒有 lint |
|------|-------|----------------|
| 散文 | `prose` | 核心指標是修辭比例 40%-50%,量不出來 |
| 詩歌 | `poetry` | 手法之一是「打破常規語法」,與 lint 的前提直接衝突 |
| 戲劇 / 劇本 | `drama` | 成語密度依角色而非依全劇;潛台詞的定義就是沒寫出來的那一層 |
| 記敘文 | `narrative` | 六要素齊不齊、敘事順序對不對,都要理解文意 |
| 抒情文 / 心得 | `lyric` | 修辭比例橫跨 20%-60%,本身就不是一個門檻 |
| 說明文 | `exposition` | 「有沒有列數據」勉強可判,但那只是四個手法之一 |
| 賦 / 駢文 | `fu` | 四六句對偶**恰好可判**,但那份規則會與 `writing` 完全相反,必須是獨立引擎。尚未建 |
| 史傳 / 奏啟 | `historiography` | 核心手法「婉曲」的定義就是不直說 |
| 企劃書 | `proposal` | `chinese.md` 只給了「規格化與標準化」一句,規格來源太薄,不憑空發明 |

### 這些 skill 怎麼被打包(CHG-20260816-03)

它們**各自仍是獨立 skill**,description 一字未改,自動觸發不受影響。改變的只是打包。
**本表列出全部 plugin**,而不只是 `CHG-20260816-03` 新分組的那四個——
只列一部分的表沒有可判定的不變量:`[8b/19]` 要比的是「表 == 登記簿」,
而子集比對會讓「表上多一列 / 少一列 / 成分欄空著」三種都不紅(審議席實測)。
`zh-style` 由每個 plugin 全部打包,是引擎不是文體,不列在成分欄。

<!-- genres-table:packaging -->
| plugin id | 中文名 | 打包的 skill |
|---|---|---|
| `architecture` | — | `architecture`、`techdoc` |
| `classical` | 文言 | `fu`、`historiography`、`regulated-verse`、`ci-poetry` |
| `composition` | 作文 | `prose`、`narrative`、`lyric`、`exposition`、`poetry` |
| `drama` | — | `drama`(自成一家,單成員合併收益為零) |
| `fiction` | — | `fiction` |
| `official` | — | `official`、`bizdoc` |
| `press` | — | `press`、`bizdoc` |
| `proposal` | — | `proposal`(歸屬另議:屬公文 / 新聞稿家族) |
| `spec` | — | `spec`、`techdoc` |
| `writing` | — | `writing` |

分組判準是**文體家族**(KN-003 第一層:使用者會用什麼名字找它),
不是「有沒有 lint」——後者是實作狀態的快照,而 `fu` 那一列自己就寫著
「四六句對偶恰好可判…尚未建」,以它分組的大類會在建 lint 那天自己解體。

**`poetry` 不進 `classical`**:它是**現代詩 / 新詩**(見其 SKILL.md),
不是文言韻文,而且沒有人會用「文言」去找新詩。這一段保留,因為它正好是
**`regulated-verse`(近體詩)與 `ci-poetry`(詞)的對照**——那兩支才是文言韻文,
而且都已在 `classical` 裡。

**`poetry` 歸 `composition`**:使用者裁示新詩「偏向藝術或作文」。兩席量過之後選作文——
「藝術」過不了駁回 `freeform` 的那把尺(沒有人說「幫我寫一篇藝術」),
而列舉式的「詩歌與劇本」只是文件標題,不能證成一個 plugin 家族:
**詩與劇本在中文文體分類裡是平級大類,兩者合起來沒有傳統類名。**
至於「散文體加分行詩會不會破壞一致性」,那是 KN-003 第二層(規則共用)的問題,
而 `composition` **不共用任何規則**,只做打包——分組只走第一層。

**`drama` 不另立 plugin**:單成員合併收益為零。

**近體詩與詞都已建成**,兩支都在 `classical`:

- `regulated-verse`(`CHG-20260817-01`)帶平水韻資產與 `verse_check.py`;
  判句式、韻腳同部與不重字、對句第二字平仄相對。
  黏、拗救、對仗的詞性語義**明標不判**。
- `ci-poetry`(`CHG-20260817-02`〜`-05`)帶詞林正韻 19 部與白香詞譜 100 調;
  判韻組同部與平仄。**句數/字數不符列未判定**(疑為本工具未收之體),
  同牌異體、換韻合法性、領字、去聲位**明標不判**。

`fu`(賦 / 駢文)仍是唯一帶對仗而沒有 lint 的一支。

**詞的資料量確實是近體詩的數十倍**——每個牌自有句式韻位,而韻走詞林正韻
(由平水韻 106 部合併為 19 部)。白香詞譜收 100 調,其中 85 調逐行對齊通過,
而**首發只啟用其中九個常用牌**——對齊通過是啟用的必要條件,不是充分條件。
其餘一律列「非本工具所收白香體/未判定」而不硬猜。殘留風險見 `backlog.md`。

`fu` 的 lint 不因本張解鎖:賦的四六句對偶是**字數對稱**問題,不需要聲韻資料,
它「尚未建」是排序問題而非資料問題;而駢文的平仄相對與近體詩的定格平仄是兩套規則。

**plugin id 用 ASCII 而非中文**,因為 git 的 `core.quotepath` 會把 CJK 路徑印成
八進位跳脫,版號閘與 catalog 閘兩端都取不到 blob、判成「沒變」——實測的 fail-open。
中文名放在 marketplace 的 description 裡。

## 兩個要記住的衝突

1. **`writing` 與議論文的成語規範不一致。** `chinese.md` 說議論文的成語比例高(25%-35%),`writing` 的立場則是禁 AI 腔與空心評價、限制刻意句。這不是誰對誰錯——`writing` 服務的是「讀起來像有人在講話」的現代網路評論,不是傳統論說文。要收 `chinese.md` 的議論文規格,得先決定改哪一邊,不能兩份規則並存。
2. **賦/駢文與 `writing` 是正面衝突。** 一個要密集對偶,一個把對稱句列為配額制。這正是「不同文體要不同 skill」最乾淨的例子。
