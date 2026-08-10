# architecture

中文架構說明 / 設計文件寫作技能(繁中)。當使用者要寫架構說明、系統設計文件、技術選型文件、模組關係說明時使用。 修辭比例極低(0%-2%),僅允許類比。規則不是散文建議而是可跑的 lint——判定邏輯在 `techdoc` 引擎, 交稿前跑 `techdoc_check.py --kind arch`(安裝本 plugin 時引擎會一起帶進來)。 **不要拿 writing 或 fiction 的規則套這個文體**——那兩支要的修辭密度在這裡全是違規。

本 plugin 同時帶入 `techdoc` 引擎(判定邏輯所在),因此裝了就跑得動 lint。

```
/plugin marketplace add kamira/skill-chinese-write
/plugin install architecture
```

完整規範見 `skills/architecture/SKILL.md`。各文體的拆分判準見 knowledge 的 KN-003。
