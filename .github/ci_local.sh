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

# 成語密度是**提醒**而非硬性違規,所以它在 CI 裡要靠 --strict 才擋得住東西。
# 沒有這一步,密度規則等於沒有閘——CHG-20260813-01 D-1:分母鉗位讓這條規則
# 從來沒有被任何輸入真正跑到過,而唯一會踩線的輸入正被鉗位遮著。
echo "[3b/13] fiction 成語密度:紅端要紅、綠端要綠(--strict)"
# **紅端要分 rc 1 與 rc 2。** 只寫 `if 指令; then 失敗; fi` 的話,夾具被刪、路徑打錯、
# rules JSON 壞掉(全是 rc 2)都會被當成「紅端成立」而放行——「紅端要紅」可以被
# ENOENT 滿足(V5 審議)。
set +e
$PY skills/fiction/scripts/fiction_check.py skills/fiction/assets/sample-bad-idiom-density.md --genre wuxia --strict > /dev/null 2>&1
RC=$?
set -e
if [ "$RC" -eq 0 ]; then
  echo "    ❌ 成語密度紅端夾具竟然通過 —— 分母又被鉗位了,或門檻壞了"; exit 1
elif [ "$RC" -ne 1 ]; then
  echo "    ❌ 紅端夾具的退出碼是 $RC,不是 1 —— 那是環境/參數錯誤(檔案不見?規則檔壞了?),"
  echo "       不能拿來當作「規則有在擋」的證據"; exit 1
fi
$PY skills/fiction/scripts/fiction_check.py skills/fiction/assets/sample-good.md --genre wuxia --strict > /dev/null

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

# **不要把這一步的輸出丟進 /dev/null。** BASELINE 有別於「整組豁免」的核心論據就是
# 「會印出來、掃描結果永遠說得出還欠幾對」——把 stdout 重導掉,那個承諾在 CI 裡當場失效,
# 而且紅燈時只看得到步驟名、看不到是哪一對哪一段文字(V4 審議)。
echo "[10b/13] 夾具不得逐字引用規則自己的例句(含紅燈可達自檢)"
# self-test 的輸出也不要吞:五端自檢哪一端不可達,紅燈時要看得到(V5 審議指出
# 這一行就是我在下一行罵的同款反模式)。
$PY scripts/fixture_coupling_check.py --self-test | sed "s/^/    /"
$PY scripts/fixture_coupling_check.py --repo . | sed 's/^/    /'

# 分母改成真實字數之後,per_k 可能是 0——每一處除法都得有守衛。
# 施工時 style_check.py 的破折號密度就漏了一個,空輸入直接 ZeroDivisionError。
# 「我記得加守衛」不是斷言,所以把它變成閘:五支引擎各餵一個空檔,不准有 traceback。
echo "[10c/13] 空輸入不得 traceback(per_k 除以零守衛)"
EMPTY="$(mktemp)"; : > "$EMPTY"
for CMD in \
  "skills/writing/scripts/style_check.py $EMPTY" \
  "skills/fiction/scripts/fiction_check.py $EMPTY" \
  "skills/techdoc/scripts/techdoc_check.py $EMPTY --kind spec" \
  "skills/techdoc/scripts/techdoc_check.py $EMPTY --kind arch" \
  "skills/bizdoc/scripts/bizdoc_check.py $EMPTY --kind gov" \
  "skills/bizdoc/scripts/bizdoc_check.py $EMPTY --kind press" \
  "skills/zh-style/scripts/zh_style_check.py $EMPTY" ; do
  if $PY $CMD 2>&1 | grep -q Traceback; then
    echo "    ❌ 空輸入炸了:$CMD"; rm -f "$EMPTY"; exit 1
  fi
done
rm -f "$EMPTY"

# min_sample_chars(300)讓短夾具的密度變成「未驗到」。這是誠實的,但驗收審議指出
# 一個真實風險:門檻會**悄悄擴大成規則的逃生門**——今天七份未驗到,明天有人把門檻
# 調到 600,一半的夾具就靜靜不受規則管了,而 CI 全程綠燈。
# 所以把「哪幾份預期未驗到」釘死:名單一多一少都轉紅,要改門檻就得同時改這裡並說明。
# **四支引擎全掃,不只 fiction。** 初版只掃 `skills/fiction*`,等於同一個逃生門
# 只堵了四分之一——而 bizdoc 的兩份 good 夾具(230 / 226 字)已經掉進去了:
# 成語密度規則沒有任何夾具跑得到,正是 D-1 要修的那個 KN-001 狀態被門檻重新引入
# (V5 審議)。另外三支原本連「未驗到」都不印,已一併補上。
echo "[10d/13] 未驗到名單必須釘死(門檻不得悄悄變成逃生門)"
# 實測值,不是憑印象填的。
# 這三份的密度規則目前沒有任何輸入跑得到,是已知且具名的缺口,不是通過。
EXPECT_UNVERIFIED="skills/bizdoc/assets/sample-gov-good.md skills/fiction-flash/assets/sample-good.md skills/zh-style/assets/sample-good.md"
ACTUAL_UNVERIFIED=""
probe_unverified() {   # $1=腳本 $2=檔案 $3...=額外參數
  local s="$1"; shift; local f="$1"; shift
  if $PY "$s" "$f" "$@" 2>&1 | grep -q "未驗到"; then echo "$f"; fi
}
for F in skills/fiction/assets/sample-*.md skills/fiction-*/assets/sample-*.md; do
  ACTUAL_UNVERIFIED="$ACTUAL_UNVERIFIED $(probe_unverified skills/fiction/scripts/fiction_check.py "$F")"
done
for F in skills/writing/assets/sample-*.md skills/prose/assets/sample-*.md \
         skills/narrative/assets/sample-*.md skills/poetry/assets/sample-*.md \
         skills/fu/assets/sample-*.md skills/zh-style/assets/sample-*.md; do
  [ -f "$F" ] || continue
  ACTUAL_UNVERIFIED="$ACTUAL_UNVERIFIED $(probe_unverified skills/writing/scripts/style_check.py "$F")"
done
for F in skills/techdoc/assets/sample-*.md; do
  ACTUAL_UNVERIFIED="$ACTUAL_UNVERIFIED $(probe_unverified skills/techdoc/scripts/techdoc_check.py "$F" --kind spec)"
done
for F in skills/bizdoc/assets/sample-*.md; do
  ACTUAL_UNVERIFIED="$ACTUAL_UNVERIFIED $(probe_unverified skills/bizdoc/scripts/bizdoc_check.py "$F" --kind gov)"
done
ACTUAL_UNVERIFIED="$(echo $ACTUAL_UNVERIFIED | tr ' ' '\n' | sort -u | tr '\n' ' ')"
ACTUAL_UNVERIFIED="$(echo $ACTUAL_UNVERIFIED | tr ' ' '\n' | sort | tr '\n' ' ' | xargs)"
EXPECT_UNVERIFIED="$(echo $EXPECT_UNVERIFIED | tr ' ' '\n' | sort | tr '\n' ' ' | xargs)"
if [ "$ACTUAL_UNVERIFIED" != "$EXPECT_UNVERIFIED" ]; then
  echo "    ❌ 未驗到名單變了"
  echo "       預期:$EXPECT_UNVERIFIED"
  echo "       實際:$ACTUAL_UNVERIFIED"
  echo "       密度門檻動了就要在這裡同步,並在 CHG 說明為什麼那幾份可以不受規則管"
  exit 1
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
