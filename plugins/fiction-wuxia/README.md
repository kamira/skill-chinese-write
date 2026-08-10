# fiction-wuxia

中文武俠 / 仙俠小說寫作技能(繁中)。當使用者要寫武俠、仙俠、修真、江湖故事、武打場面、門派恩怨時使用。 這是 `fiction` 小說主層的**子層**:主層的技術規範(換人說話就獨立成段、段落字數上限、 擬聲詞改用強動詞、分章與切章點)全部適用,本支再加上這個流派特有的配比—— 修辭比例中高 30%-40%、成語密度8-14 次/千字,全流派最高,以及成語該落在哪些段落。 交稿前跑主層的 lint 並帶上 `--genre wuxia`。 **不要拿 writing skill 的評論規則套小說**——那支要求第一人稱、禁短句收尾、限制刻意句, 三條對小說都是反的。

本 plugin 同時帶入 `fiction` 引擎(判定邏輯所在),因此裝了就跑得動 lint。

```
/plugin marketplace add kamira/skill-chinese-write
/plugin install fiction-wuxia
```

完整規範見 `skills/fiction-wuxia/SKILL.md`。各文體的拆分判準見 knowledge 的 KN-003。
