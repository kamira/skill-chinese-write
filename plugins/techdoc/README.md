# techdoc — 中文技術文件

規格書與架構說明。管的是**讀的人不必猜**:每個形容詞背後有沒有數字,每個模組關係有沒有圖。

```
/plugin marketplace add kamira/skill-chinese-write
/plugin install techdoc
```

## 三條硬規範(兩種 kind 都適用)

1. **模糊形容詞一律換成具體數據**——快速、良好、適當、盡量、大幅、顯著。「快速回應」沒有意義,「P95 < 200ms」才有:差別在驗收那天指得出來還是各說各話。
2. **禁誇張與情緒詞**——非常、完美、革命性、驚人。
3. **修辭配額**:規格書 0 處;架構說明 2 處,且只用於把抽象架構類比成已知實物。

## 各自的結構規範

| | `--kind spec` | `--kind arch` |
|---|---|---|
| 硬性 | 修辭 0 處 | **沒有任何圖 → 擋** |
| 警告 | 缺模組化編號;絕對動詞比例低於 30% | 缺權衡/取捨段落 |

```
python3 skills/techdoc/scripts/techdoc_check.py 規格.md --kind spec
python3 skills/techdoc/scripts/techdoc_check.py 架構.md --kind arch
```

## 為什麼兩種文件是同一支

拆 skill 的判準是**硬規則互不互斥**,不是文體名字不同。規格書與架構說明的硬規則完全相同,只差結構;硬規則相反的文體(如評論 vs 小說)才拆成兩支。
