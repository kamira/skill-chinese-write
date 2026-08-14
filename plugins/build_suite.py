#!/usr/bin/env python3
"""
build_suite.py — 同步 repo 頂層 skills/ 複本進各 plugin 的 skills/(建置產物)

單一真相在 skills/;plugin 內複本只由本腳本產生(冪等)。PLUGINS 對照表定義每個 plugin
打包哪些 skill。
用法:
  python3 plugins/build_suite.py           # 同步(回報新增/更新/刪除數)
  python3 plugins/build_suite.py --check   # 只比對:不同步 → exit 1(CI 用)
"""
from __future__ import annotations
import filecmp
import re
import shutil
import sys
from pathlib import Path

# 釘住輸出編碼(CHG-20260803-01 T1):不依賴主控台/locale 的 ambient 編碼。
# 非 UTF-8 主控台(如 Windows cp932)印 CJK/emoji 會 UnicodeEncodeError;
# 釘住後同一份程式在任何平台的輸出行為一致。errors="replace" 確保永不因輸出而崩潰。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "skills"
PLUGINS = {
    "writing": ('writing', 'zh-style'),
    "fiction": ('fiction', 'zh-style'),
    "fiction-flash": ('fiction-flash', 'fiction', 'zh-style'),
    "fiction-long": ('fiction-long', 'fiction', 'zh-style'),
    "fiction-wuxia": ('fiction-wuxia', 'fiction', 'zh-style'),
    "fiction-scifi": ('fiction-scifi', 'fiction', 'zh-style'),
    "fiction-mystery": ('fiction-mystery', 'fiction', 'zh-style'),
    "fiction-romance": ('fiction-romance', 'fiction', 'zh-style'),
    "spec": ('spec', 'techdoc', 'zh-style'),
    "architecture": ('architecture', 'techdoc', 'zh-style'),
    "official": ('official', 'bizdoc', 'zh-style'),
    "press": ('press', 'bizdoc', 'zh-style'),
    "proposal": ('proposal', 'zh-style'),
    "prose": ('prose', 'zh-style'),
    "poetry": ('poetry', 'zh-style'),
    "drama": ('drama', 'zh-style'),
    "narrative": ('narrative', 'zh-style'),
    "lyric": ('lyric', 'zh-style'),
    "exposition": ('exposition', 'zh-style'),
    "fu": ('fu', 'zh-style'),
    "historiography": ('historiography', 'zh-style'),
}
EXCLUDE = ("__pycache__", ".DS_Store")

# commands 的**單一登記簿**(CHG-20260814-03)。
# 來源在頂層 `commands/<檔名>.md`,plugin 內 `plugins/<p>/commands/` 是**建置產物**。
#
# 為什麼要有這張表而不是「整個 commands/ 全部複製到每個 plugin」:
# slash command 的呼叫面是 `/<plugin>:<命令>`,所以哪個 plugin 收哪幾個命令是**語意決定**,
# 不是複製規則。沒有這張表,就沒有名冊可以做反向比對——而反向正是上次出孤兒事故的方向
# (三道閘全是名冊→磁碟,不在名冊裡的東西誰都走不到)。
COMMANDS: dict[str, tuple[str, ...]] = {
    # 搬遷批才會填真的命令(CHG-20260814-03 只建機制,不搬內容)。
    # 目前為空 = 宣告「沒有任何 plugin 要打包 command」,反向斷言因此會擋下
    # 任何出現在頂層 commands/ 或 plugin 內 commands/ 的檔案。
}
COMMANDS_SRC = "commands"
# 佔位字串:與 chg_field_check 同一套判準(角括號包住,或明顯的待填字樣)。
PLACEHOLDER_RE = re.compile(r"^(<[^>]*>|TODO|TBD|待填|說明|description)$", re.I)


def files_of(base: Path):
    return {p.relative_to(base): p for p in base.rglob("*")
            if p.is_file() and not any(x in p.parts for x in EXCLUDE)}


def sync_commands(root: Path, registry: dict, check: bool) -> tuple[int, int, int, list[str]]:
    """commands 的同步與反向斷言。**純函式:root 與名冊都由參數傳入。**

    抽成函式的理由是可測性(CHG-20260814-03,審議席裁決):
    要證明「同步不是單檔名寫死」,得跑**兩個不同檔名、分屬不同 plugin** 的案例;
    而把夾具放進正式 `plugins/<p>/commands/` 就算第一批真實搬遷(審議席原話:
    「不因名為夾具而改變」),S2 不得放。所以 `--self-test` 改成在暫存目錄造一棵
    假樹、傳入合成名冊,**直接走這支正式邏輯**——既證明不是寫死,又不污染正式命令空間。

    回傳 (added, updated, removed, reverse_problems)。
    """
    added = updated = removed = 0
    cmd_src_dir = root / COMMANDS_SRC
    declared = {c for cs in registry.values() for c in cs}
    # **掃全部條目,不只 .md 檔。** 初版寫 `is_file() and suffix == ".md"`,
    # 於是頂層 commands/ 裡的非 .md 檔與子目錄兩種都看不見——複審 probe 實測
    # 兩者都無聲通過 exit 0。平台只吃平面 .md,所以那兩類本來就不該存在;
    # 看不見它們不是「放行」,是**閘的盲區**,和上次孤兒事故同型。
    on_disk_src = ({p.name for p in cmd_src_dir.iterdir()
                    if p.name not in EXCLUDE} if cmd_src_dir.is_dir() else set())
    src_bad_shape = ([f"{p.name}({'目錄' if p.is_dir() else '非 .md'})"
                      for p in sorted(cmd_src_dir.iterdir())
                      if p.name not in EXCLUDE
                      and (p.is_dir() or p.suffix != ".md")]
                     if cmd_src_dir.is_dir() else [])

    dst_bad_shape = []
    for plugin, cmds in registry.items():
        dst = root / "plugins" / plugin / COMMANDS_SRC
        want = {c: cmd_src_dir / c for c in cmds}
        # 同上:掃全部條目。**已宣告 plugin 的 commands/ 裡的子目錄是最嚴重的一個孔**
        # ——sync 只看第一層檔案、inventory 只驗 `commands` 節點型別不看內部,
        # 於是 `commands/deep/evil.md` 會被**打包出貨**。CHG 自己寫的
        # 「兩閘之間的縫就是下一個孤兒的住處」,縫就在這裡。
        have = ({p.name: p for p in dst.iterdir()
                 if p.is_file() and p.name not in EXCLUDE} if dst.is_dir() else {})
        if dst.is_dir():
            dst_bad_shape += [f"{plugin}/{COMMANDS_SRC}/{p.name}"
                              f"({'目錄' if p.is_dir() else '非 .md'})"
                              for p in sorted(dst.iterdir())
                              if p.name not in EXCLUDE
                              and (p.is_dir() or p.suffix != ".md")]
        for name, sp in sorted(want.items()):
            if not sp.is_file():
                continue                      # 缺來源由下方反向斷言具名報出
            dp = dst / name
            if name not in have:
                added += 1
                if not check:
                    dp.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(sp, dp)
            elif not filecmp.cmp(sp, dp, shallow=False):
                updated += 1
                if not check:
                    shutil.copy2(sp, dp)
        for name, dp in sorted(have.items()):
            if name not in want:              # plugin 內未宣告的 command = 孤兒
                removed += 1
                if not check:
                    dp.unlink()

    # ---- 反向:磁碟 → 名冊。**與 check 模式無關,永遠擋。**
    # 上次孤兒事故的成因就是三道閘全走名冊→磁碟,不在名冊裡的東西誰都走不到。
    reverse = []
    orphan_src = on_disk_src - declared
    missing_src = declared - on_disk_src
    stray_dirs = [f"{d.relative_to(root).as_posix()}"
                  f"({len([x for x in d.iterdir() if x.name not in EXCLUDE])} 檔)"
                  for d in sorted((root / "plugins").glob("*/" + COMMANDS_SRC))
                  if d.parent.name not in registry]
    if orphan_src:
        reverse.append(f"頂層 {COMMANDS_SRC}/ 有沒被任何 plugin 宣告的命令:"
                       + "、".join(sorted(orphan_src)))
    if missing_src:
        reverse.append("COMMANDS 宣告了、但頂層來源不存在:"
                       + "、".join(sorted(missing_src)))
    if stray_dirs:
        reverse.append(f"plugin 內有 {COMMANDS_SRC}/ 但該 plugin 未宣告任何命令:"
                       + "、".join(stray_dirs))
    if src_bad_shape:
        reverse.append(f"頂層 {COMMANDS_SRC}/ 只收平面 .md,出現不該有的條目:"
                       + "、".join(src_bad_shape))
    if dst_bad_shape:
        reverse.append(f"plugin 內 {COMMANDS_SRC}/ 只收平面 .md,"
                       "子目錄會被打包出貨:" + "、".join(dst_bad_shape))

    # ---- D-11:command frontmatter 至少要有非佔位的 description。
    # 那是平台唯一必要欄位,缺它的 command 會靜靜裝上然後壞掉。
    # **登記簿空不豁免**——KN-001 第 8 次的原話:規則的正確性由跑到它的輸入決定。
    for name in sorted(on_disk_src):
        f = cmd_src_dir / name
        if not f.is_file() or f.suffix != ".md":
            continue                      # 形狀問題已由上面具名
        head = f.read_text(encoding="utf-8", errors="ignore")[:400]
        m = re.search(r"^---\s*$(.*?)^---\s*$", head, re.S | re.M)
        desc = re.search(r"^description:\s*(.*)$", m.group(1), re.M) if m else None
        val = desc.group(1).strip() if desc else ""
        if not val or PLACEHOLDER_RE.match(val):
            reverse.append(f"{COMMANDS_SRC}/{name} 的 frontmatter 缺 description 或仍是佔位"
                           f"({val or '空'})——平台唯一必要欄位,缺它會靜靜裝上然後壞掉")
    return added, updated, removed, reverse


def _mkcmd(root: Path, name: str, body: str) -> None:
    d = root / COMMANDS_SRC
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(f"---\ndescription: {body}\n---\n{body}\n", encoding="utf-8")


def self_test() -> int:
    """commands 同步的紅綠端自檢——在暫存目錄造假樹,**直接走 sync_commands 正式邏輯**。

    為什麼不用真的夾具檔:放進 `plugins/<p>/commands/` 就算第一批真實搬遷
    (審議席原話:「不因名為夾具而改變」),而 S2 的範圍不含搬遷。
    合成樹既證明同步不是單檔名寫死,又不污染正式命令空間。

    兩個命令**分屬不同 plugin、檔名不同**——單檔名寫死的實作會在這裡露餡。
    """
    import tempfile
    fails = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        reg = {"alpha": ("one.md",), "beta": ("two.md",)}
        _mkcmd(root, "one.md", "第一個命令")
        _mkcmd(root, "two.md", "第二個命令")

        a, u, r, rev = sync_commands(root, reg, check=True)      # 1. 新增:先紅
        if not (a == 2 and u == r == 0) or rev:
            fails.append(f"新增未被偵測(a={a} u={u} r={r} rev={rev})")
        sync_commands(root, reg, check=False)                    # 2. 同步
        a, u, r, rev = sync_commands(root, reg, check=True)       # 3. 轉綠
        if (a, u, r) != (0, 0, 0) or rev:
            fails.append(f"同步後未歸零(a={a} u={u} r={r} rev={rev})")
        for p, n in (("alpha", "one.md"), ("beta", "two.md")):
            if not (root / "plugins" / p / COMMANDS_SRC / n).is_file():
                fails.append(f"{p}/{COMMANDS_SRC}/{n} 沒被產生——同步可能寫死單一檔名")

        _mkcmd(root, "one.md", "第一個命令改過了")               # 4. 漂移
        a, u, r, _ = sync_commands(root, reg, check=True)
        if u != 1:
            fails.append(f"內容漂移未被偵測(u={u})")
        sync_commands(root, reg, check=False)

        (root / "plugins" / "alpha" / COMMANDS_SRC / "ghost.md").write_text("x", encoding="utf-8")
        a, u, r, _ = sync_commands(root, reg, check=True)         # 5. 生成端孤兒
        if r != 1:
            fails.append(f"生成端孤兒未被偵測(r={r})")
        sync_commands(root, reg, check=False)

        _mkcmd(root, "unlisted.md", "沒登記")                     # 6. 反向:來源孤兒
        _, _, _, rev = sync_commands(root, reg, check=True)
        if not any("沒被任何 plugin 宣告" in x for x in rev):
            fails.append(f"來源孤兒(磁碟→名冊)未被偵測:{rev}")
        (root / COMMANDS_SRC / "unlisted.md").unlink()

        _, _, _, rev = sync_commands(root, {"gamma": ("nope.md",)}, check=True)  # 7. 反向:缺來源
        if not any("頂層來源不存在" in x for x in rev):
            fails.append(f"宣告了但來源不存在,未被偵測:{rev}")

        (root / "plugins" / "delta" / COMMANDS_SRC).mkdir(parents=True)
        (root / "plugins" / "delta" / COMMANDS_SRC / "x.md").write_text("x", encoding="utf-8")
        _, _, _, rev = sync_commands(root, reg, check=True)        # 8. 反向:未宣告的 plugin
        if not any("未宣告任何命令" in x for x in rev):
            fails.append(f"未宣告 plugin 的 commands/ 未被偵測:{rev}")
        shutil.rmtree(root / "plugins" / "delta")

        # ---- 以下五案由複審 probe 找出:初版三個孔全部無聲通過 exit 0
        (root / COMMANDS_SRC / "notes.txt").write_text("x", encoding="utf-8")
        _, _, _, rev = sync_commands(root, reg, check=True)        # 9. 孔:頂層非 .md
        if not any("只收平面" in x and "notes.txt" in x for x in rev):
            fails.append(f"頂層非 .md 檔未被偵測(閘的盲區):{rev}")
        (root / COMMANDS_SRC / "notes.txt").unlink()

        (root / COMMANDS_SRC / "sub").mkdir()
        _, _, _, rev = sync_commands(root, reg, check=True)        # 10. 孔:頂層子目錄
        if not any("只收平面" in x and "sub" in x for x in rev):
            fails.append(f"頂層子目錄未被偵測(閘的盲區):{rev}")
        (root / COMMANDS_SRC / "sub").rmdir()

        deep = root / "plugins" / "alpha" / COMMANDS_SRC / "deep"
        deep.mkdir(parents=True, exist_ok=True)
        (deep / "evil.md").write_text("x", encoding="utf-8")
        _, _, _, rev = sync_commands(root, reg, check=True)        # 11. 孔:會被打包出貨
        if not any("子目錄會被打包出貨" in x for x in rev):
            fails.append(f"plugin 內子目錄未被偵測——這個會出貨:{rev}")
        shutil.rmtree(deep)

        (root / COMMANDS_SRC / "one.md").write_text("沒有 frontmatter\n", encoding="utf-8")
        _, _, _, rev = sync_commands(root, reg, check=True)        # 12. D-11:缺 description
        if not any("缺 description 或仍是佔位" in x for x in rev):
            fails.append(f"缺 description 未被偵測:{rev}")

        (root / COMMANDS_SRC / "one.md").write_text(
            "---\ndescription: TODO\n---\nx\n", encoding="utf-8")
        _, _, _, rev = sync_commands(root, reg, check=True)        # 13. D-11:佔位
        if not any("缺 description 或仍是佔位" in x for x in rev):
            fails.append(f"佔位 description 未被偵測:{rev}")

    if fails:
        for f in fails:
            print(f"  ❌ {f}")
        print("\n✗ self-test 未通過:commands 同步或反向斷言的紅綠端不可達。")
        return 1
    print("✅ self-test:13 案全過——同步三分支(新增/漂移/孤兒)、"
          "反向斷言三條(來源孤兒/缺來源/未宣告 plugin)、"
          "形狀三孔(頂層非 .md、頂層子目錄、plugin 內子目錄「會出貨」)、"
          "D-11 兩案(缺 description、佔位)。"
          "兩個命令分屬不同 plugin 且檔名不同,證明不是單檔名寫死。")
    return 0


def main(argv) -> int:
    if "--self-test" in argv:
        return self_test()
    check = "--check" in argv
    added = updated = removed = 0
    for plugin, skills in PLUGINS.items():
        for name in skills:
            src, dst = SRC / name, ROOT / "plugins" / plugin / "skills" / name
            if not src.is_dir():
                print(f"ERROR: 缺來源 {src}")
                return 1
            sfiles, dfiles = files_of(src), files_of(dst) if dst.is_dir() else {}
            for rel, sp in sorted(sfiles.items()):
                dp = dst / rel
                if rel not in dfiles:
                    added += 1
                    if not check:
                        dp.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(sp, dp)
                elif not filecmp.cmp(sp, dp, shallow=False):
                    updated += 1
                    if not check:
                        shutil.copy2(sp, dp)
            for rel, dp in sorted(dfiles.items()):
                if rel not in sfiles:
                    removed += 1
                    if not check:
                        dp.unlink()

    # ---- commands(CHG-20260814-03)。邏輯在 sync_commands,這裡只接線。
    c_add, c_upd, c_rem, reverse = sync_commands(ROOT, COMMANDS, check)
    added += c_add; updated += c_upd; removed += c_rem
    if reverse:
        print("\n✗ commands 反向斷言(磁碟 → 名冊):")
        for r in reverse:
            print("  - " + r)
        print("  單一登記簿是 build_suite.py 的 COMMANDS。磁碟上多出來或少掉的東西,"
              "\n  代表登記簿與現實分岔——那正是孤兒目錄事故的形狀。")
        return 1

    total = added + updated + removed
    print(f"[{'check' if check else 'sync'}] 新增 {added} / 更新 {updated} / "
          f"移除 {removed}(共 {total} 變更)")
    if check and total:
        print("plugin 內 skills 與 commands 複本與來源不同步"
              "——執行 python3 plugins/build_suite.py 後提交")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
