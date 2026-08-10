# press

中文新聞稿寫作技能(繁中)。當使用者要寫新聞稿、媒體聲明、對外公告、記者會稿時使用。 修辭比例趨近於零(0%-5%)。規則不是散文建議而是可跑的 lint——判定邏輯在 `bizdoc` 引擎, 交稿前跑 `bizdoc_check.py --kind press`(安裝本 plugin 時引擎會一起帶進來)。 **不要拿 writing 或 fiction 的規則套這個文體**——那兩支要的修辭密度在這裡全是違規。

本 plugin 同時帶入 `bizdoc` 引擎(判定邏輯所在),因此裝了就跑得動 lint。

```
/plugin marketplace add kamira/skill-chinese-write
/plugin install press
```

完整規範見 `skills/press/SKILL.md`。各文體的拆分判準見 knowledge 的 KN-003。
