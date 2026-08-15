# 文體對照表 — 哪些已經是 skill,哪些還不是

本 repo 的立場是**不同文體就是不同 skill**:評論靠論證推進、小說靠場景與人物推進,它們的硬規則會互相誤殺(具體例子見 `skills/fiction/SKILL.md` 的對照)。

這份表是骨架,用途有二:決定下一支要拆哪個文體;以及讓人一眼看出**哪些文體目前沒有任何機器在把關**。

## 23 支 skill,依家族分組

判準見 knowledge 的 **KN-003**:**拆不拆看觸發面**(使用者會不會用這個名字找它),**規則檔共不共用看硬規則是否互斥**。

### 不屬於任何文體的引擎

| 規則 | skill | lint |
|------|-------|------|
| 中文正字法(半形標點)+ 收尾(總結殼、光禿短句) | `zh-style` | `zh_style_check.py` |

`zh-style` 沒有前門也沒有 plugin——沒有人會說「幫我寫一篇正字法」。它由**所有 plugin 全部打包**,因為它的兩條規則在每個文體的判定完全相同。

### 有自己引擎的(硬規則與其他文體互斥)

| 文體 | skill | lint |
|------|-------|------|
| 評論、議論文、專欄、影評書評 | `writing` | `style_check.py` |
| 小說主層(對話、分段、分章) | `fiction` | `fiction_check.py` |
| 技術文件(引擎,不單獨安裝) | `techdoc` | `techdoc_check.py` |
| 商務公務文(引擎,不單獨安裝) | `bizdoc` | `bizdoc_check.py` |

### 指回引擎的前門(硬規則與引擎相同,只差配比或結構)

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

## 兩個要記住的衝突

1. **`writing` 與議論文的成語規範不一致。** `chinese.md` 說議論文的成語比例高(25%-35%),`writing` 的立場則是禁 AI 腔與空心評價、限制刻意句。這不是誰對誰錯——`writing` 服務的是「讀起來像有人在講話」的現代網路評論,不是傳統論說文。要收 `chinese.md` 的議論文規格,得先決定改哪一邊,不能兩份規則並存。
2. **賦/駢文與 `writing` 是正面衝突。** 一個要密集對偶,一個把對稱句列為配額制。這正是「不同文體要不同 skill」最乾淨的例子。
