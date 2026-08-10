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
    "writing": ('writing',),
    "fiction": ('fiction',),
    "fiction-flash": ('fiction-flash', 'fiction'),
    "fiction-long": ('fiction-long', 'fiction'),
    "fiction-wuxia": ('fiction-wuxia', 'fiction'),
    "fiction-scifi": ('fiction-scifi', 'fiction'),
    "fiction-mystery": ('fiction-mystery', 'fiction'),
    "fiction-romance": ('fiction-romance', 'fiction'),
    "spec": ('spec', 'techdoc'),
    "architecture": ('architecture', 'techdoc'),
    "official": ('official', 'bizdoc'),
    "press": ('press', 'bizdoc'),
    "proposal": ('proposal',),
    "prose": ('prose',),
    "poetry": ('poetry',),
    "drama": ('drama',),
    "narrative": ('narrative',),
    "lyric": ('lyric',),
    "exposition": ('exposition',),
    "fu": ('fu',),
    "historiography": ('historiography',),
}
EXCLUDE = ("__pycache__", ".DS_Store")


def files_of(base: Path):
    return {p.relative_to(base): p for p in base.rglob("*")
            if p.is_file() and not any(x in p.parts for x in EXCLUDE)}


def main(argv) -> int:
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
    total = added + updated + removed
    tag = "check" if check else "sync"
    print(f"[{tag}] 新增 {added} / 更新 {updated} / 移除 {removed}(共 {total} 變更)")
    if check and total:
        print("plugin 內 skills 複本與來源不同步——執行 python3 plugins/build_suite.py 後提交")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
