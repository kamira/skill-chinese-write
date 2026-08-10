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

echo "[1/13] 實際操作驗收(含漂移紅燈可達探針)"
bash .github/verify.sh

echo "[2/13] writing 風格 lint 夾具:好樣本要過、壞樣本要擋"
$PY skills/writing/scripts/style_check.py skills/writing/assets/sample-good.md > /dev/null
$PY skills/writing/scripts/style_check.py skills/writing/assets/sample-issue.md > /dev/null
if $PY skills/writing/scripts/style_check.py skills/writing/assets/sample-bad.md > /dev/null 2>&1; then
  echo "    ❌ sample-bad.md 竟然通過 lint —— 詞表或門檻壞了"; exit 1
fi

echo "[3/13] fiction lint 夾具:好樣本要過、壞樣本要擋"
$PY skills/fiction/scripts/fiction_check.py skills/fiction/assets/sample-good.md --genre wuxia > /dev/null
if $PY skills/fiction/scripts/fiction_check.py skills/fiction/assets/sample-bad.md --genre wuxia > /dev/null 2>&1; then
  echo "    ❌ fiction sample-bad.md 竟然通過 lint —— 規則或門檻壞了"; exit 1
fi

echo "[4/13] 小說子層四支夾具:各以自己的流派跑"
for G in scifi mystery romance flash; do
  $PY skills/fiction/scripts/fiction_check.py "skills/fiction-$G/assets/sample-good.md" --genre $G > /dev/null
done

echo "[5/13] techdoc lint 夾具:兩份 good 要過、bad 在兩種 kind 都要被擋"
$PY skills/techdoc/scripts/techdoc_check.py skills/techdoc/assets/sample-spec-good.md --kind spec > /dev/null
$PY skills/techdoc/scripts/techdoc_check.py skills/techdoc/assets/sample-arch-good.md --kind arch > /dev/null
for K in spec arch; do
  if $PY skills/techdoc/scripts/techdoc_check.py skills/techdoc/assets/sample-bad.md --kind $K > /dev/null 2>&1; then
    echo "    ❌ techdoc sample-bad.md 在 --kind $K 竟然通過 —— 規則或門檻壞了"; exit 1
  fi
done

echo "[6/13] bizdoc lint 夾具:兩份 good 要過、兩份 bad 在對應 kind 要被擋"
$PY skills/bizdoc/scripts/bizdoc_check.py skills/bizdoc/assets/sample-gov-good.md --kind gov > /dev/null
$PY skills/bizdoc/scripts/bizdoc_check.py skills/bizdoc/assets/sample-press-good.md --kind press > /dev/null
for K in gov press; do
  if $PY skills/bizdoc/scripts/bizdoc_check.py skills/bizdoc/assets/sample-bad.md --kind $K > /dev/null 2>&1; then
    echo "    ❌ bizdoc sample-bad.md 在 --kind $K 竟然通過 —— 規則或門檻壞了"; exit 1
  fi
done
if $PY skills/bizdoc/scripts/bizdoc_check.py skills/bizdoc/assets/sample-gov-bad-subject.md --kind gov > /dev/null 2>&1; then
  echo "    ❌ 主旨過長的夾具竟然通過 —— 規則或門檻壞了"; exit 1
fi

echo "[7/13] zh-style:夾具雙向 + 全 repo 夾具零半形"
$PY skills/zh-style/scripts/zh_style_check.py --self-test > /dev/null
$PY skills/zh-style/scripts/zh_style_check.py skills/zh-style/assets/sample-good.md > /dev/null
if $PY skills/zh-style/scripts/zh_style_check.py skills/zh-style/assets/sample-bad.md > /dev/null 2>&1; then
  echo "    ❌ zh-style sample-bad.md 竟然通過"; exit 1
fi
$PY skills/zh-style/scripts/zh_style_check.py skills/*/assets/sample-good.md skills/*/assets/sample-issue.md skills/*/assets/sample-spec-good.md skills/*/assets/sample-arch-good.md skills/*/assets/sample-gov-good.md skills/*/assets/sample-press-good.md > /dev/null

echo "[8/13] skill 清單一致性(含紅燈可達自檢)"
$PY scripts/skill_inventory_check.py --self-test > /dev/null
$PY scripts/skill_inventory_check.py --repo . > /dev/null

echo "[9/13] CHG 欄位不得留佔位字串(含紅燈可達自檢)"
$PY scripts/chg_field_check.py --self-test > /dev/null
$PY scripts/chg_field_check.py --repo . > /dev/null

echo "[10/13] CHG 設計圖閘:真實帳本要過、夾具紅綠兩端都要對"
$PY scripts/chg_diagram_gate.py --repo . > /dev/null
$PY scripts/chg_diagram_gate.py --repo . --glob 'tests/fixtures/chg-gate/pass/case-*.md' > /dev/null
if $PY scripts/chg_diagram_gate.py --repo . --glob 'tests/fixtures/chg-gate/fail/case-*.md' > /dev/null 2>&1; then
  echo "    ❌ 缺圖的夾具竟然通過 —— 這道閘等於不存在"; exit 1
fi

echo "[11/13] py_compile"
$PY -m py_compile $(find skills plugins tools -name '*.py' -not -path '*/plugins/*/skills/*')

echo "[12/13] JSON 可解析"
for f in $(find . -name '*.json' -not -path './.git/*'); do
  $PY -m json.tool "$f" > /dev/null || { echo "    ❌ 壞掉的 JSON: $f"; exit 1; }
done

echo "[13/13] catalog 版本(靜態 + 變動就要 bump)"
$PY plugins/catalog_check.py --repo . --check > /dev/null
if git fetch origin main --depth=50 -q 2>/dev/null; then
  $PY plugins/catalog_check.py --repo . --since origin/main > /dev/null
else
  # 離線時**明說沒驗到**,不冒充通過(KN-004:判定不出來不等於沒問題)
  echo "    ⚠️  取不到 origin/main —— bump-on-change 這一項未驗到,不是通過"
fi

echo "✅ 本機治理閘通過"
