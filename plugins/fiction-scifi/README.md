# fiction-scifi

中文科幻小說寫作技能(繁中)。當使用者要寫科幻、未來題材、太空、AI、賽博龐克、硬科幻時使用。 這是 `fiction` 小說主層的**子層**:主層的技術規範(換人說話就獨立成段、段落字數上限、 擬聲詞改用強動詞、分章與切章點)全部適用,本支再加上這個流派特有的配比—— 修辭比例低 10%-15%、成語密度1-3 次/千字,以及成語該落在哪些段落。 交稿前跑主層的 lint 並帶上 `--genre scifi`。 **不要拿 writing skill 的評論規則套小說**——那支要求第一人稱、禁短句收尾、限制刻意句, 三條對小說都是反的。

本 plugin 同時帶入 `fiction` 引擎(判定邏輯所在),因此裝了就跑得動 lint。

```
/plugin marketplace add kamira/skill-chinese-write
/plugin install fiction-scifi
```

完整規範見 `skills/fiction-scifi/SKILL.md`。各文體的拆分判準見 knowledge 的 KN-003。
