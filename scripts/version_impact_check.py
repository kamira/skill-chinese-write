#!/usr/bin/env python3
"""版號影響閘——skill 的內容變了,打包它的每一個 plugin 都要 bump。

## 這道閘補的洞

`catalog_check --since` 的 bump 規則,判定「哪些 plugin 需要 bump」時走的是
`skills_of()`:

    def skills_of(repo, plugin):
        return [p for p in [repo / "skills" / plugin / "SKILL.md"] if p.is_file()]

**它只看同名 skill。** 而一個 plugin 的出貨樹裡,同名的只有一支,其餘全是隨附。
實測 `zh-style` 被**全部 21 個** plugin 打包、`fiction` 被 7 個。

於是:今天改一條 `zh-style` 的規則,`catalog_check --since` 只會逼 marketplace
的總版號 bump,**21 個宿主 plugin 的 entry / plugin.json 一個都不用動,閘全綠**
——而那 21 個 plugin 的出貨行為全變了,已安裝的使用者一個都拿不到。

規則想管「plugin 變了就要 bump」,斷言查的只是其中一小塊。**KN-001 的形狀。**

## 內容 vs 戳記

`CHG-20260814-05` 留下的教訓是另一個方向:`skills/fiction/SKILL.md` 的版號
被三處同步斷言拖著從 1.0.0 跳到 1.1.0,byte-sync 把它灌進六個宿主副本,
**而 fiction skill 的內容一個字沒改**。若照「出貨樹變了就 bump」硬套,
六個宿主都得 bump,release note 只能寫「內含戳記變了」——那是
`CHG-20260814-03` 剛擋掉的無內容版本污染。

所以判準是:**整棵出貨樹的 byte,但根 `SKILL.md` 排除 `metadata.version` 那一行。**
排除後為空 = 戳記變更,沒有人需要 bump。

審議席(codex)對兩個邊界的裁決:
- **整棵樹都算**——`assets/`、`references/`、`scripts/` 任一 byte 變都要 bump。
  規則檔與引擎也在出貨樹裡,改它們同樣是行為變更,而它們沒有版號可言。
- **空白與註解也算**——「以 byte 為準,只要 byte 狀態改變,同一版本就不應
  指向兩種產物;僅精確排除 `metadata.version` 那一行。」

這意味著本閘**沒有語意層的寬容**:改一個空格就要 bump 21 個宿主。
那不是誤傷,是 copy-bundling 的誠實成本。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

EXCLUDE_PARTS = ("__pycache__", ".DS_Store")
VERSION_LINE = re.compile(rb"^(\s*)version:\s*\S+\s*$")


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True)


def blob_at(repo: Path, ref: str, path: str) -> bytes | None:
    """某個 ref 當時的檔案內容。不存在回 None(新增/刪除要能分辨)。

    **用 `cat-file blob` 不用 `show`,而且兩端都取 committed 狀態。**
    初版拿 `git show <ref>:path` 的輸出去比工作樹的 `read_bytes()`,
    在 Windows 上每一個檔都判成「變了」——`show` 會套 eol 轉換,工作樹是 CRLF、
    blob 是 LF,於是全樹假陽性,self-test 12 案裡 5 案直接爆掉。

    比對兩端都必須是同一種東西。`--since` 的語意本來就是 `REF..HEAD`
    (與 `catalog_check` 一致),未 commit 的改動不在裡面。
    """
    r = git(repo, "cat-file", "blob", f"{ref}:{path}")
    return r.stdout if r.returncode == 0 else None


def semver(v: str) -> tuple[int, ...] | None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", v or ""):
        return None
    return tuple(int(x) for x in v.split("."))


def advanced(old: str, new: str) -> bool:
    """新版號必須**嚴格大於**舊的。

    審議席(fable)指出:規則寫「必 bump」而斷言只查「不同」,
    那麼內容變更 + 版號 1.1.0 → 1.0.1 會照字面通過。
    `catalog_check --since` 現行就只比「不同」;本閘不抄那個。
    """
    a, b = semver(old), semver(new)
    if a is None or b is None:
        return old != new          # 非 semver 就退回「不同」,但下面會另外具名報出
    return b > a


def strip_version_line(data: bytes) -> bytes:
    """只把**frontmatter 區塊裡**的 `version:` 那一行拿掉。

    **只拿掉那一行,不做任何其他正規化。** 空白、註解、換行一律保留——
    審議席原話:「以 byte 為準,只要 byte 狀態改變,同一版本就不應指向兩種產物」。
    加任何「聰明」的正規化,就是在替閘開語意層的後門。

    初版剝的是**全檔任何**符合的行,而 docstring 卻寫「只把 frontmatter 裡的」。
    複審實測那個落差會造成**死鎖**:正文裡一行 `version: v1 → v2` 的真內容變更
    被判成「一個 byte 都沒變」的戳記紅,而戳記紅無論怎麼 bump 都過不了
    ——沒有任何一條路能讓它變綠。方向是誤殺不是放行,但死鎖比誤殺更糟。
    """
    lines = data.split(b"\n")
    # frontmatter = 開頭第一個 `---` 到下一個 `---` 之間
    if not lines or lines[0].strip() != b"---":
        return data
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == b"---")
    except StopIteration:
        return data
    # **只剝 `metadata:` 區塊底下那一行**,不是 frontmatter 裡任何一行。
    # CHG-20260814-07:二讀複審實測,剝「frontmatter 內任何 version:」
    # 會讓 frontmatter 頂層的 `version:` 鍵被判成戳記——訊息會說
    # 「metadata.version 從 1.0.0 動到 1.0.0」這種胡話,而且那個形狀
    # 怎麼 bump 都過不了(案 19 死鎖的 frontmatter 版)。
    out, in_meta = [], False
    for ln in lines[1:end]:
        if re.match(rb"^metadata:\s*$", ln):
            in_meta = True
            out.append(ln)
            continue
        if in_meta and re.match(rb"^\S", ln):    # 回到頂層鍵 = 離開 metadata 區塊
            in_meta = False
        if in_meta and VERSION_LINE.match(ln):
            continue                             # 這才是要剝的那一行
        out.append(ln)
    return b"\n".join([lines[0], *out, *lines[end:]])


def skill_files(repo: Path, skill: str) -> list[str]:
    base = repo / "skills" / skill
    if not base.is_dir():
        return []
    return sorted(p.relative_to(repo).as_posix() for p in base.rglob("*")
                  if p.is_file() and not any(x in p.parts for x in EXCLUDE_PARTS))


def _parse_registry(src: str, name: str, where: str) -> dict[str, tuple[str, ...]]:
    m = re.search(rf"^{name}[^=]*=\s*\{{(.*?)^\}}", src, re.S | re.M)
    if m is None:
        raise SystemExit(f"讀不到 build_suite.py 的 {name}({where})"
                         "——名冊形狀變了,本閘失效。**不 skip**:"
                         "讀不到名冊時放行,等於名冊一改形狀規則就全部消失")
    out: dict[str, tuple[str, ...]] = {}
    # key 兩種引號都認。初版只認雙引號,於是單引號的名冊會 **parse 成空 dict**
    # 而不是報錯——「解析不出來」與「真的沒有 plugin」長得一模一樣,
    # 那是本閘自己的靜默 fail-open。
    for e in re.finditer(r"""["']([\w.-]+)["']\s*:\s*\(([^)]*)\)""", m.group(1)):
        out[e.group(1)] = tuple(x.strip().strip("'\"")
                                for x in e.group(2).split(",") if x.strip())
    if not out and re.search(r"\S", m.group(1)):
        raise SystemExit(f"{name} 的區塊有內容卻一個條目都 parse 不出來({where})"
                         "——名冊寫法變了。**空 dict 不得與『解析失敗』同義**")
    return out


def load_retired(repo: Path, ref: str) -> dict[str, str]:
    """讀 `RETIRED` 名冊——**退役過的 plugin id**(CHG-20260814-10)。

    這張名冊在的理由:現存全部閘只斷言「名冊↔磁碟一致」,而把 plugin 目錄與
    名冊條目**一起**刪掉,兩邊同時消失就「一致」——**對每一道閘都是不可見事件**。

    舊 ref 沒有這張名冊是正常的(它是本張才加的),回空 dict;
    但**格式壞掉**要炸,與另外兩張名冊同一口徑。
    """
    raw = blob_at(repo, ref, "plugins/build_suite.py")
    if raw is None:
        return {}
    src = raw.decode("utf-8", "replace")
    m = re.search(r"^RETIRED[^=]*=\s*\{(.*?)^\}", src, re.S | re.M)
    if m is None:
        return {}                      # 名冊還沒出生 ≠ 名冊壞了
    out = {k: v for k, v in re.findall(
        r"""["']([\w.-]+)["']\s*:\s*["']([^"']*)["']""", m.group(1))}
    if not out and re.search(r"\S", m.group(1)):
        raise SystemExit(f"RETIRED 區塊有內容卻一個條目都 parse 不出來({ref})"
                         "——**空 dict 不得與『解析失敗』同義**")
    return out


def load_registries(repo: Path, ref: str) -> tuple[dict, dict]:
    """從**某個 ref 的 blob** 讀 PLUGINS 與 COMMANDS。

    兩件事在 CHG-20260814-07 改掉:

    1. **從 blob 讀,不從工作樹讀。** 初版 `load_plugins` 只讀工作樹,
       所以「成分變更」這條規則若沿用它,等於**拿 HEAD 跟 HEAD 比**——空話。
    2. **COMMANDS 也要讀。** 初版完全不碰它,於是 `COMMANDS` 增刪一個命令
       對本閘完全隱形,而批量搬遷要改它五次。

    任一端 parse 不出形狀就 `SystemExit`,不 skip。
    """
    raw = blob_at(repo, ref, "plugins/build_suite.py")
    if raw is None:
        raise SystemExit(f"{ref} 當時沒有 plugins/build_suite.py——無法比對名冊")
    src = raw.decode("utf-8", "replace")
    return (_parse_registry(src, "PLUGINS", ref),
            _parse_registry(src, "COMMANDS", ref))


def load_plugins(repo: Path) -> dict[str, tuple[str, ...]]:
    """工作樹版本,保留給不需要兩端比較的呼叫者。"""
    src = (repo / "plugins" / "build_suite.py").read_text(encoding="utf-8")
    return _parse_registry(src, "PLUGINS", "工作樹")


def hosts_of(plugins: dict[str, tuple[str, ...]], skill: str) -> list[str]:
    return sorted(p for p, sk in plugins.items() if skill in sk)


def entry_versions(repo: Path, ref: str) -> dict[str, str]:
    """marketplace 的 plugin → entry.version(committed 狀態)。"""
    path = ".claude-plugin/marketplace.json"
    raw = blob_at(repo, ref, path)
    if raw is None:
        return {}
    try:
        mk = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    return {p.get("name", "?"): str(p.get("version", "")) for p in mk.get("plugins", [])}


def plugin_json_version(repo: Path, ref: str, plugin: str) -> str:
    path = f"plugins/{plugin}/.claude-plugin/plugin.json"
    raw = blob_at(repo, ref, path)
    if raw is None:
        return ""
    try:
        return str(json.loads(raw.decode("utf-8")).get("version", ""))
    except json.JSONDecodeError:
        return ""


def skill_version(repo: Path, ref: str, skill: str) -> str:
    path = f"skills/{skill}/SKILL.md"
    raw = blob_at(repo, ref, path)
    if raw is None:
        return ""
    m = re.search(r"^metadata:\s*$\s*^\s+version:\s*(\S+)\s*$",
                  raw.decode("utf-8", "replace"), re.M)
    return m.group(1) if m else ""


def tree_files(repo: Path, ref: str, prefix: str) -> set[str]:
    r = git(repo, "ls-tree", "-r", "--name-only", ref, "--", prefix)
    if r.returncode != 0:
        return set()
    return {p for p in r.stdout.decode("utf-8", "replace").split("\n")
            if p and not any(x in p.split("/") for x in EXCLUDE_PARTS)}


def classify(repo: Path, ref: str, head: str, skill: str) -> str:
    """回傳 'content' / 'stamp' / 'none'。**兩端都是 committed 狀態。**

    'stamp' 不再與 'none' 同義——見 check() 裡的戳記凍結規則。
    """
    root_md = f"skills/{skill}/SKILL.md"
    paths = tree_files(repo, ref, f"skills/{skill}/") | \
        tree_files(repo, head, f"skills/{skill}/")

    stamp_only = False
    for p in sorted(paths):
        old, new = blob_at(repo, ref, p), blob_at(repo, head, p)
        if old == new:
            continue
        if p == root_md and old is not None and new is not None:
            if strip_version_line(old) == strip_version_line(new):
                stamp_only = True     # 只有戳記行不同
                continue
        return "content"
    return "stamp" if stamp_only else "none"


def resolve_base(repo: Path, ref: str) -> str | None:
    """把 `--since` 的參照解析成**分岔點**,不是它的 tip。回不了就 None。

    複審實測的誤傷:main 合法前進(某支 skill 內容變 + 全員正確 bump)之後,
    一條**只動 docs 的無關分支**跑本閘會紅三條,訊息指控它
    「shared 的版號從 1.1.0 倒退到 1.0.0」——它根本沒碰過那支 skill。

    `catalog_check --since` 同樣是兩點比較,但它只比「不同」所以意外容忍;
    本閘改成嚴格遞增之後,**任何 skill 內容 PR 合入 main,所有未 rebase 的
    並行分支都會全紅,而且紅得與自己的程式碼無關**。
    `ci_local.sh` 開頭自己引的 KN-002 講的就是這種閘:誤報會教人忽略它。

    merge-base 取不到時**回 None(fail-closed)**,不退回 tip——
    退回 tip 就是把剛修掉的誤傷偷偷放回來。
    """
    if git(repo, "rev-parse", "--verify", ref).returncode != 0:
        return None
    mb = git(repo, "merge-base", ref, "HEAD")
    if mb.returncode != 0 or not mb.stdout.strip():
        return None
    return mb.stdout.decode().strip()


def exclude_drift(repo: Path) -> list[str]:
    """EXCLUDE 名單的交叉斷言——兩份名單分岔,就有檔案在某一支眼裡不存在。

    審議席(fable)要求比照 `TOP_TOOL_FILES` 的做法。理由一樣:
    本閘用自己的 EXCLUDE 決定「哪些檔算出貨樹」,`build_suite` 用它的 EXCLUDE
    決定「哪些檔要同步」。兩邊不一致的那些檔,會被同步出去卻不被版號閘看見。
    """
    src = (repo / "plugins" / "build_suite.py").read_text(encoding="utf-8")
    m = re.search(r"^EXCLUDE\s*=\s*\(([^)]*)\)", src, re.M)
    if not m:
        return ["讀不到 build_suite.py 的 EXCLUDE——名單形狀變了,交叉斷言失效"]
    theirs = tuple(x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip())
    if set(theirs) != set(EXCLUDE_PARTS):
        return [f"EXCLUDE 名單分岔:本檔 {sorted(EXCLUDE_PARTS)} vs "
                f"build_suite.py {sorted(theirs)}"
                "——分岔處的檔會被同步出貨卻不被版號閘看見"]
    return []


GEN_SPACES = ("skills", "commands")   # plugin 目錄裡的生成空間


def own_files_delta(repo: Path, ref: str, head: str, plugin: str) -> list[str]:
    """R3:plugin **自己的手寫檔**有沒有變。**補集定義,不是列舉。**

    範圍 = `plugins/<p>/**` 扣除 `skills/**` 與 `commands/**` 兩塊生成空間,
    再扣除 `plugin.json` 的頂層 `version` 鍵。

    審議席(fable)否掉了草案的列舉式寫法(「plugin.json、README 等」):
    **列舉會讓下一個手寫檔靜默漏網,正是這個 repo 的孤兒事故形狀。**
    補集定義下,未知的檔落進「算」,不是落進「不算」。

    `version` 鍵用 **JSON 解析後刪鍵**比對,不對文字做 regex 剝行——
    CHG-20260814-06 的案 19 死鎖有 JSON 雙胞胎:巢狀物件裡的 `"version"`、
    README 裡恰好長那樣的一行,剝掉任何一個都是重演同一個 bug。
    """
    pj = f"plugins/{plugin}/.claude-plugin/plugin.json"
    paths = (tree_files(repo, ref, f"plugins/{plugin}/")
             | tree_files(repo, head, f"plugins/{plugin}/"))
    out: list[str] = []
    for p in sorted(paths):
        parts = p.split("/")
        if len(parts) > 2 and parts[2] in GEN_SPACES:
            continue                       # 生成空間,由它的驅動源負責
        old, new = blob_at(repo, ref, p), blob_at(repo, head, p)
        if old == new:
            continue
        if p == pj and old is not None and new is not None:
            try:
                a = json.loads(old.decode("utf-8"))
                b = json.loads(new.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                out.append(f"{p} 解析不了(視為內容變更)")
                continue
            va, vb = a.pop("version", None), b.pop("version", None)
            # **只有在 version 值真的變了時才豁免。**
            # 複審 probe P5:初版寫 `if a == b: continue`,於是 plugin.json
            # 的**純格式重排**(byte 變、JSON 語意相同、version 沒動)
            # 也被一併豁免——出貨的 byte 變了卻不觸發任何規則,
            # 違反「以 byte 為準」那條裁決。JSON 比對本來只該替 version 鍵開口,
            # 不該替所有語意等價的 byte 噪音開口。
            if a == b and va != vb:
                continue                   # 只有頂層 version 鍵不同 = 戳記
        out.append(p)
    return out


def check(repo: Path, ref: str, head: str = "HEAD") -> list[str]:
    """**理由聚合,不是規則抑制。**

    同一件事會讓多條規則開火(掛一支新 skill → 成分變了,同時新 skill 樹
    從無到有讓 skill→宿主規則也火)。兩發要的是同一個動作。

    審議席(fable)畫的線:「絕對不要寫成『R2 已觸發就跳過 R1』——
    **抑制邏輯的 bug 是靜默綠**,fail-open 的形狀;
    聚合邏輯的 bug 最多是理由列少一條,verdict 不變。」
    """
    P_old, C_old = load_registries(repo, ref)
    P_new, C_new = load_registries(repo, head)
    old_e, new_e = entry_versions(repo, ref), entry_versions(repo, head)
    bad: list[str] = exclude_drift(repo)
    # **席位從兩張名冊的聯集種,不是只從 PLUGINS。**
    # 複審 probe P1:只出現在 COMMANDS、不出現在 PLUGINS 的 plugin,
    # 進不了下面的 R4 迴圈,於是「驅動源全靜止卻動版號」對它**永遠不會紅**。
    # 今天 COMMANDS 的鍵剛好是 PLUGINS 的子集所以打不到正式樹,
    # 但名冊格式允許那個形狀——**對一類合法輸入紅端不可達**,
    # 正是本張自己立的病名。
    reasons: dict[str, list[str]] = {p: [] for p in set(P_new) | set(C_new)}

    def why(plugin: str, msg: str) -> None:
        reasons.setdefault(plugin, []).append(msg)

    # ---- R2:名冊成分變更。**兩端各自從 blob parse**,否則是拿 HEAD 跟 HEAD 比。
    for p in sorted(set(P_old) | set(P_new) | set(C_old) | set(C_new)):
        if p not in P_new and p not in C_new:
            continue          # 整個消失的 plugin:diff 式的閘看不見,見 CHG 的停點 2
        if P_old.get(p, ()) != P_new.get(p, ()):
            why(p, f"PLUGINS 成分變了 {P_old.get(p, ())} → {P_new.get(p, ())}")
        if C_old.get(p, ()) != C_new.get(p, ()):
            why(p, f"COMMANDS 成分變了 {C_old.get(p, ())} → {C_new.get(p, ())}")

    # ---- R5/R6/R7:**消失也要看得見**(CHG-20260814-10)。
    #
    # 現存全部閘只斷言「名冊↔磁碟一致」,而把 plugin 目錄與名冊條目**一起**刪掉,
    # 兩邊同時消失就「一致」——對每一道閘都是不可見事件。R2 的那句
    # `if p not in P_new and p not in C_new: continue` 就是這個盲區的所在。
    R_old, R_new = load_retired(repo, ref), load_retired(repo, head)
    live_old = set(P_old) | set(C_old)
    live_new = set(P_new) | set(C_new)

    # R5 縮水必須具名
    for p in sorted(live_old - live_new):
        if p not in R_new:
            bad.append(f"plugin「{p}」自 {ref} 起從名冊消失,但沒有列進 RETIRED"
                       "——目錄與名冊一起刪掉的話,每一道閘看到的都是「一致」,"
                       "縮水因此要具名才看得見")

    # R6 名冊與現實雙向一致
    for p in sorted(R_new):
        if p in live_new:
            bad.append(f"plugin「{p}」列在 RETIRED,卻仍在 PLUGINS/COMMANDS 裡"
                       "——具名了卻沒真的退役")
        if (repo / "plugins" / p).exists():
            bad.append(f"plugin「{p}」列在 RETIRED,但 plugins/{p}/ 還在磁碟上")
        if p in new_e:
            bad.append(f"plugin「{p}」列在 RETIRED,但 marketplace 還有它的 entry")

    # R7 復活必須先從名冊移除,而那個移除在 diff 裡看得見
    for p in sorted(set(R_old) & live_new):
        bad.append(f"plugin「{p}」在 {ref} 是退役狀態,現在又出現在名冊裡"
                   "——要復活得先把它從 RETIRED 拿掉,那一步才看得見")

    # ---- R1:頂層 command 的內容變 → 宣告它的每個 plugin
    for c in sorted({c for cs in C_new.values() for c in cs}):
        path = f"commands/{c}"
        if blob_at(repo, ref, path) != blob_at(repo, head, path):
            for p in sorted(h for h, cs in C_new.items() if c in cs):
                why(p, f"它宣告的 command「{c}」內容變了")

    # ---- R3:plugin 自己的手寫檔(補集定義)
    for p in sorted(P_new):
        if changed := own_files_delta(repo, ref, head, p):
            why(p, "自己的手寫檔變了:" + "、".join(changed[:4])
                + (f" 等 {len(changed)} 檔" if len(changed) > 4 else ""))

    plugins = P_new
    for s in sorted({s for sk in plugins.values() for s in sk}):
        kind = classify(repo, ref, head, s)
        sv_old, sv_new = skill_version(repo, ref, s), skill_version(repo, head, s)

        # ---- 戳記凍結:內容沒變,版號就不准動。
        # 審議席(fable)指出草案把這一格寫成**豁免**,但它必須是**禁令**。
        # 放行式寫法留下的不只是漂移:它讓人「先無內容動戳記、下一張 CHG 再動內容」,
        # 把一次內容變更拆成兩個各自全綠的 diff。禁令把那條路一起封死。
        if kind == "stamp":
            bad.append(f"skill「{s}」的內容自 {ref} 起一個 byte 都沒變,"
                       f"但 metadata.version 從 {sv_old} 動到 {sv_new}"
                       "——戳記凍結:無內容的版號移動會讓同一個號碼指向兩種產物,"
                       "也讓「先動戳記、再動內容」變成兩個全綠的 diff")
            continue
        if kind != "content":
            continue

        # ---- 內容變了:skill 自己的版號必須**遞增**
        if not advanced(sv_old, sv_new):
            bad.append(f"skill「{s}」的出貨內容自 {ref} 起有變動,但 "
                       f"skills/{s}/SKILL.md 的 metadata.version 沒有遞增"
                       f"({sv_old or '(讀不到)'} → {sv_new or '(讀不到)'})")
        elif semver(sv_new) is None:
            bad.append(f"skill「{s}」的 metadata.version「{sv_new}」不是合法 semver"
                       "——「有沒有遞增」在非 semver 上判不出來")

        # ---- **每一個宿主** plugin 都要遞增。這才是本閘存在的理由。
        for h in hosts_of(plugins, s):
            e_old, e_new = old_e.get(h, ""), new_e.get(h, "")
            j_old, j_new = (plugin_json_version(repo, ref, h),
                            plugin_json_version(repo, head, h))
            # **宿主這半的 semver 格式檢查原本是空的。**
            # `advanced()` 在任一端非 semver 時退回「不同」,而我只對 skill 補了
            # 具名報錯。複審實測三案全綠:宿主 1.0.0 → "banana"、→ "0.0.1-rollback"
            # (實質倒退)、→ "1.1"(誠實打錯字)。而 catalog_check 只驗 marketplace
            # 總版號的 semver 格式,entry / plugin.json 無人驗——沒有別的閘兜底。
            # **格式檢查不看舊值,遞增檢查才看。** 兩者的例外不一樣:
            # 新 plugin 沒有「遞增」可言(舊值缺席),但它照樣得是合法 semver。
            # 二讀 probe 實測:新 plugin 帶 `"banana"` 全綠——skill 那半連新 skill
            # 都驗格式,宿主這半卻把格式也綁在舊值存在上,兩半不對稱。
            why(h, f"它打包的 skill「{s}」內容變了")

    # ---- 統一判定:**每個 plugin 只判一次版號**,紅時把全部理由列出來。
    for p in sorted(reasons):
        rs = reasons[p]
        e_old, e_new_v = old_e.get(p, ""), new_e.get(p, "")
        j_old = plugin_json_version(repo, ref, p)
        j_new = plugin_json_version(repo, head, p)
        if not rs:
            # ---- R4 驅動源全靜止,而版號動了 → **禁止**。
            #
            # 草案原本以「整棵出貨樹沒變」定義,而 plugin.json 自己就在樹裡,
            # 於是 version 一動樹就變,「樹沒變」永假,**這條規則永遠不火**
            # ——紅端不可達的禁令,實效等於 fail-open。審議席稱它是
            # 「規則在自己的定義裡自我取消」,比措辭寫鬆更難看出來。
            #
            # 改以**驅動源集合**定義之後才有紅端:名冊成分、成分指向的頂層
            # skill/command、以及自己的手寫檔(扣掉 version 鍵)——全部靜止。
            if (e_old and e_old != e_new_v) or (j_old and j_old != j_new):
                bad.append(f"plugin「{p}」的驅動源自 {ref} 起全部靜止"
                           "(名冊成分沒動、打包的 skill 與 command 內容沒動、"
                           "自己的手寫檔也沒動),"
                           f"但版號動了(entry {e_old} → {e_new_v}、"
                           f"plugin.json {j_old} → {j_new})"
                           "——無內容的版本會污染歷史,"
                           "也讓「先動版號、再動內容」變成兩個全綠的 diff")
            continue

        for label, old_v, new_v in (("entry", e_old, e_new_v),
                                    ("plugin.json", j_old, j_new)):
            if semver(new_v) is None:
                bad.append(f"plugin「{p}」的 {label} 版號「{new_v or '(空)'}」"
                           "不是合法 semver——「有沒有遞增」在非 semver 上判不出來,"
                           "而 advanced() 會退回只比「不同」,倒退與打錯字都會過")
        if not (advanced(e_old, e_new_v) and advanced(j_old, j_new)):
            bad.append(f"plugin「{p}」的版號沒有遞增"
                       f"(entry {e_old or '(缺)'} → {e_new_v or '(缺)'})"
                       f",但它有 {len(rs)} 個變更理由:" + ";".join(rs)
                       + "——已安裝的使用者拿不到這些變更")
    return bad


# ---------------------------------------------------------------- self-test
def _run(repo: Path, *args: str) -> None:
    r = git(repo, *args)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} 失敗:{r.stderr.decode('utf-8', 'replace')}")


def _mk(repo: Path, rel: str, body: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


_SKILL = "---\nname: {n}\nmetadata:\n  version: {v}\n---\n\n# {n}\n\n{body}\n"


def _registry(plugins: dict, commands: dict) -> str:
    """合成樹的 build_suite.py。**兩張名冊都要有**——閘現在兩張都讀。"""
    def blk(name, d):
        # **用雙引號,和正式的 build_suite.py 一致。** 合成夾具與真實格式不同,
        # 會讓自檢驗到一種正式樹裡不存在的形狀——這次就是這樣才發現解析器
        # 對單引號回空 dict 而非報錯。
        body = "".join(f'    "{k}": ({", ".join(repr(x) for x in v)},),\n'
                       for k, v in d.items())
        return f"{name} = {{\n{body}}}\n"
    return (f"EXCLUDE = {EXCLUDE_PARTS!r}\n"
            + blk("PLUGINS", plugins) + blk("COMMANDS", commands))


def _seed(repo: Path) -> None:
    """造一棵最小的合成樹:兩個 plugin 共用一支隨附 skill。

    **共用是重點。** 只有一個宿主的話,「同名 skill」與「全部宿主」這兩種
    判定會給出一樣的答案,而本閘要抓的正是兩者不同的那個縫。
    """
    _run(repo, "init", "-q", "-b", "main")
    _run(repo, "config", "user.email", "t@t")
    _run(repo, "config", "user.name", "t")
    # 合成樹裡的 build_suite 必須帶著**與正式檔相同**的 EXCLUDE,
    # 否則交叉斷言會在每一案都紅,把真正要驗的東西蓋掉。
    # `solo` **只在 COMMANDS、不在 PLUGINS**。這個形狀是刻意的:
    # 席位若只從 PLUGINS 種,它就進不了 R4 的視野,而名冊格式允許它存在。
    _mk(repo, "plugins/build_suite.py", _registry(
        {"alpha": ("alpha", "shared"), "beta": ("beta", "shared")},
        {"alpha": ("hello.md",), "solo": ("hello.md",)}))
    _mk(repo, "commands/hello.md", "---\ndescription: 打招呼\n---\n內容\n")
    for s in ("alpha", "beta", "shared"):
        _mk(repo, f"skills/{s}/SKILL.md", _SKILL.format(n=s, v="1.0.0", body="原文"))
    _mk(repo, "skills/shared/assets/rules.json", '{"a": 1}\n')
    for p in ("alpha", "beta", "solo"):
        _mk(repo, f"plugins/{p}/.claude-plugin/plugin.json",
            json.dumps({"name": p, "version": "1.0.0"}, ensure_ascii=False) + "\n")
    _mk(repo, ".claude-plugin/marketplace.json", json.dumps({
        "metadata": {"version": "1.0.0"},
        "plugins": [{"name": "alpha", "version": "1.0.0"},
                    {"name": "beta", "version": "1.0.0"},
                    {"name": "solo", "version": "1.0.0"}]}, ensure_ascii=False) + "\n")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "base")


def _bump_plugin(repo: Path, plugin: str, v: str) -> None:
    p = repo / ".claude-plugin/marketplace.json"
    mk = json.loads(p.read_text(encoding="utf-8"))
    for e in mk["plugins"]:
        if e["name"] == plugin:
            e["version"] = v
    p.write_text(json.dumps(mk, ensure_ascii=False) + "\n", encoding="utf-8")
    pj = repo / f"plugins/{plugin}/.claude-plugin/plugin.json"
    d = json.loads(pj.read_text(encoding="utf-8"))
    d["version"] = v
    pj.write_text(json.dumps(d, ensure_ascii=False) + "\n", encoding="utf-8")


def revival_test() -> list[str]:
    """37:**復活必須先從名冊移除**,而那個移除在 diff 裡看得見。

    這一案要三個時點(退役前 → 退役 → 復活),`case()` 的兩點模型做不到,
    所以自成一支:base 有 beta、mid 退役它、head 又把它放回名冊而 RETIRED 沒動。
    """
    import shutil
    import tempfile
    out: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        _seed(repo)
        _run(repo, "add", "-A"); _run(repo, "commit", "-q", "--allow-empty", "-m", "base")

        keep = {"alpha": ("alpha", "shared")}
        cmds = {"alpha": ("hello.md",), "solo": ("hello.md",)}
        _mk(repo, "plugins/build_suite.py",
            _registry(keep, cmds) + 'RETIRED = {\n    "beta": "CHG-TEST",\n}\n')
        shutil.rmtree(repo / "plugins" / "beta", ignore_errors=True)
        mk = repo / ".claude-plugin/marketplace.json"
        d = json.loads(mk.read_text(encoding="utf-8"))
        d["plugins"] = [e for e in d["plugins"] if e["name"] != "beta"]
        mk.write_text(json.dumps(d, ensure_ascii=False) + "\n", encoding="utf-8")
        _run(repo, "add", "-A"); _run(repo, "commit", "-q", "-m", "退役 beta")
        mid = git(repo, "rev-parse", "HEAD").stdout.decode().strip()

        # 復活:名冊放回 beta,但 RETIRED 沒動
        _mk(repo, "plugins/build_suite.py",
            _registry({"alpha": ("alpha", "shared"), "beta": ("beta", "shared")}, cmds)
            + 'RETIRED = {\n    "beta": "CHG-TEST",\n}\n')
        _run(repo, "add", "-A"); _run(repo, "commit", "-q", "-m", "復活 beta")

        got = check(repo, mid, "HEAD")
        if not any("又出現在名冊裡" in g for g in got):
            out.append(f"37 復活未被偵測——RETIRED 裡的名字回到名冊應該紅:{got}")
    return out


def aggregation_test() -> list[str]:
    """30:**聚合而非抑制**——同一 plugin 命中兩條規則時,只出一則訊息、列兩個理由。

    審議席(fable)畫的線:「絕對不要寫成『R2 已觸發就跳過 R1』——
    抑制邏輯的 bug 是**靜默綠**,fail-open 的形狀;
    聚合邏輯的 bug 最多是理由列少一條,verdict 不變。」

    案 29 只驗「有紅」,這一案驗**形狀**:alpha 的訊息必須是一則,
    而且同時含 skill 與手寫檔兩個理由。抑制式實作在這裡會露餡——
    它只會列出先觸發的那一個。
    """
    import tempfile
    out: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        _seed(repo)
        base = git(repo, "rev-parse", "HEAD").stdout.decode().strip()
        _mk(repo, "skills/shared/SKILL.md", _SKILL.format(n="shared", v="1.1.0", body="改了"))
        _mk(repo, "plugins/alpha/NOTICE", "同時也改了手寫檔\n")
        _run(repo, "add", "-A")
        _run(repo, "commit", "-q", "-m", "兩條規則")
        got = check(repo, base, "HEAD")
        mine = [g for g in got if "plugin「alpha」的版號沒有遞增" in g]
        if len(mine) != 1:
            out.append(f"30 聚合:alpha 應只出一則版號訊息,實際 {len(mine)} 則:{mine}")
        elif not ("它打包的 skill" in mine[0] and "自己的手寫檔" in mine[0]):
            out.append(f"30 聚合:兩個理由沒有同時出現在同一則訊息裡——"
                       f"這是抑制式實作的樣子:{mine[0]}")
    return out


def divergent_history_test() -> list[str]:
    """20:**分岔歷史下,無關的分支不得被牽連。**

    複審實測的誤傷:main 合法前進(某支 skill 內容變 + 全員正確 bump)之後,
    一條只動 docs 的分支跑本閘會紅三條,指控它「shared 的版號從 1.1.0 倒退到
    1.0.0」——它根本沒碰過那支 skill。成因是基準取了 ref 的 **tip** 而非分岔點。

    這一案打的是 `resolve_base`,不是 `check`——誤傷發生在基準的選擇上,
    拿寫死的 base 去跑 check 永遠重現不出來。
    """
    import tempfile
    out: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        _seed(repo)
        _run(repo, "branch", "side")

        # main 合法前進:shared 內容變,skill 與兩個宿主全部正確 bump
        _mk(repo, "skills/shared/SKILL.md", _SKILL.format(n="shared", v="1.1.0", body="改了規則"))
        _bump_plugin(repo, "alpha", "1.1.0")
        _bump_plugin(repo, "beta", "1.1.0")
        _run(repo, "add", "-A")
        _run(repo, "commit", "-q", "-m", "main 前進")

        # 無關分支:只動 docs
        _run(repo, "checkout", "-q", "side")
        _mk(repo, "docs/note.md", "與版號無關的一段字\n")
        _run(repo, "add", "-A")
        _run(repo, "commit", "-q", "-m", "只動 docs")

        tip = git(repo, "rev-parse", "main").stdout.decode().strip()
        if not check(repo, tip, "HEAD"):
            out.append("20 前置不成立:拿 main 的 tip 當基準竟然沒紅,"
                       "那這一案證明不了 merge-base 修掉了什麼")
        base = resolve_base(repo, "main")
        if base is None:
            out.append("20 resolve_base 回不出分岔點")
        elif got := check(repo, base, "HEAD"):
            out.append(f"20 分岔歷史:無關分支被牽連 {got}")
    return out


def self_test() -> int:
    import tempfile
    fails: list[str] = []

    ran: list[str] = []      # 案數用數的,不用寫死的

    def case(label: str, mutate, want: str | None):
        ran.append(label)
        # 變更必須**先 commit** 再驗——`--since` 的語意是 REF..HEAD,
        # 兩端都是 committed 狀態。拿工作樹去比 blob 會在 Windows 上
        # 因 eol 轉換全樹假陽性(初版就是這樣爆的)。
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _seed(repo)
            base = git(repo, "rev-parse", "HEAD").stdout.decode().strip()
            mutate(repo)
            _run(repo, "add", "-A")
            _run(repo, "commit", "-q", "--allow-empty", "-m", "mutate")
            got = check(repo, base, "HEAD")
            hit = any(want in g for g in got) if want else not got
            if not hit:
                fails.append(f"{label}:want={want!r} got={got}")

    # 1 綠端:什麼都沒動
    case("1 綠端:無變動", lambda r: None, None)

    # 2 **真洞的紅端**:隨附 skill 內容變,兩個宿主都沒 bump
    def m2(r):
        _mk(r, "skills/shared/SKILL.md", _SKILL.format(n="shared", v="1.1.0", body="改了規則"))
    case("2 隨附內容變、宿主未 bump", m2, "plugin「alpha」的版號沒有遞增")

    # 3 只 bump 其中一個宿主,另一個仍要紅——「有 bump 就算過」是常見的鬆脫
    def m3(r):
        m2(r)
        _bump_plugin(r, "alpha", "1.1.0")
    case("3 只 bump 一個宿主", m3, "plugin「beta」的版號沒有遞增")

    # 4 綠端:內容變且兩個宿主都 bump、skill 自己也 bump
    def m4(r):
        m2(r)
        _bump_plugin(r, "alpha", "1.1.0")
        _bump_plugin(r, "beta", "1.1.0")
    case("4 綠端:全員 bump", m4, None)

    # 5 skill 內容變但自己的版號沒動
    def m5(r):
        _mk(r, "skills/shared/SKILL.md", _SKILL.format(n="shared", v="1.0.0", body="改了規則"))
        _bump_plugin(r, "alpha", "1.1.0")
        _bump_plugin(r, "beta", "1.1.0")
    case("5 skill 內容變、skill 版號沒動", m5, "metadata.version 沒有遞增")

    # 6 **戳記凍結**:內容沒變就不准動版號。
    #   草案原本把這一格寫成豁免,審議席(fable)糾正為禁令——放行式寫法
    #   讓「先無內容動戳記、下一張 CHG 再動內容」變成兩個各自全綠的 diff。
    def m6(r):
        _mk(r, "skills/shared/SKILL.md", _SKILL.format(n="shared", v="1.1.0", body="原文"))
    case("6 戳記凍結:無內容的版號移動必紅", m6, "戳記凍結")

    # 7 assets/ 也算內容——它沒有 metadata.version 可言
    def m7(r):
        _mk(r, "skills/shared/assets/rules.json", '{"a": 2}\n')
    case("7 assets 變也算內容", m7, "plugin「alpha」的版號沒有遞增")

    # 8 刪掉一份 reference 也是內容變更(只看「現存檔有沒有改」會漏掉)
    def m8(r):
        (r / "skills/shared/assets/rules.json").unlink()
    case("8 刪檔也算內容", m8, "plugin「alpha」的版號沒有遞增")

    # 9 新增檔案同理
    def m9(r):
        _mk(r, "skills/shared/references/new.md", "新的參考\n")
    case("9 新增檔也算內容", m9, "plugin「alpha」的版號沒有遞增")

    # 10 空白變更也算——審議席明裁不做語意寬容
    def m10(r):
        _mk(r, "skills/shared/SKILL.md",
            _SKILL.format(n="shared", v="1.1.0", body="原文 "))   # 尾隨一個空格
    case("10 空白變更也算內容", m10, "plugin「alpha」的版號沒有遞增")

    # 11 **6b:三處版號分岔但內容沒變 → 刻意放行**
    #    舊的三處同步斷言會擋這個形狀;本張刻意改變不變量。
    #    寫成綠端案例,是為了讓後來的人看得出這是決定不是疏忽。
    # 11 的**機制**在 CHG-20260814-07 換過。原本靠「bump plugin 但無內容變更」
    # 來示範分岔合法,而 R4(plugin 層戳記凍結)正好禁止那個動作——
    # 案子的意圖(分岔合法)仍成立,示範它的手法不能再用被禁的那一種。
    #
    # 新機制:`shared` 內容變 → 兩個宿主都正確 bump 到 1.1.0;
    # 而 `skills/alpha/SKILL.md` 自己沒變,版號留在 1.0.0。
    # 於是 skill 1.0.0 vs plugin 1.1.0 **分岔且完全合法**,正是退役那條斷言
    # 會擋、而新規則組刻意放行的形狀。
    def m11(r):
        _mk(r, "skills/shared/SKILL.md", _SKILL.format(n="shared", v="1.1.0", body="改了規則"))
        _bump_plugin(r, "alpha", "1.1.0")
        _bump_plugin(r, "beta", "1.1.0")
    case("11 綠端:skill 版號與 plugin 版號分岔(刻意放行)", m11, None)

    # 12 非宿主的 plugin 不該被牽連
    def m12(r):
        _mk(r, "skills/alpha/SKILL.md", _SKILL.format(n="alpha", v="1.1.0", body="改了"))
        _bump_plugin(r, "alpha", "1.1.0")
    case("12 只 alpha 用的 skill 變,不得牽連 beta", m12, None)

    # 13 **版號要遞增,不是「不同」**:內容變 + 1.0.0 → 0.9.9 照字面規則會綠
    def m13(r):
        _mk(r, "skills/shared/SKILL.md", _SKILL.format(n="shared", v="0.9.9", body="改了規則"))
        _bump_plugin(r, "alpha", "0.9.9")
        _bump_plugin(r, "beta", "0.9.9")
    case("13 版號倒退不算 bump", m13, "沒有遞增")

    # 14 EXCLUDE 名單分岔的交叉斷言
    def m14(r):
        p = r / "plugins/build_suite.py"
        p.write_text(p.read_text(encoding="utf-8").replace(
            f"EXCLUDE = {EXCLUDE_PARTS!r}", "EXCLUDE = ('__pycache__',)"), encoding="utf-8")
    case("14 EXCLUDE 兩份名單分岔", m14, "EXCLUDE 名單分岔")

    # ---- 15~17 由複審(fable)的紅端 probe 打出來:**宿主這半的 semver 檢查是空的**。
    # advanced() 在任一端非 semver 時退回「不同」,而具名報錯只補在 skill 那半。
    # 這三案 fable 實測全綠,而 catalog_check 只驗 marketplace 總版號的格式,
    # entry / plugin.json 無人驗——沒有別的閘兜底。
    def _host_ver(v):
        def m(r):
            _mk(r, "skills/shared/SKILL.md", _SKILL.format(n="shared", v="1.1.0", body="改了規則"))
            _bump_plugin(r, "alpha", v)
            _bump_plugin(r, "beta", "1.1.0")
        return m
    case("15 宿主版號變成非 semver 字串", _host_ver("banana"), "不是合法 semver")
    case("16 宿主版號打錯字(1.1)", _host_ver("1.1"), "不是合法 semver")
    case("17 宿主版號實質倒退但非 semver", _host_ver("0.0.1-rollback"), "不是合法 semver")

    # 18 entry 與 plugin.json 單邊 bump——`_bump_plugin` 永遠兩處一起動,
    #    這一案把它們拆開,釘住「只動一處不算」。
    def m18(r):
        _mk(r, "skills/shared/SKILL.md", _SKILL.format(n="shared", v="1.1.0", body="改了規則"))
        _bump_plugin(r, "beta", "1.1.0")
        p = r / ".claude-plugin/marketplace.json"      # 只動 entry,不動 plugin.json
        mk = json.loads(p.read_text(encoding="utf-8"))
        for e in mk["plugins"]:
            if e["name"] == "alpha":
                e["version"] = "1.1.0"
        p.write_text(json.dumps(mk, ensure_ascii=False) + "\n", encoding="utf-8")
    case("18 entry 與 plugin.json 單邊 bump", m18, "plugin「alpha」的版號沒有遞增")

    # 19 **正文裡的 version: 行是內容,不是戳記。**
    #    初版剝的是全檔任何符合的行,於是正文改一行 `version:` 會被判成
    #    「一個 byte 都沒變」的戳記紅——而戳記紅無論怎麼 bump 都過不了,是死鎖。
    def m19(r):
        _mk(r, "skills/shared/SKILL.md",
            _SKILL.format(n="shared", v="1.0.0", body="用法:\n  version: v2"))
    case("19 正文的 version 行算內容不算戳記", m19, "metadata.version 沒有遞增")

    # 21 **新 plugin 也要是合法 semver**。二讀 probe 實測這裡原本全綠:
    #    格式檢查被綁在「舊值存在」上,而新 plugin 的舊值當然不存在。
    #    遞增檢查對新 plugin 豁免是對的,格式檢查跟著豁免就不對了。
    def m21(r):
        _mk(r, "skills/shared/SKILL.md", _SKILL.format(n="shared", v="1.1.0", body="改了規則"))
        _bump_plugin(r, "alpha", "1.1.0")
        _bump_plugin(r, "beta", "1.1.0")
        # gamma 是這一趟才出現的新 plugin,版號非 semver。
        # 名冊直接重寫,不做字串替換——替換目標一改格式就靜默打不中,
        # 而打不中的後果是「案子還在、但它驗的東西不見了」。
        _mk(r, "plugins/build_suite.py", _registry(
            {"alpha": ("alpha", "shared"), "beta": ("beta", "shared"),
             "gamma": ("shared",)},
            {"alpha": ("hello.md",), "solo": ("hello.md",)}))
        _mk(r, "plugins/gamma/.claude-plugin/plugin.json",
            json.dumps({"name": "gamma", "version": "banana"}, ensure_ascii=False) + "\n")
        mk = r / ".claude-plugin/marketplace.json"
        d = json.loads(mk.read_text(encoding="utf-8"))
        d["plugins"].append({"name": "gamma", "version": "banana"})
        mk.write_text(json.dumps(d, ensure_ascii=False) + "\n", encoding="utf-8")
    case("21 新 plugin 的非 semver 版號", m21, "不是合法 semver")

    # ---- 22~29:CHG-20260814-07 的 plugin 層規則。

    # 22 R2:從 PLUGINS 的 tuple 移除一支 skill(宿主出貨樹少一整支)
    def m22(r):
        _mk(r, "plugins/build_suite.py", _registry(
            {"alpha": ("alpha",), "beta": ("beta", "shared")},
            {"alpha": ("hello.md",), "solo": ("hello.md",)}))
    case("22 R2:PLUGINS 移除一支 skill", m22, "PLUGINS 成分變了")

    # 23 R2:把既有 skill 掛進新宿主
    def m23(r):
        _mk(r, "plugins/build_suite.py", _registry(
            {"alpha": ("alpha", "shared"), "beta": ("beta", "shared", "alpha")},
            {"alpha": ("hello.md",), "solo": ("hello.md",)}))
    case("23 R2:既有 skill 掛進新宿主", m23, "PLUGINS 成分變了")

    # 24 R2:COMMANDS 成分變更——批量搬遷要改它五次,而它原本完全沒被讀
    def m24(r):
        _mk(r, "commands/bye.md", "---\ndescription: 道別\n---\n內容\n")
        _mk(r, "plugins/build_suite.py", _registry(
            {"alpha": ("alpha", "shared"), "beta": ("beta", "shared")},
            {"alpha": ("hello.md", "bye.md"), "solo": ("hello.md",)}))
    case("24 R2:COMMANDS 成分變更", m24, "COMMANDS 成分變了")

    # 25 R1:頂層 command 的內容變 → 宣告它的 plugin 必須遞增
    def m25(r):
        _mk(r, "commands/hello.md", "---\ndescription: 打招呼\n---\n改過的內容\n")
    case("25 R1:command 內容變", m25, "它宣告的 command「hello.md」內容變了")

    # 26 R3:plugin 自己的手寫檔。用一個**沒被任何列舉提過**的檔名,
    #    證明範圍是補集而不是白名單——列舉式會讓它靜默漏網。
    def m26(r):
        _mk(r, "plugins/alpha/NOTICE", "第三方聲明\n")
    case("26 R3:未列舉過的手寫檔(NOTICE)", m26, "自己的手寫檔變了")

    # 27 **R4 的紅端。這一案是本張最不可妥協的一條。**
    #    草案以「整棵出貨樹沒變」定義 R4,而 plugin.json 自己就在樹裡,
    #    於是 version 一動樹就變,條件永假、規則永遠不火——
    #    紅端不可達的禁令,實效等於 fail-open。改以驅動源定義才打得出這一案。
    def m27(r):
        _bump_plugin(r, "alpha", "1.4.0")     # 驅動源全靜止,只有版號動
    case("27 R4:驅動源全靜止而版號動(plugin 層戳記凍結)", m27, "驅動源")

    # 28 R4 的綠端:驅動源有變時 R4 不得開火
    def m28(r):
        _mk(r, "plugins/alpha/NOTICE", "新檔\n")
        _bump_plugin(r, "alpha", "1.1.0")
    case("28 R4 綠端:驅動源有變就不是戳記", m28, None)

    # 29 **理由聚合**:同一個 plugin 同時命中兩條規則,版號只判一次,
    #    而且兩個理由都要出現在同一則訊息裡。
    def m29(r):
        _mk(r, "skills/shared/SKILL.md", _SKILL.format(n="shared", v="1.1.0", body="改了"))
        _mk(r, "plugins/alpha/NOTICE", "同時也改了手寫檔\n")
    case("29 理由聚合:兩條規則命中同一 plugin", m29, "它打包的 skill")

    # 31 frontmatter **頂層**的 version 鍵是內容,不是戳記。
    #    複審實測:剝「frontmatter 內任何 version:」會讓這個形狀被判成戳記,
    #    訊息說「metadata.version 從 1.0.0 動到 1.0.0」——胡話,而且怎麼 bump
    #    都過不了(案 19 死鎖的 frontmatter 版)。
    def m31(r):
        _mk(r, "skills/shared/SKILL.md",
            "---\nname: shared\nversion: 0.2\nmetadata:\n  version: 1.0.0\n---\n\n# shared\n")
    case("31 frontmatter 頂層 version 鍵算內容", m31, "metadata.version 沒有遞增")

    # ---- 32、33:複審 probe 打到的兩處,各自的紅端。

    # 32 P1:只在 COMMANDS、不在 PLUGINS 的 plugin,R4 也必須看得到它。
    #    席位若只從 PLUGINS 種,這個形狀的紅端永遠不可達。
    def m32(r):
        _bump_plugin(r, "solo", "1.1.0")     # 驅動源全靜止,只動版號
    case("32 只在 COMMANDS 的 plugin,R4 也要看得到", m32, "驅動源")

    # 33 P5:plugin.json 的**純格式重排**——byte 變、JSON 語意同、version 沒動。
    #    初版的 JSON 比對把所有語意等價的 byte 噪音一併豁免,不只 version 鍵。
    def m33(r):
        p = r / "plugins/alpha/.claude-plugin/plugin.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    case("33 plugin.json 純格式重排也算內容", m33, "自己的手寫檔變了")

    # ---- 34~37:**消失也要看得見**(CHG-20260814-10)。
    #
    # 審議席的警告寫在這裡:綠端的合成樹**必須把 plugin 目錄與 marketplace 條目
    # 一起刪乾淨**,否則 R6 會讓綠端不可達——而「綠端不可達」會用最難看的方式
    # 被發現(整批案子永遠紅,而你以為是規則太嚴)。
    import shutil

    def _retire(r, names, tombstone=True, wipe=True):
        keep = {k: v for k, v in
                {"alpha": ("alpha", "shared"), "beta": ("beta", "shared")}.items()
                if k not in names}
        cmds = {k: v for k, v in
                {"alpha": ("hello.md",), "solo": ("hello.md",)}.items()
                if k not in names}
        src = _registry(keep, cmds)
        if tombstone:
            src += ("RETIRED = {\n" + "".join(
                f'    "{n}": "CHG-TEST",\n' for n in names) + "}\n")
        _mk(r, "plugins/build_suite.py", src)
        if wipe:
            for n in names:
                shutil.rmtree(r / "plugins" / n, ignore_errors=True)
                mk = r / ".claude-plugin/marketplace.json"
                d = json.loads(mk.read_text(encoding="utf-8"))
                d["plugins"] = [e for e in d["plugins"] if e["name"] != n]
                mk.write_text(json.dumps(d, ensure_ascii=False) + "\n", encoding="utf-8")

    case("34 R5:刪了卻沒列進 RETIRED",
         lambda r: _retire(r, ["beta"], tombstone=False), "沒有列進 RETIRED")
    case("35 R5 綠端:刪了且具名(目錄與 marketplace 都清乾淨)",
         lambda r: _retire(r, ["beta"]), None)
    case("36 R6:列進 RETIRED 卻沒真的退役",
         lambda r: _mk(r, "plugins/build_suite.py",
                       _registry({"alpha": ("alpha", "shared"), "beta": ("beta", "shared")},
                                 {"alpha": ("hello.md",), "solo": ("hello.md",)})
                       + 'RETIRED = {\n    "beta": "CHG-TEST",\n}\n'),
         "具名了卻沒真的退役")

    fails += revival_test()
    fails += aggregation_test()
    fails += divergent_history_test()
    # **加了獨立測試就要登記在這裡。** 動態計數只保證「數對了 ran 的長度」,
    # 保證不了「EXTRA 名單與實際呼叫一致」——這一行漏了 revival_test,
    # 橫幅就少算一案,而那正是寫死數字的病換了個位置。
    EXTRA = ("理由聚合", "分岔歷史", "退役復活")

    if fails:
        for f in fails:
            print(f"  ❌ {f}")
        print("\n✗ self-test 未通過:版號影響閘的紅綠端不可達。")
        return 1
    # **案數是數出來的,不是寫死的。**
    # 寫死的數字每加一案就要記得改,而漏改的後果不是少報——是
    # 「橫幅說 30、實際 31」,然後那個數字被抄進 ACC 當引文。
    # 這個 repo 已經為「宣稱沒有對過量測」付過三次代價。
    print(f"✅ self-test:{len(ran) + len(EXTRA)} 案全過"
          f"({len(ran)} 個 case + {len(EXTRA)} 支獨立測試:{'、'.join(EXTRA)})\n"
          "  [skill 層]\n"
          "   真洞五條:隨附內容變 / 只 bump 一個宿主 / assets 變 / 刪檔 / 新增檔\n"
          "   綠端四條:無變動 / 全員 bump / 版號分岔但內容沒變(刻意放行) / 非宿主不牽連\n"
          "   戳記凍結一條、skill 自身版號一條、空白不寬容一條、版號倒退一條\n"
          "   EXCLUDE 交叉斷言一條\n"
          "   宿主 semver 三條(非 semver 字串 / 打錯字 1.1 / 非 semver 的實質倒退)\n"
          "   entry 與 plugin.json 單邊 bump 一條\n"
          "   正文的 version 行算內容一條\n"
          "   分岔歷史下無關分支不得被牽連一條\n"
          "   新 plugin 的非 semver 版號一條\n"
          "  [plugin 層,CHG-20260814-07]\n"
          "   R2 成分變更三條(PLUGINS 移除 / 掛進新宿主 / COMMANDS 變更)\n"
          "   R1 command 內容變一條\n"
          "   R3 未列舉過的手寫檔一條(補集定義,不是白名單)\n"
          "   R4 兩條(驅動源全靜止而版號動必紅 / 驅動源有變不得誤判為戳記)\n"
          "   理由聚合兩條(有紅一條、**同一則訊息含兩個理由**一條)\n"
          "   frontmatter 頂層 version 鍵算內容一條")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    repo = Path(".").resolve()
    if "--repo" in argv:
        repo = Path(argv[argv.index("--repo") + 1]).resolve()
    want = argv[argv.index("--since") + 1] if "--since" in argv else "origin/main"
    ref = resolve_base(repo, want)
    if ref is None:
        # **取不到基準預設是紅的,不是綠的。**
        #
        # `catalog_check.check_since` 在同樣情境下 `return []`(「略過此檢查,不誤殺」)。
        # 那在它身上還說得過去——它只是版本紀律的其中一道。但解耦之後,
        # **整個版本紀律都押在 diff 式的閘上**,fail-open 就從方便變成承重牆的裂縫:
        # CI 只要 fetch 失敗,全部版號規則靜靜消失,而輸出看起來和通過一樣。
        #
        # 審議席(fable)的裁決:CI 裡必須硬紅,fetch 是 CI 自己的責任;
        # skip 只留給本地,而且要顯式要求。
        if "--allow-missing-ref" in argv:
            print(f"⚠️  取不到「{want}」的分岔點——本閘**未驗到**,不是通過"
                  "(--allow-missing-ref 只該用在本地)")
            return 0
        print(f"✗ 取不到「{want}」的分岔點(merge-base)——版本紀律全押在本閘上,"
              "取不到基準等於整套規則消失。\n"
              "  CI 請先 `git fetch origin main`。\n"
              "  **若分岔點早於淺 fetch 的深度**(CI 用 --depth=50),"
              "訊息會長得跟「沒 fetch」一樣,\n"
              "  但要下的是 `git fetch --deepen=200 origin main`(或 --unshallow)。\n"
              "  本地要略過請顯式加 --allow-missing-ref。")
        return 1
    bad = check(repo, ref)
    if bad:
        print(f"✗ 版號影響閘(基準 {ref}):")
        for b in bad:
            print("  - " + b)
        print("\n  判準:skill 的整棵出貨樹(SKILL.md / assets / references / scripts)"
              "\n  任一 byte 變動即為內容變更,只排除根 SKILL.md 的 version 那一行。"
              "\n  內容變了,打包它的每一個 plugin 都要 bump——包括隨附進去的那些。")
        return 1
    print(f"✅ 版號影響閘(基準 {ref}):skill 內容變更沒有漏掉宿主 bump,"
          "plugin 層的成分變更 / 手寫檔 / command 內容也都有對應的版號,"
          "且沒有無驅動源的版號移動")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
