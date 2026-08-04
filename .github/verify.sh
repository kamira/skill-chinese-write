#!/usr/bin/env bash
# 實際操作驗收(CHG-20260804-02 的 operate 節)。exit 0 = pass。
# 這支存在的理由:verify 階段若沒有可重跑的指令,就只能停下來等人——
# 而「等人」在 CI 上與「沒驗」看起來一樣。
set -euo pipefail
cd "$(dirname "$0")/.."
RUN=tools/autopilot/scripts/autopilot_runner.py

echo "[1/5] runner 可執行"
python3 $RUN --help > /dev/null

echo "[2/5] 所有 plan 格式 CHG 通過 plan-check"
for f in docs/writing/changes/CHG-*.md; do
  if grep -qE '^### Global Constraints' "$f" || grep -qE '^- \[.\] T[0-9]' "$f"; then
    python3 $RUN plan-check --chg "$f" > /dev/null
  else
    echo "    (skip non-plan: $f)"
  fi
done

echo "[3/5] 漂移檢查:綠燈可達"
python3 tools/tools_drift_check.py > /dev/null

echo "[4/5] 漂移檢查:**紅燈也可達**(改一個字元必須轉紅)"
cp tools/autopilot/scripts/static_check.py /tmp/verify_drift.bak
trap 'cp /tmp/verify_drift.bak tools/autopilot/scripts/static_check.py' EXIT
echo "# drift probe" >> tools/autopilot/scripts/static_check.py
if python3 tools/tools_drift_check.py > /dev/null 2>&1; then
  echo "    ❌ 副本被改過卻沒紅 —— 這道閘等於不存在"; exit 1
fi
cp /tmp/verify_drift.bak tools/autopilot/scripts/static_check.py
python3 tools/tools_drift_check.py > /dev/null

echo "[5/5] 其餘治理閘"
python3 tools/autopilot/scripts/doc_integrity_check.py --repo . > /dev/null
python3 tools/autopilot/scripts/static_check.py --repo . --paths skills plugins > /dev/null
python3 plugins/build_suite.py --check > /dev/null
python3 plugins/catalog_check.py --repo . --check > /dev/null

echo "✅ 實際操作驗收通過"
