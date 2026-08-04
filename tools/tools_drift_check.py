#!/usr/bin/env python3
"""隨身治理工具的漂移檢查(衛星 repo 專用)。

`tools/` 底下那幾支是從 `kamira/skill-ai-sdlc-autopilot` **帶過來的副本**。
分開治理的代價就是副本會漂,而漂移有兩個方向:

  · 本地被改過  —— 這裡查得出來(雜湊對不上)
  · 上游前進了  —— 這裡**查不出來**,需要主動同步

第二種是這支程式的已知盲點,所以它不印任何「工具是最新的」之類的話。
把查不出來的事說成查過了,比不查更糟(KN-001)。

Run: python3 tools/tools_drift_check.py → 0 一致,1 有本地改動,2 清單壞掉。
"""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
PROV = HERE / "PROVENANCE.json"


def sha256(p: Path) -> str:
    """正規化行尾後再算——否則 Windows checkout 會讓每個檔案都『被改過』。"""
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    if not PROV.is_file():
        print(f"❌ 找不到 {PROV.name} — 沒有清單就無從判斷副本有沒有被動過")
        return 2
    try:
        data = json.loads(PROV.read_text(encoding="utf-8-sig"))
        want = data["sha256"]
    except (ValueError, OSError, KeyError) as exc:
        print(f"❌ {PROV.name} 讀不到雜湊清單:{exc}(讀不到就照過,等於這道檢查不存在)")
        return 2
    if not want:
        print(f"❌ {PROV.name} 的雜湊清單是空的 — 空清單會讓每一次檢查都通過")
        return 2

    bad, missing = [], []
    for name, digest in sorted(want.items()):
        p = HERE / name
        if not p.is_file():
            missing.append(name)
        elif sha256(p) != digest:
            bad.append(name)

    if missing:
        print(f"❌ 清單列了但檔案不見:{', '.join(missing)}")
    if bad:
        print(f"❌ 本地被改過(與帶過來當下對不上):{', '.join(bad)}")
        print("   要嘛把改動送回上游 kamira/skill-ai-sdlc-autopilot,")
        print("   要嘛重新同步一份並更新 PROVENANCE.json。就地分叉會讓兩邊都不可信。")
    if missing or bad:
        return 1

    src = data.get("source_commit", "(未記錄)")
    print(f"✅ {len(want)} 支隨身工具與帶過來當下一致(來源 commit {src[:12]})")
    print("   註:本檢查看不出**上游是否已前進**——那需要主動同步,不在這道閘的範圍內。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
