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
    return problems


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
    content_changed = [f for f in (l.strip() for l in diff.stdout.splitlines())
                       if f.startswith(("plugins/", "skills/")) and f.rsplit("/", 1)[-1] != "README.md"]
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
    if old_mv == cur_mv:
        sample = ", ".join(content_changed[:5])
        return [f"plugins/skills 內容自 {ref} 起有變動但 marketplace metadata.version 未 bump"
                f"(仍為 {cur_mv})——每次 plugin 變動須同步 bump catalog(觸發檔:{sample} …)"
                f"\n    修正:python3 plugins/catalog_check.py --bump {ref}(自動推導,不必人挑版號)"]
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


def main(argv) -> int:
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
