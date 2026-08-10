#!/usr/bin/env bash
# 本機治理閘(取代 GitHub Actions 的 governance.yml)。exit 0 = pass。
#
# 為什麼不是 workflow:本 repo 是私有的,而私有 repo 的 Actions 需要帳務正常;
# 帳務一斷,**job 連排都不會排**——把 workflow 改小完全沒有用,因為紅的不是步驟,是啟動。
# 一個永遠紅、且紅得與程式碼無關的閘,教會人的是忽略它(KN-002 同一條道理)。
#
# 檔名是刻意選的:autopilot runner 的 local-gate 探測順序第一位就是 .github/ci_local.sh,
# 所以就算 pre-push hook 沒裝,merge 前那道閘仍然找得到它。
set -euo pipefail
cd "$(dirname "$0")/.."

PY=python3
command -v python3 > /dev/null 2>&1 || PY=python

RUN=tools/autopilot/scripts/autopilot_runner.py

echo "[1/5] 實際操作驗收(含漂移紅燈可達探針)"
bash .github/verify.sh

echo "[2/5] 風格 lint 夾具:好樣本要過、壞樣本要擋"
$PY skills/writing/scripts/style_check.py skills/writing/assets/sample-good.md > /dev/null
$PY skills/writing/scripts/style_check.py skills/writing/assets/sample-issue.md > /dev/null
if $PY skills/writing/scripts/style_check.py skills/writing/assets/sample-bad.md > /dev/null 2>&1; then
  echo "    ❌ sample-bad.md 竟然通過 lint —— 詞表或門檻壞了"; exit 1
fi

echo "[3/5] py_compile"
$PY -m py_compile $(find skills plugins tools -name '*.py' -not -path '*/plugins/*/skills/*')

echo "[4/5] JSON 可解析"
for f in $(find . -name '*.json' -not -path './.git/*'); do
  $PY -m json.tool "$f" > /dev/null || { echo "    ❌ 壞掉的 JSON: $f"; exit 1; }
done

echo "[5/5] catalog 版本(靜態 + 變動就要 bump)"
$PY plugins/catalog_check.py --repo . --check > /dev/null
if git fetch origin main --depth=50 -q 2>/dev/null; then
  $PY plugins/catalog_check.py --repo . --since origin/main > /dev/null
else
  # 離線時**明說沒驗到**,不冒充通過(KN-004:判定不出來不等於沒問題)
  echo "    ⚠️  取不到 origin/main —— bump-on-change 這一項未驗到,不是通過"
fi

echo "✅ 本機治理閘通過"
