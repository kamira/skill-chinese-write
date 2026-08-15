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
    head = [ln for ln in lines[1:end] if not VERSION_LINE.match(ln)]
    return b"\n".join([lines[0], *head, *lines[end:]])


def skill_files(repo: Path, skill: str) -> list[str]:
    base = repo / "skills" / skill
    if not base.is_dir():
        return []
    return sorted(p.relative_to(repo).as_posix() for p in base.rglob("*")
                  if p.is_file() and not any(x in p.parts for x in EXCLUDE_PARTS))


def load_plugins(repo: Path) -> dict[str, tuple[str, ...]]:
    """從 build_suite.py 讀 PLUGINS——**單一登記簿,不另抄一份**。

    抄一份就會分岔,而「兩份名冊分岔」正是這個 repo 出過孤兒事故的原因。
    """
    src = (repo / "plugins" / "build_suite.py").read_text(encoding="utf-8")
    m = re.search(r"^PLUGINS[^=]*=\s*\{(.*?)^\}", src, re.S | re.M)
    if not m:
        raise SystemExit("讀不到 build_suite.py 的 PLUGINS——名冊形狀變了,本閘失效")
    out: dict[str, tuple[str, ...]] = {}
    for e in re.finditer(r'"([\w.-]+)"\s*:\s*\(([^)]*)\)', m.group(1)):
        out[e.group(1)] = tuple(x.strip().strip("'\"")
                                for x in e.group(2).split(",") if x.strip())
    return out


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


def check(repo: Path, ref: str, head: str = "HEAD") -> list[str]:
    plugins = load_plugins(repo)
    old_e, new_e = entry_versions(repo, ref), entry_versions(repo, head)
    bad: list[str] = exclude_drift(repo)

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
            # 舊值缺席不報:那是**新 plugin**,它沒有「遞增」可言。
            for label, old_v, new_v in (("entry", e_old, e_new),
                                        ("plugin.json", j_old, j_new)):
                if old_v and semver(new_v) is None:
                    bad.append(f"plugin「{h}」的 {label} 版號「{new_v or '(空)'}」"
                               "不是合法 semver——「有沒有遞增」在非 semver 上判不出來,"
                               "而 advanced() 會退回只比「不同」,倒退與打錯字都會過")
            e_ok = advanced(e_old, e_new)
            j_ok = advanced(j_old, j_new)
            if not (e_ok and j_ok):
                bad.append(f"skill「{s}」的內容變了,而它被 plugin「{h}」打包出貨,"
                           f"但 {h} 的版號沒有遞增"
                           f"(entry {old_e.get(h, '?')} → {new_e.get(h, '?')})"
                           f"——已安裝 {h} 的使用者拿不到這個變更")
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
    _mk(repo, "plugins/build_suite.py",
        f"EXCLUDE = {EXCLUDE_PARTS!r}\n"
        'PLUGINS = {\n    "alpha": (\'alpha\', \'shared\'),\n'
        '    "beta": (\'beta\', \'shared\'),\n}\n')
    for s in ("alpha", "beta", "shared"):
        _mk(repo, f"skills/{s}/SKILL.md", _SKILL.format(n=s, v="1.0.0", body="原文"))
    _mk(repo, "skills/shared/assets/rules.json", '{"a": 1}\n')
    for p in ("alpha", "beta"):
        _mk(repo, f"plugins/{p}/.claude-plugin/plugin.json",
            json.dumps({"name": p, "version": "1.0.0"}, ensure_ascii=False) + "\n")
    _mk(repo, ".claude-plugin/marketplace.json", json.dumps({
        "metadata": {"version": "1.0.0"},
        "plugins": [{"name": "alpha", "version": "1.0.0"},
                    {"name": "beta", "version": "1.0.0"}]}, ensure_ascii=False) + "\n")
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

    def case(label: str, mutate, want: str | None):
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
    case("2 隨附內容變、宿主未 bump", m2, "plugin「alpha」打包出貨")

    # 3 只 bump 其中一個宿主,另一個仍要紅——「有 bump 就算過」是常見的鬆脫
    def m3(r):
        m2(r)
        _bump_plugin(r, "alpha", "1.1.0")
    case("3 只 bump 一個宿主", m3, "plugin「beta」打包出貨")

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
    case("7 assets 變也算內容", m7, "plugin「alpha」打包出貨")

    # 8 刪掉一份 reference 也是內容變更(只看「現存檔有沒有改」會漏掉)
    def m8(r):
        (r / "skills/shared/assets/rules.json").unlink()
    case("8 刪檔也算內容", m8, "plugin「alpha」打包出貨")

    # 9 新增檔案同理
    def m9(r):
        _mk(r, "skills/shared/references/new.md", "新的參考\n")
    case("9 新增檔也算內容", m9, "plugin「alpha」打包出貨")

    # 10 空白變更也算——審議席明裁不做語意寬容
    def m10(r):
        _mk(r, "skills/shared/SKILL.md",
            _SKILL.format(n="shared", v="1.1.0", body="原文 "))   # 尾隨一個空格
    case("10 空白變更也算內容", m10, "plugin「alpha」打包出貨")

    # 11 **6b:三處版號分岔但內容沒變 → 刻意放行**
    #    舊的三處同步斷言會擋這個形狀;本張刻意改變不變量。
    #    寫成綠端案例,是為了讓後來的人看得出這是決定不是疏忽。
    def m11(r):
        _bump_plugin(r, "alpha", "1.4.0")      # plugin 跳到 1.4.0
        # skills/alpha/SKILL.md 仍停在 1.0.0 —— 正是 writing 那次的形狀
    case("11 綠端:版號分岔但內容沒變(刻意放行)", m11, None)

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
    case("18 entry 與 plugin.json 單邊 bump", m18, "plugin「alpha」打包出貨")

    # 19 **正文裡的 version: 行是內容,不是戳記。**
    #    初版剝的是全檔任何符合的行,於是正文改一行 `version:` 會被判成
    #    「一個 byte 都沒變」的戳記紅——而戳記紅無論怎麼 bump 都過不了,是死鎖。
    def m19(r):
        _mk(r, "skills/shared/SKILL.md",
            _SKILL.format(n="shared", v="1.0.0", body="用法:\n  version: v2"))
    case("19 正文的 version 行算內容不算戳記", m19, "metadata.version 沒有遞增")

    fails += divergent_history_test()

    if fails:
        for f in fails:
            print(f"  ❌ {f}")
        print("\n✗ self-test 未通過:版號影響閘的紅綠端不可達。")
        return 1
    print("✅ self-test:20 案全過\n"
          "   真洞五條:隨附內容變 / 只 bump 一個宿主 / assets 變 / 刪檔 / 新增檔\n"
          "   綠端四條:無變動 / 全員 bump / 版號分岔但內容沒變(刻意放行) / 非宿主不牽連\n"
          "   戳記凍結一條、skill 自身版號一條、空白不寬容一條、版號倒退一條\n"
          "   EXCLUDE 交叉斷言一條\n"
          "   宿主 semver 三條(非 semver 字串 / 打錯字 1.1 / 非 semver 的實質倒退)\n"
          "   entry 與 plugin.json 單邊 bump 一條\n"
          "   正文的 version 行算內容一條\n"
          "   分岔歷史下無關分支不得被牽連一條")
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
              "  CI 請先 `git fetch origin main`;本地要略過請顯式加 --allow-missing-ref。")
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
    print(f"✅ 版號影響閘(基準 {ref}):沒有 skill 的內容變更漏掉宿主 bump")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
