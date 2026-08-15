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

# 成功時安靜、失敗時**把原因印出來**。
# CHG-20260810-07 把「hook 的輸出蓋掉自己的錯誤訊息」列為觀察項,並寫明第二次發生就改;
# CHG-20260813-01 施工時第二次發生:[5/5] 靜默 exit 1,一個字都沒印,查不出是哪一支擋的。
quiet() {
  local out
  if ! out=$("$@" 2>&1); then
    echo "    ❌ 失敗:$*"
    echo "$out" | sed 's/^/    /'
    return 1
  fi
}

echo "[5/5] 其餘治理閘"
quiet python3 tools/autopilot/scripts/doc_integrity_check.py --repo .
quiet python3 tools/autopilot/scripts/static_check.py --repo . --paths skills plugins
quiet python3 plugins/build_suite.py --self-test
quiet python3 plugins/build_suite.py --check
quiet python3 plugins/catalog_check.py --self-test
quiet python3 plugins/catalog_check.py --repo . --check
quiet python3 scripts/skill_inventory_check.py --self-test
quiet python3 scripts/skill_inventory_check.py --repo .
quiet python3 scripts/genre_ratio_freeze.py --self-test
quiet python3 scripts/genre_ratio_freeze.py --repo .
quiet python3 scripts/version_impact_check.py --self-test

echo "✅ 實際操作驗收通過"
