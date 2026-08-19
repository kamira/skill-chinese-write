#!/usr/bin/env python3
"""
genres_table_check.py — `docs/genres.md` 的表要與磁碟、與登記簿一致(唯讀)

## 為什麼要有這一支(BL-019)

`docs/genres.md` 是「哪些文體已經是 skill、哪些沒有 lint」的對照表,而在此之前
**沒有任何機器在看它**——審議席實測:整份一字未改也全綠。

它已經失準過,而且是活的:表的第 27 行列了 `ci-poetry`,而 plugin 打包那一列
漏了它;正文更寫著「唐詩 / 宋詞尚未存在」。**主體改了、表沒跟上**——
這個 repo 反覆出現的同一件事。

## 判什麼、不判什麼

**只判表格層,敘述層明標不判。**

| 判 | 不判 |
|---|---|
| 表列的 skill 必須存在於 `skills/` | 正文敘述是否過期 |
| 「有引擎」那張表的 lint 檔必須存在 | 分組判準說得對不對 |
| 「沒有 lint」那張表的 skill:SKILL.md 要有那句宣告,**且它的腳本不得在 `ci_local.sh` 裡被跑** | 中文名、理由欄的內容 |
| plugin 打包表必須等於 `build_suite.PLUGINS` | |
| `skills/` 下每一支都要在表上出現(雙向) | |

敘述層要靠 NLP 才判得動,而造那個會製造誤殺面(KN-002)。
**這道閘抓不到「唐詩 / 宋詞尚未存在」那類過期敘述**——那句話寫在這裡,
是為了讓下一個人知道它不在守備範圍,而不是以為有人在守。

## 紅端

`--self-test` 對**真實的 `docs/genres.md`** 做單點突變,每種對應一條斷言。
突變後必須紅,**而且要紅在對應的那一條上**——不是「有紅就算」。
跑完還原,並斷言檔案內容與原始一致。

用法:
  python3 scripts/genres_table_check.py --repo .
  python3 scripts/genres_table_check.py --self-test

退出碼:0 一致 | 1 不一致 | 2 環境/參數錯誤
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

# **錨點,不是節標題。** 初版用節標題當鍵,那把閘耦合到文件的排版:
# 改個標題就要同步改程式,而閘要守的不變量與標題怎麼寫無關。
# (審議席否決內容雜湊時給的是同一個理由:要守什麼就只斷言什麼。)
# 錨點是 HTML 註解,讀的人看不到,而標題可以自由改寫。
SEC_UNIVERSAL = "universal"
SEC_ENGINE = "engine"
SEC_FRONT = "frontdoor"
SEC_NOLINT = "nolint"
SEC_PLUGIN = "packaging"
ANCHOR = re.compile(r"<!--\s*genres-table:([a-z-]+)\s*-->")
# 「沒有 lint」是 SKILL.md 裡的**宣告**,不是靠檔名猜。
# 初版斷言「scripts/ 底下不得有 .py」,而 ci-poetry 的 assets_verify.py 就不是文體 lint
# ——那條會在任何一支加了輔助腳本時誤紅。收窄成 `*_check.py` 一樣是拿檔名猜語義。
NO_LINT_DECL = "本支沒有可跑的 lint"

CODE = re.compile(r"`([^`]+)`")
# zh-style 是引擎不是文體,由所有 plugin 打包,不列在 plugin 表的成分欄裡。
UNIVERSAL = "zh-style"
HEADER_CELLS = ("文體", "規則", "plugin id")


def sections(text: str) -> dict:
    """回 {錨點名: 該錨點之後第一張表的資料列}。**圍籬內的表格行不算。**

    不濾圍籬的話,文件裡示範用的表格會被當成真的宣稱——
    `chg_field_check` 就被同一件事咬過(它抓到了正文引用的別張 Status)。
    """
    out: dict = {}
    cur = None
    fence = False
    for ln in text.splitlines():
        s = ln.lstrip()
        if s.startswith("```") or s.startswith("~~~"):
            fence = not fence
            continue
        if fence:
            continue
        m = ANCHOR.search(ln)
        if m:
            key = m.group(1)
            if key in out:
                out[key] = None          # 重複錨點 → 由 rows_of 判紅
            else:
                out[key] = []
            cur = key
            continue
        if not ln.startswith("|"):
            if ln.strip() and cur is not None and out.get(cur):
                cur = None               # 表結束了,後面的表不算這個錨點的
            continue
        if cur is None or out.get(cur) is None:
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if not cells or set("".join(cells)) <= set("-: "):
            continue
        if cells[0] in HEADER_CELLS:
            continue
        out[cur].append(cells)
    return out


class SectionMissing(Exception):
    pass


def rows_of(secs: dict, key: str) -> list:
    """找不到錨點 = **斷言靜默消失**,所以拋例外而不是回空清單。

    初版用節標題當鍵並在找不到時回 `[]`,於是猜錯的 `SEC_PLUGIN = "plugin"`
    讓 plugin 那條斷言**從頭到尾沒跑過而閘照樣有輸出**——
    同一個形狀本 repo 已經記過多次:規則不見了,而輸出長得跟通過一樣。
    """
    if key not in secs:
        raise SectionMissing("genres-table:" + key)
    if secs[key] is None:
        raise SectionMissing("genres-table:" + key + "(出現不只一次)")
    if not secs[key]:
        raise SectionMissing("genres-table:" + key + "(錨點在,但後面沒有表格資料列)")
    return secs[key]


def _first_code(cell: str):
    m = CODE.search(cell)
    return m.group(1) if m else None


def check(repo: Path, ci_path: Path = None) -> list:
    bad: list = []
    gp = repo / "docs" / "genres.md"
    if not gp.exists():
        return ["docs/genres.md 不存在——掃不到不等於通過"]
    secs = sections(gp.read_text(encoding="utf-8"))
    skills_dir = repo / "skills"
    if not skills_dir.is_dir():
        return ["skills/ 不存在——掃不到不等於通過"]
    on_disk = {d.name for d in skills_dir.iterdir() if d.is_dir()}
    claimed = set()
    # `ci_path` 只給 self-test 用。**探針不得改寫正在執行的 `ci_local.sh`**——
    # bash 是邊讀邊執行的,把跑到一半的腳本換掉會讓它從錯的位置繼續。
    # 第一版就是這樣寫的,結果 `[8b/19]` 當場把整條 CI 卡死、輸出全空。
    cip = ci_path if ci_path is not None else repo / ".github" / "ci_local.sh"
    if not cip.exists():
        return [".github/ci_local.sh 不存在——「這支腳本有沒有在把關」無從判定,"
                "**掃不到不等於通過**"]
    ci_text = cip.read_text(encoding="utf-8")
    # 五個節標題**先全部解析一次**。任何一個找不到就整支紅——
    # 節標題被改寫是常見的重構,而它會讓對應的斷言無聲蒸發。
    try:
        secmap = {k: rows_of(secs, k) for k in
                  (SEC_UNIVERSAL, SEC_ENGINE, SEC_FRONT, SEC_NOLINT, SEC_PLUGIN)}
    except SectionMissing as e:
        return ["genres.md 的機器錨點「" + str(e) + "」有問題"
                "——**對應的斷言會無聲消失**。錨點是 HTML 註解 "
                "`<!-- genres-table:xxx -->`,每張表前恰好一個;"
                "節標題可以自由改寫,錨點不行"]

    # ── 1 有引擎的(含通用引擎):skill 要在、lint 檔要在 ──
    for row in secmap[SEC_UNIVERSAL] + secmap[SEC_ENGINE]:
        name = _first_code(row[1]) if len(row) > 1 else None
        lint = _first_code(row[2]) if len(row) > 2 else None
        if not name:
            continue
        claimed.add(name)
        if name not in on_disk:
            bad.append("[有引擎] 表列 `" + name + "`,而 skills/" + name + "/ 不存在")
        elif lint and not (skills_dir / name / "scripts" / lint).exists():
            bad.append("[有引擎] 表說 `" + name + "` 的 lint 是 `" + lint +
                       "`,而 skills/" + name + "/scripts/" + lint + " 不存在")
        elif lint:
            sk = skills_dir / name / "SKILL.md"
            ref = "scripts/" + lint
            if sk.exists() and ref not in sk.read_text(encoding="utf-8"):
                bad.append("[有引擎] 表說 `" + name + "` 的 lint 是 `" + lint +
                           "`,而它的 SKILL.md 沒有引用 " + ref +
                           "——表與 skill 自己的宣告不一致")

    # ── 2 前門:skill 或 /plugin:command 二者之一要在 ──
    bsrc = (repo / "plugins" / "build_suite.py")
    commands: dict = {}
    if bsrc.exists():
        cm = re.search(r"COMMANDS: dict\[str, tuple\[str, \.\.\.\]\] = \{(.*?)"
                       + chr(10) + r"\}", bsrc.read_text(encoding="utf-8"), re.S)
        if cm:
            for pm in re.finditer(r'"([^"]+)":\s*\(([^)]*)\)', cm.group(1)):
                commands[pm.group(1)] = {x.strip().strip("'").strip('"')
                                         for x in pm.group(2).split(",") if x.strip()}
    if not commands:
        bad.append("build_suite.COMMANDS 解析不到任何項目"
                   "——**解析失敗不等於一致**,前門的 plugin 前綴會變成不驗")
    for row in secmap[SEC_FRONT]:
        ref = _first_code(row[1]) if len(row) > 1 else None
        if not ref:
            continue
        if ref.startswith("/"):
            # `/plugin:command` —— **前綴也要驗**。初版只看 `:` 之後那段,
            # 於是把 `/fiction:` 改成 `/press:` 照樣全綠(審議席 E1 實測)。
            plug = ref.lstrip("/").split(":")[0]
            cmd = ref.split(":")[-1]
            if not (repo / "commands" / (cmd + ".md")).exists():
                bad.append("[前門] 表列命令 `" + ref + "`,而 commands/" +
                           cmd + ".md 不存在")
            elif (cmd + ".md") not in commands.get(plug, ()):
                bad.append("[前門] 表列 `" + ref + "`,而 build_suite.COMMANDS 裡 `" +
                           plug + "` 沒有收 `" + cmd + "`"
                           "——命令的呼叫面是 `/<plugin>:<命令>`,前綴錯了就叫不出來")
            continue
        claimed.add(ref)
        if ref not in on_disk:
            bad.append("[前門] 表列 `" + ref + "`,而 skills/" + ref + "/ 不存在")

    # ── 3 沒有 lint 的:skill 要在,而且**必須真的沒有** lint ──
    for row in secmap[SEC_NOLINT]:
        name = _first_code(row[1]) if len(row) > 1 else None
        if not name:
            continue
        claimed.add(name)
        if name not in on_disk:
            bad.append("[沒有 lint] 表列 `" + name + "`,而 skills/" + name +
                       "/ 不存在")
        else:
            sk = skills_dir / name / "SKILL.md"
            if not sk.exists():
                bad.append("[沒有 lint] `" + name + "` 沒有 SKILL.md,"
                           "無從查證它是否宣告了沒有 lint")
            elif NO_LINT_DECL not in sk.read_text(encoding="utf-8"):
                bad.append("[沒有 lint] 表說 `" + name + "` 沒有 lint,"
                           "而它的 SKILL.md 沒有「" + NO_LINT_DECL + "」這句宣告"
                           "——建了 lint 就要把它挪到「有引擎」那張表")
            else:
                # **磁碟側也要看,但不猜檔名。** 判準是「CI 有沒有在跑它」——
                # `ci_local.sh` 是本 repo 的唯一真相源,一支腳本被它跑就是在把關。
                # 審議席 E4 實測:只驗宣告的話,某支長出 lint 而表與 SKILL.md 都不動,
                # 閘全盲;而初版「scripts/ 不得有 .py」會被 assets_verify.py 這類
                # 輔助腳本誤紅。用 CI 當判準兩邊都避開。
                d = skills_dir / name / "scripts"
                if d.is_dir():
                    for f in sorted(d.glob("*.py")):
                        ref = "skills/" + name + "/scripts/" + f.name
                        if ref in ci_text:
                            bad.append("[沒有 lint] 表說 `" + name + "` 沒有 lint,"
                                       "而 " + ref + " 正在 ci_local.sh 裡被跑"
                                       "——它已經是一道閘了,請挪到「有引擎」那張表")

    # ── 4 plugin 打包表 == build_suite.PLUGINS(**完整相等**)──
    # 初版只走表列、且 `pid not in plugins` 就 continue,於是三個洞全開:
    # 表多一列不紅、登記簿多一個不紅、成分欄是空的也過——
    # **那不是「相等」,是「表列的都對」。** 審議席擋下,改成兩邊建 dict 再比。
    bs = repo / "plugins" / "build_suite.py"
    if not bs.exists():
        bad.append("plugins/build_suite.py 不存在——plugin 那條斷言無從比對")
    else:
        src = bs.read_text(encoding="utf-8")
        m = re.search(r"PLUGINS = \{(.*?)" + chr(10) + r"\}", src, re.S)
        registry: dict = {}
        if m:
            for pm in re.finditer(r'"([^"]+)":\s*\(([^)]*)\)', m.group(1)):
                registry[pm.group(1)] = {x.strip().strip("'").strip('"')
                                         for x in pm.group(2).split(",")
                                         if x.strip()} - {UNIVERSAL}
        if not registry:
            bad.append("build_suite.PLUGINS 解析不到任何項目"
                       "——**解析失敗不等於一致**")
        else:
            table: dict = {}
            for row in secmap[SEC_PLUGIN]:
                pid = _first_code(row[0])
                if not pid:
                    continue
                comp = set(CODE.findall(row[2])) if len(row) > 2 else set()
                # **重複的 pid 列必須紅。** 初版直接 `table[pid] = comp`,
                # 後者蓋前者——把錯的那列擺在前面,閘就看不見它。
                # 錨點那邊已經做了「重複就紅」,表列同理(審議席 E3 實測 fail-open)。
                if pid in table:
                    bad.append("[plugin] `" + pid + "` 在表上出現不只一次"
                               "——**後一列會蓋掉前一列**,錯的那列擺前面就沒人看得見")
                    continue
                table[pid] = comp
            for pid in sorted(set(table) - set(registry)):
                bad.append("[plugin] 表列了 `" + pid +
                           "`,而 build_suite.PLUGINS 沒有這個 plugin")
            for pid in sorted(set(registry) - set(table)):
                bad.append("[plugin] build_suite.PLUGINS 有 `" + pid +
                           "`,而表上沒有這一列")
            for pid in sorted(set(table) & set(registry)):
                if not table[pid]:
                    bad.append("[plugin] `" + pid + "` 那一列的成分欄是空的"
                               "——**空欄不算相符**,登記簿裡是 " +
                               str(sorted(registry[pid])))
                elif table[pid] != registry[pid]:
                    bad.append("[plugin] `" + pid + "` 表列 " +
                               str(sorted(table[pid])) +
                               ",而 build_suite.PLUGINS 是 " +
                               str(sorted(registry[pid])))

    # ── 5 雙向:磁碟上每一支都要在表上 ──
    for name in sorted(on_disk - claimed):
        bad.append("[雙向] skills/" + name + "/ 存在,而三張表都沒有列它"
                   "——新增 skill 要同時上表,否則表會靜默過期")
    for name in sorted(claimed - on_disk):
        bad.append("[雙向] 表列 `" + name + "`,而磁碟上沒有")
    return bad


ROW = "| `fiction` | — | `fiction` |"

MUTATIONS = [
    ("有引擎/skill 不存在", "| `regulated-verse` |", "| `regulated-verse-x` |",
     "[有引擎]"),
    ("有引擎/lint 檔不存在", "`ci_check.py`", "`ci_check_x.py`", "[有引擎]"),
    ("前門/命令不存在", "`/fiction:fiction-flash`", "`/fiction:fiction-flash-x`",
     "[前門]"),
    ("沒有 lint 的那支其實有 lint", "| 散文 | `prose` |", "| 散文 | `writing` |",
     "[沒有 lint]"),
    ("plugin 成分與登記簿不符", "`fu`、`historiography`", "`fu`", "[plugin]"),
    # 以下三條是審議席擋下的缺口:初版只走表列,這三種都不紅
    ("plugin 表多一列", ROW,
     ROW + chr(10) + "| `nosuchplugin` | — | `prose` |", "[plugin]"),
    ("plugin 表少一列", ROW + chr(10), "", "[plugin]"),
    ("plugin 成分欄是空的", ROW, "| `fiction` | — | 待補 |", "[plugin]"),
    ("前門/plugin 前綴錯", "`/fiction:fiction-flash`", "`/press:fiction-flash`",
     "[前門]"),
    ("plugin 表同一個 pid 出現兩次", ROW, ROW + chr(10) + ROW, "[plugin]"),
    ("錨點被刪掉", "<!-- genres-table:packaging -->" + chr(10), "",
     "genres.md 的機器錨點"),
    ("錨點重複", "<!-- genres-table:nolint -->",
     "<!-- genres-table:nolint -->" + chr(10) + "<!-- genres-table:nolint -->",
     "genres.md 的機器錨點"),
]


def self_test(repo: Path) -> int:
    """對**真實的 genres.md** 做單點突變。綠端是真實檔案,不是我造的樣本。"""
    gp = repo / "docs" / "genres.md"
    if not gp.exists():
        print("  ❌ docs/genres.md 不存在,self-test 無從跑起")
        return 1
    orig = gp.read_text(encoding="utf-8")
    fails = []
    base = check(repo)
    if base:
        fails.append("綠端:現行 genres.md 本身就不一致 " + str(base[:3]))

    def run_mut(label: str, text: str, want: str):
        gp.write_text(text, encoding="utf-8")
        try:
            got = check(repo)
        finally:
            gp.write_text(orig, encoding="utf-8")
        if not any(g.startswith(want) for g in got):
            fails.append("突變「" + label + "」應紅在 " + want + ",實得 " +
                         (str(got[:2]) if got else "全綠") + "——**該斷言不可達**")

    for label, a, b, want in MUTATIONS:
        n = orig.count(a)
        if n != 1:
            fails.append("突變「" + label + "」的錨點在 genres.md 命中 " + str(n) +
                         " 次,不是 1——**探針本身壞了**,它打在哪裡不確定")
            continue
        run_mut(label, orig.replace(a, b, 1), want)

    # 雙向的紅端:把某一支從表上刪掉(刪除突變,不是換詞)
    row = "| 詞(宋詞) | `ci-poetry` | `ci_check.py` |"
    n = orig.count(row)
    if n != 1:
        fails.append("雙向突變的錨點命中 " + str(n) + " 次,不是 1")
    else:
        run_mut("表上刪掉一支磁碟有的 skill", orig.replace(row + chr(10), "", 1),
                "[雙向]")

    # ── 突變 genres.md 以外的檔:①③ 的 SKILL.md 側與 ci_local 側 ──
    # 審議席指出:「11 個紅端皆可達」為真,但那 11 個全在 genres.md 上突變,
    # 而 SKILL.md 側的兩條斷言**一個都沒被覆蓋**。可達性要對每一條分別成立。
    def mutate_file(label, path, a, b, want, times=1):
        """times = **預期命中數**,不是「至少一次」。

        斷言是「SKILL.md 有沒有引用那支 lint」,所以突變必須把**全部**出現處
        都拿掉——只改其中一處,另一處還在,斷言照樣綠。
        第一版只改了行 59 而行 6 還在,於是「應紅卻全綠」。
        """
        f = repo / path
        if not f.exists():
            fails.append("突變「" + label + "」的檔不存在:" + path)
            return
        raw = f.read_bytes()
        txt = raw.decode("utf-8")
        n = txt.count(a)
        if n != times:
            fails.append("突變「" + label + "」的錨點在 " + path + " 命中 " +
                         str(n) + " 次,預期 " + str(times) + "——**探針本身壞了**")
            return
        f.write_bytes(txt.replace(a, b).encode("utf-8"))
        try:
            got = check(repo)
        finally:
            f.write_bytes(raw)
        if f.read_bytes() != raw:
            fails.append("突變「" + label + "」沒把 " + path + " 還原")
        if not any(g.startswith(want) for g in got):
            fails.append("突變「" + label + "」應紅在 " + want + ",實得 " +
                         (str(got[:2]) if got else "全綠") + "——**該斷言不可達**")

    mutate_file("有引擎/SKILL.md 沒引用它宣稱的 lint",
                "skills/regulated-verse/SKILL.md",
                "scripts/verse_check.py", "scripts/verse_check_x.py",
                "[有引擎]", times=2)
    mutate_file("沒有 lint/SKILL.md 少了那句宣告",
                "skills/prose/SKILL.md", NO_LINT_DECL, "本支暫時沒有 lint",
                "[沒有 lint]")
    # 這一條要**同時**建檔與掛進 CI 才碰得到:9 支「沒有 lint」的 skill
    # 磁碟上都沒有 scripts/ 目錄,只改 ci_local 的話那個路徑根本不存在,斷言不會觸發。
    # (第一版只改 ci_local,結果「應紅卻全綠」——探針自己漏了前置條件。)
    probe_dir = repo / "skills" / "prose" / "scripts"
    probe_py = probe_dir / "prose_check.py"
    cip = repo / ".github" / "ci_local.sh"
    ci_raw = cip.read_bytes()
    ci_txt = ci_raw.decode("utf-8")
    hook = "$PY skills/zh-style/scripts/zh_style_check.py --self-test"
    if hook not in ci_txt:
        fails.append("ci_local 突變的錨點找不到:" + hook)
    else:
        made_dir = not probe_dir.exists()
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            fake_ci = Path(td) / "ci_local.sh"
            fake_ci.write_text(ci_txt.replace(
                hook, hook + chr(10) + "$PY skills/prose/scripts/prose_check.py", 1),
                encoding="utf-8")
            try:
                probe_dir.mkdir(parents=True, exist_ok=True)
                probe_py.write_text("# probe" + chr(10), encoding="utf-8")
                got = check(repo, ci_path=fake_ci)
            finally:
                if probe_py.exists():
                    probe_py.unlink()
                if made_dir and probe_dir.exists():
                    probe_dir.rmdir()
        if probe_py.exists() or (made_dir and probe_dir.exists()):
            fails.append("**探針沒把 skills/prose/scripts/ 清乾淨**")
        if cip.read_bytes() != ci_raw:
            fails.append("**探針動到了活的 ci_local.sh**——它正在被執行,不得改寫")
        if not any(g.startswith("[沒有 lint]") for g in got):
            fails.append("突變「沒有 lint 的那支,腳本卻在 ci_local 裡被跑」"
                         "應紅在 [沒有 lint],實得 " +
                         (str(got[:2]) if got else "全綠") + "——**該斷言不可達**")

    if gp.read_text(encoding="utf-8") != orig:
        fails.append("**self-test 沒把 genres.md 還原**")
    if fails:
        for f in fails:
            print("  ❌ " + f)
        return 1
    # **數字從資料算出來,不寫死。** 寫死的數字會在加案時過期,
    # 而它讀起來跟真的一樣——本 repo 反覆出現的「改了主體、漏了標頭」。
    print("✅ self-test:綠端是真實檔案;" + str(len(MUTATIONS) + 4) +
          " 個紅端皆由單點突變產生,且各自紅在對應的斷言上(不是「有紅就算」)。")
    print("   genres.md 側:" + "、".join(lbl for lbl, _, _, _ in MUTATIONS) +
          "、表上刪掉一支磁碟有的 skill")
    print("   其他檔側:SKILL.md 沒引用它宣稱的 lint、SKILL.md 少了沒有 lint 的宣告、"
          "沒有 lint 的那支卻在 ci_local 裡被跑")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="genres.md 的表要與磁碟一致")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    repo = Path(a.repo)
    if a.self_test:
        return self_test(repo)
    bad = check(repo)
    if bad:
        print("✗ docs/genres.md 與磁碟 / 登記簿不一致 " + str(len(bad)) + " 處:")
        for b in bad:
            print("  " + b)
        print("")
        print("表是「哪些文體有機器在把關」的對照表。它自己過期時,"
              "讀的人會以為某支有 lint 而其實沒有——或反過來。")
        return 1
    print("✅ docs/genres.md 的表與磁碟、與 build_suite.PLUGINS 一致。")
    print("   **敘述層不判**:正文的分組理由、中文名、「尚未建」這類句子"
          "本閘看不到,過期了不會紅。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
