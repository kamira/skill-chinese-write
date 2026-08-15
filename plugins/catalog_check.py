#!/usr/bin/env python3
"""
catalog_check.py — marketplace catalog 版本治理(唯讀;不改任何檔)

兩種檢查:
  --check        靜態(git-free,恆守):
                   1) marketplace metadata.version 為合法 semver
                   2) 每個 plugin 的 marketplace entry.version == 該 plugin .claude-plugin/plugin.json 的 version
                      (防 entry 與 plugin 版本分岔)
  --since <REF>  git-aware(變動必 bump):<REF>..HEAD 若動到 plugins/ 或 skills/ 的實質內容,
                   marketplace metadata.version 必須與 <REF> 當時不同——否則「plugin 變了卻沒 bump catalog」→ 擋。
                   <REF> 無法解析(未 fetch 等)→ 印說明並 exit 0(不誤殺)。

用法:
  python3 plugins/catalog_check.py --check
  python3 plugins/catalog_check.py --since origin/main
  python3 plugins/catalog_check.py --repo . --check --since origin/main

退出碼:0 通過 | 1 檢查未過 | 2 環境/參數錯誤
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# 釘住輸出編碼(CHG-20260803-01 T1):不依賴主控台/locale 的 ambient 編碼。
# 非 UTF-8 主控台(如 Windows cp932)印 CJK/emoji 會 UnicodeEncodeError;
# 釘住後同一份程式在任何平台的輸出行為一致。errors="replace" 確保永不因輸出而崩潰。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
MARKET_REL = ".claude-plugin/marketplace.json"


def git(repo: Path, *args: str):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def load_marketplace(repo: Path) -> dict:
    return json.loads((repo / MARKET_REL).read_text(encoding="utf-8"))


def market_version(mk: dict) -> str:
    return str(mk.get("metadata", {}).get("version", ""))


def plugin_source_dir(repo: Path, entry: dict) -> Path:
    src = str(entry.get("source", "")).lstrip("./")  # "./plugins/ai-sdlc-suite"
    return repo / src


SKILL_VER_RE = re.compile(r"^metadata:\s*$\s*^\s+version:\s*(\S+)\s*$", re.M)


def skills_of(repo: Path, plugin: str) -> list[Path]:
    """該 plugin 打包的 skill 本體(頂層 skills/ 才是單一真相,plugin 內是生成物)。
    找不到就回空——不是每個 plugin 都必然有同名 skill,缺席不該被誤判成分岔。"""
    return [p for p in [repo / "skills" / plugin / "SKILL.md"] if p.is_file()]


def skill_version(skill_md: Path) -> str | None:
    m = SKILL_VER_RE.search(skill_md.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def check_static(repo: Path) -> list[str]:
    problems = []
    mk = load_marketplace(repo)
    mv = market_version(mk)
    if not SEMVER_RE.match(mv):
        problems.append(f"marketplace metadata.version「{mv}」非合法 semver(X.Y.Z)")
    for entry in mk.get("plugins", []):
        name = entry.get("name", "?")
        ev = str(entry.get("version", ""))
        pj = plugin_source_dir(repo, entry) / ".claude-plugin" / "plugin.json"
        if not pj.is_file():
            problems.append(f"plugin「{name}」找不到 {pj.relative_to(repo)}")
            continue
        try:
            pjv = str(json.loads(pj.read_text(encoding="utf-8")).get("version", ""))
        except json.JSONDecodeError as e:
            problems.append(f"plugin「{name}」plugin.json 解析失敗:{e}")
            continue
        if ev != pjv:
            problems.append(f"plugin「{name}」marketplace entry.version={ev} ≠ plugin.json version={pjv}(版本分岔)")
        # ---- 第三處(skill 本體的 metadata.version)已於 CHG-20260814-06 **退役**。
        #
        # 它曾抓到真東西:writing 在 SKILL.md 停在 1.3.0、另外兩處是 1.4.0,
        # 全綠地活了一輪。但它把 **skill 版號**與 **plugin 版號**綁死,而那個綁定
        # 兩個方向都錯:
        #   - plugin 因為多了一個 command 而 bump 時,skill 版號被迫跟跳
        #     (CHG-20260814-05:fiction skill 內容一個字沒改,戳記卻從 1.0.0 跳到
        #      1.1.0,再被 byte-sync 灌進六個宿主副本,逼出六個無內容版本)
        #   - 反過來,skill 內容真的變時,打包它的其他宿主 plugin 卻**不必動**
        #     ——zh-style 被全部 21 個 plugin 打包,那才是 A(a) 級的傷害,
        #       而這條斷言完全看不見
        #
        # **這不是嚴格更強的替換,是刻意改變不變量**(審議席 codex 的原話)。
        # 「三處分岔」從此合法。接手的是 scripts/version_impact_check.py:
        #   內容變   → skill 自己與**全部宿主**都必須 semver 遞增
        #   內容沒變 → 版號**禁止**移動(戳記凍結)
        # 副本一致性則由 build_suite --check 的 byte 比對接手。
        #
        # 殘餘風險,白紙黑字記著:**base 上已經存在的分岔,任何 diff 式的閘都看不見。**
        # writing 那次若發生在新閘上線之前,新規則組同樣抓不到。這是有意識接受的,
        # 靠戳記凍結保證它從此無法被**引入**。
        _ = (skills_of, skill_version)     # 保留兩支工具,供 version_impact_check 之外的用途
    return problems


# `plugins/` 頂層唯二不是 plugin 的東西——**就地複製,不 import**。
# 兩支治理工具須各自可獨立執行(審議席指定);名單漂移由 self-test 的交叉斷言攔住。
# 單一真相在 `scripts/skill_inventory_check.py` 的同名常數。
TOP_TOOL_FILES = {"build_suite.py", "catalog_check.py"}


def needs_bump(changed: list[str]) -> list[str]:
    """從 diff 檔名清單篩出**真的會改變出貨內容**的那些。純函式,好測。

    為什麼要排除 `TOP_TOOL_FILES`(CHG-20260814-03,審議席裁決):
    原條件是 `startswith(("plugins/","skills/"))` 只排 README.md,於是改建置工具
    `plugins/build_suite.py` 也會強制 bump marketplace 版號——**但出貨內容一個 byte 都沒變**
    (`build_suite --check` = 0)。這條規則甚至會**對 catalog_check.py 自己開火**。
    規則寫得比意圖寬,擋住了不該擋的;零出貨變動卻 bump,還會製造無內容版本、
    污染版本歷史、讓消費端誤判有新發布。

    **用名單排除,不用路徑深度**:深度規則會把未列名的 `plugins/` 頂層異常檔靜默放過,
    而那正是孤兒事故的形狀。分類依據是既有語意(TOP_TOOL_FILES),不是目錄層數。
    """
    out = []
    for f in changed:
        f = f.strip()
        if not f.startswith(("plugins/", "skills/")):
            continue
        parts = f.split("/")
        if f.rsplit("/", 1)[-1] == "README.md":
            continue                                  # 純敘述,不影響 plugin 行為
        if len(parts) == 2 and parts[0] == "plugins" and parts[1] in TOP_TOOL_FILES:
            continue                                  # 治理工具,不出貨
        out.append(f)
    return out


def check_since(repo: Path, ref: str) -> list[str]:
    if not (repo / ".git").exists():
        print("(--since:非 git repo,略過)")
        return []
    if git(repo, "rev-parse", "--verify", "--quiet", ref).returncode != 0:
        print(f"(--since:無法解析 ref「{ref}」——未 fetch base?略過此檢查,不誤殺)")
        return []
    diff = git(repo, "diff", "--name-only", f"{ref}..HEAD")
    if diff.returncode != 0:
        print(f"(--since:git diff 失敗,略過:{diff.stderr.strip()[:100]})")
        return []
    # plugins/skills 下的實質內容變動;排除純 README.md 敘述(不影響 plugin 行為)
    content_changed = needs_bump(diff.stdout.splitlines())
    if not content_changed:
        return []
    old = git(repo, "show", f"{ref}:{MARKET_REL}")
    if old.returncode != 0:
        print(f"(--since:{ref} 無 marketplace.json,視為新增,略過)")
        return []
    try:
        old_mv = market_version(json.loads(old.stdout))
    except json.JSONDecodeError:
        print("(--since:base marketplace.json 解析失敗,略過)")
        return []
    cur_mv = market_version(load_marketplace(repo))
    # **「遞增」不是「不同」。** 本行原本寫 `old_mv == cur_mv`,於是
    # 1.2.0 → 1.1.0 這種倒退照過——正是 CHG-20260814-06 在 version_impact_check
    # 那半被糾正過的同一型病,原樣活在這裡。CHG-20260814-07 一併修。
    a, b = _semver(old_mv), _semver(cur_mv)
    advanced = (b > a) if (a and b) else (old_mv != cur_mv)
    if not advanced:
        sample = ", ".join(content_changed[:5])
        how = "未 bump" if old_mv == cur_mv else f"沒有遞增({old_mv} → {cur_mv})"
        return [f"plugins/skills 內容自 {ref} 起有變動但 marketplace metadata.version {how}"
                f"(現為 {cur_mv})——每次 plugin 變動須同步 bump catalog(觸發檔:{sample} …)"
                f"\n    修正:python3 plugins/catalog_check.py --bump {ref}(自動推導,不必人挑版號)"]
    if a is None or b is None:
        return [f"marketplace metadata.version「{cur_mv}」不是合法 semver"
                "——「有沒有遞增」在非 semver 上判不出來,會退回只比「不同」"]
    return []


# ---------- --bump:自動推導版號(唯一會寫檔的模式) ----------

def _semver(v: str):
    return tuple(int(x) for x in v.split(".")) if SEMVER_RE.match(v) else None


def bump_catalog(repo: Path, ref: str) -> int:
    """以 REF 的 catalog 版號為基準推導本地版號。

    規則:local <= ref → bump_minor(ref);local > ref → 不動(冪等,已正確 bump 過就不再推)。
    人挑版號會對著一個會過期的基底,合併時才發現撞號——改由此處對 REF 現況算出。
    """
    if git(repo, "rev-parse", "--verify", "--quiet", ref).returncode != 0:
        print(f"❌ --bump:無法解析 ref「{ref}」——先 `git fetch origin main`。")
        return 2
    old = git(repo, "show", f"{ref}:{MARKET_REL}")
    if old.returncode != 0:
        print(f"(--bump:{ref} 無 marketplace.json,視為新增,不動。)")
        return 0
    try:
        ref_mv = market_version(json.loads(old.stdout))
    except json.JSONDecodeError:
        print("❌ --bump:base marketplace.json 解析失敗。")
        return 2
    cur_mv = market_version(load_marketplace(repo))
    rv, cv = _semver(ref_mv), _semver(cur_mv)
    if rv is None or cv is None:
        print(f"❌ --bump:版號非合法 semver(ref={ref_mv} local={cur_mv})。")
        return 2
    if cv > rv:
        print(f"✅ --bump:本地 {cur_mv} 已高於 {ref} 的 {ref_mv},無需變更(冪等)。")
        return 0
    new_mv = f"{rv[0]}.{rv[1] + 1}.0"
    path = repo / MARKET_REL
    text = path.read_text(encoding="utf-8")
    # 只改 metadata 區塊內的 version,不動 plugin entry、不重排 JSON
    new_text, n = re.subn(r'("metadata"\s*:\s*\{.*?"version"\s*:\s*")[^"]+(")',
                          lambda m: m.group(1) + new_mv + m.group(2), text, count=1, flags=re.S)
    if n != 1:
        print("❌ --bump:找不到 metadata.version 欄位,未改任何內容。")
        return 2
    path.write_text(new_text, encoding="utf-8")
    if market_version(load_marketplace(repo)) != new_mv:
        print("❌ --bump:改寫後驗證失敗。")
        return 2
    print(f"✅ --bump:catalog {cur_mv} → {new_mv}(基準 {ref}={ref_mv})。")
    return 0


BUMP_CASES = [
    # (檔名, 該不該要求 bump, 為什麼)
    ("plugins/writing/skills/writing/SKILL.md", True, "真的出貨內容"),
    ("plugins/fiction/.claude-plugin/plugin.json", True, "plugin manifest 也是出貨物"),
    ("skills/writing/assets/style_rules.json", True, "單一真相變了,出貨物跟著變"),
    ("plugins/build_suite.py", False, "建置工具,不出貨"),
    ("plugins/catalog_check.py", False, "同上——這條規則原本會對自己開火"),
    ("plugins/writing/README.md", False, "純敘述,不影響 plugin 行為"),
    ("plugins/stray.py", True, "**未列名**的 plugins/ 頂層檔:名單而非深度的存在理由"),
    ("docs/writing/changes/CHG-1.md", False, "不在 plugins/ 或 skills/ 底下"),
    (".github/ci_local.sh", False, "同上"),
]


def self_test() -> int:
    """`--since` 觸發條件的紅綠端 + 名單交叉斷言(CHG-20260814-03,審議席指定)。"""
    fails = []
    for f, want, why in BUMP_CASES:
        hit = bool(needs_bump([f]))
        if hit != want:
            fails.append(f"「{f}」預期{'要' if want else '不'}觸發、實際"
                         f"{'觸發' if hit else '不觸發'}({why})")

    # 交叉斷言:兩支治理工具各自持有一份名單(刻意不 import,兩者須能獨立執行),
    # 所以名單漂移必須有東西攔。這裡就是那個東西。
    peer = Path(__file__).resolve().parent.parent / "scripts" / "skill_inventory_check.py"
    if peer.is_file():
        m = re.search(r"^TOP_TOOL_FILES\s*=\s*\{([^}]*)\}",
                      peer.read_text(encoding="utf-8"), re.M)
        if not m:
            fails.append(f"在 {peer.name} 找不到 TOP_TOOL_FILES——交叉斷言失效")
        else:
            peer_set = {x.strip().strip('"\'') for x in m.group(1).split(",") if x.strip()}
            if peer_set != TOP_TOOL_FILES:
                fails.append(f"TOP_TOOL_FILES 兩邊不一致:本檔 {sorted(TOP_TOOL_FILES)} vs "
                             f"{peer.name} {sorted(peer_set)}——名單漂移")
    else:
        fails.append(f"找不到 {peer}——交叉斷言無法執行,等於沒有")

    fails += static_self_test()
    fails += since_version_self_test()

    if fails:
        for f in fails:
            print(f"  ❌ {f}")
        print("\n✗ self-test 未通過。")
        return 1
    print(f"✅ self-test:--since 觸發條件 {len(BUMP_CASES)} 案全對"
          f"(含未列名的 plugins/ 頂層檔仍觸發),"
          f"TOP_TOOL_FILES 與 skill_inventory_check 一致,"
          f"check_static 兩案(entry≠plugin.json 必紅、"
          f"SKILL.md 與 plugin.json 分岔必綠),"
          f"且總版號遞增兩案(倒退必紅、正確遞增必綠)。")
    return 0


def since_version_self_test() -> list[str]:
    """總版號的「遞增」有沒有紅端。

    這條規則原本寫的是「不同」,所以 `1.2.0 → 1.1.0` 照過。改成遞增之後
    必須有一個案例證明倒退真的會紅——否則就是又一條沒有紅端的規則。
    """
    import json as _json
    import subprocess
    import tempfile

    def run(repo, *a):
        return subprocess.run(["git", *a], cwd=repo, capture_output=True)

    def mk(repo, rel, body):
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def catalog(v):
        return _json.dumps({"metadata": {"version": v}, "plugins": []},
                           ensure_ascii=False)

    out: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        run(repo, "init", "-q", "-b", "main")
        run(repo, "config", "user.email", "t@t")
        run(repo, "config", "user.name", "t")
        mk(repo, ".claude-plugin/marketplace.json", catalog("1.2.0"))
        mk(repo, "skills/solo/SKILL.md", "---\nname: solo\n---\n原文\n")
        run(repo, "add", "-A")
        run(repo, "commit", "-q", "-m", "base")
        base = run(repo, "rev-parse", "HEAD").stdout.decode().strip()

        mk(repo, "skills/solo/SKILL.md", "---\nname: solo\n---\n改過\n")
        mk(repo, ".claude-plugin/marketplace.json", catalog("1.1.0"))   # 倒退
        run(repo, "add", "-A")
        run(repo, "commit", "-q", "-m", "regress")
        if not any("沒有遞增" in p for p in check_since(repo, base)):
            out.append("總版號倒退(1.2.0 → 1.1.0)竟然沒紅"
                       "——「遞增」這條規則的紅端不可達")

        mk(repo, ".claude-plugin/marketplace.json", catalog("1.3.0"))   # 正確遞增
        run(repo, "add", "-A")
        run(repo, "commit", "-q", "-m", "ok")
        if got := check_since(repo, base):
            out.append(f"總版號正確遞增卻被擋:{got}")
    return out


def static_self_test() -> list[str]:
    """`check_static` 的紅綠端。**在 CHG-20260814-06 之前這裡是空的。**

    複審(fable)指出的事實:被退役的第三處斷言,**從被寫下到被拆掉,
    整個生命週期沒被機器看過一眼**——拆掉它時沒有任何測試轉紅。
    那正是「閘被無聲拔牙」的機制本身。

    更要緊的是現在式:退役之後,「SKILL.md 與 plugin.json 分岔是合法的」
    這個新不變量**只釘在 version_impact_check 的 self-test 裡,不在退役現場**。
    於是 CHG 自己預言的回歸——「下一個人把它當 bug 修回去」——今天就能無聲發生:
    把第三處斷言加回去,全部測試照綠。

    所以這裡放兩案:保留下來的那條要有紅端,退役掉的那條要有**綠端**。
    綠端是本次不變量改變的錨,它紅了就代表有人把斷言加回去了。
    """
    import json as _json
    import tempfile

    out: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)

        def build(entry_v: str, pj_v: str, skill_v: str) -> None:
            (repo / ".claude-plugin").mkdir(parents=True, exist_ok=True)
            (repo / ".claude-plugin" / "marketplace.json").write_text(_json.dumps({
                "metadata": {"version": "1.0.0"},
                "plugins": [{"name": "solo", "source": "./plugins/solo",
                             "version": entry_v}]}, ensure_ascii=False), encoding="utf-8")
            d = repo / "plugins" / "solo" / ".claude-plugin"
            d.mkdir(parents=True, exist_ok=True)
            (d / "plugin.json").write_text(
                _json.dumps({"name": "solo", "version": pj_v}, ensure_ascii=False),
                encoding="utf-8")
            s = repo / "skills" / "solo"
            s.mkdir(parents=True, exist_ok=True)
            (s / "SKILL.md").write_text(
                f"---\nname: solo\nmetadata:\n  version: {skill_v}\n---\n\n# solo\n",
                encoding="utf-8")

        build("1.0.0", "1.1.0", "1.0.0")          # 紅端:entry ≠ plugin.json
        if not any("版本分岔" in p for p in check_static(repo)):
            out.append("check_static 紅端不可達:entry≠plugin.json 竟然沒被抓到"
                       "——保留下來的那條斷言沒有紅端,等於沒有")

        build("1.4.0", "1.4.0", "1.0.0")          # 綠端:SKILL.md 與 plugin.json 分岔
        if got := check_static(repo):
            out.append("check_static 綠端不可達:SKILL.md 與 plugin.json 分岔應**合法**"
                       f"(CHG-20260814-06 退役第三處同步斷言),卻被擋下:{got}"
                       "——有人把退役的斷言加回去了")
    return out


def main(argv) -> int:
    if "--self-test" in argv:
        return self_test()
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--check", action="store_true", help="靜態:semver + entry==plugin.json")
    ap.add_argument("--since", metavar="REF", help="git:REF..HEAD 動到 plugins/skills 則 catalog 須 bump")
    ap.add_argument("--bump", metavar="REF", help="自動推導並寫入 catalog 版號(以 REF 現況為基準;唯一會寫檔的模式)")
    args = ap.parse_args(argv[1:])
    if not args.check and not args.since and not args.bump:
        args.check = True
    repo = Path(args.repo).resolve()
    if args.bump:
        rc = bump_catalog(repo, args.bump)
        if rc != 0 or not (args.check or args.since):
            return rc
    problems: list[str] = []
    if args.check:
        problems += check_static(repo)
    if args.since:
        problems += check_since(repo, args.since)
    if problems:
        print("❌ catalog-check 未通過:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("✅ catalog-check 通過(marketplace 版本一致" + ("、變動已 bump" if args.since else "") + ")。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
