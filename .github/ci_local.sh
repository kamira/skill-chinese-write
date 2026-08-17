#!/usr/bin/env bash
# 治理閘的**唯一真相源**。兩個載體都跑這一支:本機(pre-push hook)與
# GitHub Actions(`governance.yml` 只負責 checkout / setup-python / 呼叫這裡)。
# exit 0 = pass。
#
# ## 為什麼是一支而不是兩支(CHG-20260816-01)
#
# 這個檔曾經寫著「取代 GitHub Actions 的 governance.yml」,理由是私有 repo 的
# Actions 帳務一斷 job 連排都不會排。**那個前提已經不成立**——governance 正常在跑,
# 於是兩個載體並存,各自帶著一份重複的內容,而沒有任何東西斷言它們一致。
# 代價是實際發生過的:夾具搬家只改了這裡,governance 那份沒跟上,
# **本機綠而 CI 紅**;更久的是 `genre_ratio_freeze`(前六張的核心閘)
# 只在這裡跑,GitHub CI 從來沒跑過它。
#
# 「兩份重複的東西靠人記得同步」在這個 repo 已經是第四次(名冊 vs 磁碟、
# 三處版號、兩份 EXCLUDE)。前三次的解法是加一道交叉斷言;這次改用
# **讓第二份不存在**——一致性不必斷言,因為只剩一份。
#
# ## 載體不可知是硬規矩
#
# 跨載體傳進來的只准 `CI_SINCE_REF` 一個變數。**本檔不得讀 `GITHUB_*` / `RUNNER_*`**
# ——否則載體條件會從 workflow 遷徙到這裡,而只掃 workflow 的斷言對它全盲。
# 這條由 `scripts/carrier_manifest_check.py` 守著。
#
# 檔名是刻意選的:autopilot runner 的 local-gate 探測順序第一位就是
# .github/ci_local.sh,**改名會斷**。
set -euo pipefail
cd "$(dirname "$0")/.."

PY=python3
command -v python3 > /dev/null 2>&1 || PY=python

# diff 式的閘要拿什麼當基準。預設 origin/main(本機與 PR 情境都對);
# push 事件由 workflow 傳 `github.event.before` 進來——那是這次 push 之前的 tip,
# **不依賴 merge 策略**(squash、merge commit、直推 N 個 commit 全對),
# 而 `HEAD^` 三者都會判錯。
SINCE_REF="${CI_SINCE_REF:-origin/main}"
if [ -n "${CI_SINCE_REF:-}" ]; then
  # 零 SHA = 分支初次建立或歷史改寫。此時基準不存在,**硬紅**——
  # 沿 [10f] 的 fail-closed 前例:取不到基準等於規則消失,而輸出會長得跟通過一樣。
  # 這不是 KN-002(它稀有,而且正是該有人看的時刻)。
  if [ "$CI_SINCE_REF" = "0000000000000000000000000000000000000000" ]; then
    echo "    ❌ CI_SINCE_REF 是零 SHA——基準不存在,diff 式的閘無法驗,不得以此為通過"
    exit 1
  fi
  git rev-parse --verify --quiet "${CI_SINCE_REF}^{commit}" > /dev/null || {
    echo "    ❌ CI_SINCE_REF=$CI_SINCE_REF 解析不到——基準取不到等於整套版號規則消失"
    exit 1; }
fi

echo "[1/19] 實際操作驗收(含漂移紅燈可達探針)"
bash .github/verify.sh

echo "[2/19] writing 風格 lint 夾具 + 句型殼紅綠端自檢"
# 句型殼那條(生造的帶勁口語)腳本判不準,斷言只抓最有把握的形狀。self-test 釘住
# 使用者實測給的五個合法用法——regex 一放寬就誤殺,誤殺即紅。
$PY skills/writing/scripts/style_check.py --self-test dummy > /dev/null
$PY skills/writing/scripts/style_check.py skills/writing/assets/sample-good.md > /dev/null
$PY skills/writing/scripts/style_check.py skills/writing/assets/sample-issue.md > /dev/null
if $PY skills/writing/scripts/style_check.py skills/writing/assets/sample-bad.md > /dev/null 2>&1; then
  echo "    ❌ sample-bad.md 竟然通過 lint —— 詞表或門檻壞了"; exit 1
fi

echo "[3/19] fiction lint 夾具:好樣本要過、壞樣本要擋"
$PY skills/fiction/scripts/fiction_check.py skills/fiction/assets/sample-good.md --genre wuxia > /dev/null
if $PY skills/fiction/scripts/fiction_check.py skills/fiction/assets/sample-bad.md --genre wuxia > /dev/null 2>&1; then
  echo "    ❌ fiction sample-bad.md 竟然通過 lint —— 規則或門檻壞了"; exit 1
fi

# 成語密度是**提醒**而非硬性違規,所以它在 CI 裡要靠 --strict 才擋得住東西。
# 沒有這一步,密度規則等於沒有閘——CHG-20260813-01 D-1:分母鉗位讓這條規則
# 從來沒有被任何輸入真正跑到過,而唯一會踩線的輸入正被鉗位遮著。
echo "[3b/19] fiction 成語密度:紅端要紅、綠端要綠(--strict)"
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

echo "[4/19] 小說子層四支夾具:各以自己的流派跑"
for G in scifi mystery romance flash; do
  $PY skills/fiction/scripts/fiction_check.py "skills/fiction/assets/sample-good-$G.md" --genre $G > /dev/null
done

echo "[5/19] techdoc lint 夾具:兩份 good 要過、bad 在兩種 kind 都要被擋"
$PY skills/techdoc/scripts/techdoc_check.py skills/techdoc/assets/sample-spec-good.md --kind spec > /dev/null
$PY skills/techdoc/scripts/techdoc_check.py skills/techdoc/assets/sample-arch-good.md --kind arch > /dev/null
for K in spec arch; do
  if $PY skills/techdoc/scripts/techdoc_check.py skills/techdoc/assets/sample-bad.md --kind $K > /dev/null 2>&1; then
    echo "    ❌ techdoc sample-bad.md 在 --kind $K 竟然通過 —— 規則或門檻壞了"; exit 1
  fi
done

echo "[6/19] bizdoc lint 夾具:兩份 good 要過、兩份 bad 在對應 kind 要被擋"
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

echo "[6b/19] 近體詩格律:好樣本要過、壞樣本要擋(含紅綠端自檢)"
# 綠端夾具是**傳世詩**(杜甫〈春望〉),紅端由它單字突變產生——
# 綠端自己寫的話,寫的人與判的人是同一個,那個綠證明不了格律。
$PY skills/regulated-verse/scripts/verse_check.py --self-test > /dev/null
$PY skills/regulated-verse/scripts/verse_check.py skills/regulated-verse/assets/sample-good.md > /dev/null
if $PY skills/regulated-verse/scripts/verse_check.py skills/regulated-verse/assets/sample-bad.md > /dev/null 2>&1; then
  echo "    ❌ 近體詩 sample-bad.md 竟然通過 —— 韻腳或對仗規則壞了"; exit 1
fi

echo "[6c/19] 宋詞格律:資產守恆 + 好樣本要過、壞樣本要擋"
# 資產先驗:baixiang / cilin 的守恆帳要對得起來。
# 「sha256 錨住了輸入,沒錨住轉換」——雜湊只證明來源沒被換,
# 證明不了正規化沒把資料吃掉。西江月曾靜默掉 3 個句對而仍回報 aligned:true。
$PY skills/ci-poetry/scripts/assets_verify.py > /dev/null
$PY skills/ci-poetry/scripts/ci_check.py --self-test > /dev/null
# 綠端夾具是黃庭堅〈清平樂〉,而 self-test 的綠端是〈菩薩蠻〉——**刻意不共用**。
# 同一首當兩處綠端,兩道閘看起來是兩道、實際是一道(CHG-20260817-01 被 6b 抓過)。
$PY skills/ci-poetry/scripts/ci_check.py --tune 清平樂 skills/ci-poetry/assets/sample-good.md > /dev/null
if $PY skills/ci-poetry/scripts/ci_check.py --tune 清平樂 skills/ci-poetry/assets/sample-bad.md > /dev/null 2>&1; then
  echo "    ❌ 宋詞 sample-bad.md 竟然通過 —— 韻組同部規則壞了"; exit 1
fi

echo "[7/19] zh-style:夾具雙向 + 全 repo 夾具零半形"
$PY skills/zh-style/scripts/zh_style_check.py --self-test > /dev/null
$PY skills/zh-style/scripts/zh_style_check.py skills/zh-style/assets/sample-good.md > /dev/null
if $PY skills/zh-style/scripts/zh_style_check.py skills/zh-style/assets/sample-bad.md > /dev/null 2>&1; then
  echo "    ❌ zh-style sample-bad.md 竟然通過"; exit 1
fi
$PY skills/zh-style/scripts/zh_style_check.py skills/*/assets/sample-good.md skills/*/assets/sample-issue.md skills/*/assets/sample-spec-good.md skills/*/assets/sample-arch-good.md skills/*/assets/sample-gov-good.md skills/*/assets/sample-press-good.md > /dev/null

echo "[8/19] skill 清單一致性(含紅燈可達自檢)"
$PY scripts/skill_inventory_check.py --self-test > /dev/null
$PY scripts/skill_inventory_check.py --repo . > /dev/null

echo "[9/19] CHG 欄位不得留佔位字串(含紅燈可達自檢)"
$PY scripts/chg_field_check.py --self-test > /dev/null
$PY scripts/chg_field_check.py --repo . > /dev/null

echo "[10/19] CHG 設計圖閘:真實帳本要過、夾具紅綠兩端都要對"
$PY scripts/chg_diagram_gate.py --repo . > /dev/null
$PY scripts/chg_diagram_gate.py --repo . --glob 'tests/fixtures/chg-gate/pass/case-*.md' > /dev/null
if $PY scripts/chg_diagram_gate.py --repo . --glob 'tests/fixtures/chg-gate/fail/case-*.md' > /dev/null 2>&1; then
  echo "    ❌ 缺圖的夾具竟然通過 —— 這道閘等於不存在"; exit 1
fi

# **不要把這一步的輸出丟進 /dev/null。** BASELINE 有別於「整組豁免」的核心論據就是
# 「會印出來、掃描結果永遠說得出還欠幾對」——把 stdout 重導掉,那個承諾在 CI 裡當場失效,
# 而且紅燈時只看得到步驟名、看不到是哪一對哪一段文字(V4 審議)。
echo "[10b/19] 夾具不得逐字引用規則自己的例句(含紅燈可達自檢)"
# self-test 的輸出也不要吞:五端自檢哪一端不可達,紅燈時要看得到(V5 審議指出
# 這一行就是我在下一行罵的同款反模式)。
$PY scripts/fixture_coupling_check.py --self-test | sed "s/^/    /"
$PY scripts/fixture_coupling_check.py --repo . | sed 's/^/    /'

# 分母改成真實字數之後,per_k 可能是 0——每一處除法都得有守衛。
# 施工時 style_check.py 的破折號密度就漏了一個,空輸入直接 ZeroDivisionError。
# 「我記得加守衛」不是斷言,所以把它變成閘:五支引擎各餵一個空檔,不准有 traceback。
echo "[10c/19] 空輸入不得 traceback(per_k 除以零守衛)"
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
echo "[10d/19] 未驗到名單必須釘死(門檻不得悄悄變成逃生門)"
# 實測值,不是憑印象填的。
# 這三份的密度規則目前沒有任何輸入跑得到,是已知且具名的缺口,不是通過。
EXPECT_UNVERIFIED="skills/bizdoc/assets/sample-gov-good.md skills/fiction/assets/sample-good-flash.md skills/zh-style/assets/sample-good.md"
ACTUAL_UNVERIFIED=""
probe_unverified() {   # $1=腳本 $2=檔案 $3...=額外參數
  local s="$1"; shift; local f="$1"; shift
  if $PY "$s" "$f" "$@" 2>&1 | grep -q "未驗到"; then echo "$f"; fi
}
for F in skills/fiction/assets/sample-*.md; do
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

echo "[10e/19] 配比凍結閘(搬遷期間流派數值與執法狀態不准漂)"
# 兩趟都要跑:self-test 證明紅端可達,--repo 證明現況一致。
# 只跑後者的話,「六支全對」與「閘壞掉」看起來一樣。
$PY scripts/genre_ratio_freeze.py --self-test > /dev/null
$PY scripts/genre_ratio_freeze.py --repo . > /dev/null

echo "[10f/19] 版號影響閘(skill 內容變 → 全部宿主必 bump;內容沒變 → 戳記凍結)"
# 輸出**不丟 /dev/null**:這道閘的訊息會具名說出是哪支 skill、哪個宿主、
# 版號從哪到哪。丟掉之後只剩 exit code,人得自己再跑一次才知道紅在哪
# ——ACC-20260813-01 第 (4) 條記過這個同型病。
$PY scripts/version_impact_check.py --self-test
git fetch origin main --depth=50 -q 2>/dev/null || true
if git rev-parse --verify --quiet "${SINCE_REF}^{commit}" > /dev/null; then
  $PY scripts/version_impact_check.py --repo . --since "$SINCE_REF"
else
  # **這裡不 fail-open。** 解耦之後版本紀律整套押在這個 diff 式的閘上,
  # 取不到基準等於規則消失,而輸出會長得和通過一樣。
  echo "    ❌ 取不到基準 $SINCE_REF —— 版號影響閘無法驗,CI 不得以此為通過"
  exit 1
fi

echo "[10g/19] command 引用路徑閘(連結以檔案目錄為基準、程式碼路徑以兩個根為基準)"
$PY scripts/command_path_check.py --self-test
$PY scripts/command_path_check.py --repo .

echo "[11/19] py_compile"
# scripts/ 原本不在這行的搜尋範圍裡——治理閘自己反而沒被 py_compile 過。
$PY -m py_compile $(find skills plugins tools scripts -name '*.py' -not -path '*/plugins/*/skills/*')

echo "[12/19] JSON 可解析"
for f in $(find . -name '*.json' -not -path './.git/*'); do
  $PY -m json.tool "$f" > /dev/null || { echo "    ❌ 壞掉的 JSON: $f"; exit 1; }
done

echo "[13/19] catalog 版本(靜態 + 變動就要 bump)"
$PY plugins/catalog_check.py --repo . --check > /dev/null
git fetch origin main --depth=50 -q 2>/dev/null || true
if git rev-parse --verify --quiet "${SINCE_REF}^{commit}" > /dev/null; then
  $PY plugins/catalog_check.py --repo . --since "$SINCE_REF"
else
  # 離線時**明說沒驗到**,不冒充通過(KN-004:判定不出來不等於沒問題)
  echo "    ⚠️  取不到基準 $SINCE_REF —— bump-on-change 這一項未驗到,不是通過"
fi

# ── 以下四支原本只活在 governance.yml,本機從來跑不到(CHG-20260816-01)──
#
# 不對稱的方向要記準:**這四支不是「CI 專屬」,是歷史意外**。
# 逐支查過都是純 Python 對本地檔案的操作,沒有任何 ubuntu-only 依賴,
# 本機一直跑得動,只是沒人把它們寫進來。而 `build_suite --check` 在
# CHG-20260814-09 抓過一次真錯(regex 打中 PLUGINS 名冊),
# 那次是 CI 才紅的——本機先綠過一輪。
#
# (autopilot plan-check 不在這裡,因為它**不是缺口**:verify.sh [2/5] 就有
# 一份完整迴圈,而本檔 [1/19] 跑 verify.sh。governance 那一步是第三份重複。)

echo "[14/19] 隨身治理工具的漂移(上游是否前進看不出來,只查本地有沒有被改過)"
$PY tools/tools_drift_check.py > /dev/null

echo "[15/19] 帳本完整性(CHG↔ACC + 結構同步 + secrets)"
$PY tools/autopilot/scripts/doc_integrity_check.py --repo . > /dev/null

# 範圍**明示**收在本 repo 自己的程式碼:tools/ 是逐位元組相同的副本,
# 上游已對那四處 shell=True 具名豁免,而豁免記的是上游路徑。
# 副本的完整性由 [14/19] 負責——重新稽核一份雜湊相符的副本不會增加資訊。
# 代價寫明:repo 根目錄新增的 .py 不在這個範圍內。
echo "[16/19] 靜態與安全檢查(本 repo 自己的程式碼;tools/ 由漂移檢查涵蓋)"
$PY tools/autopilot/scripts/static_check.py --repo . --paths skills plugins > /dev/null

echo "[17/19] 載體宣告閘(workflow 每一步具名附理由;唯一真相源不得偷讀載體身分)"
# 這道閘守的是本檔開頭那條「載體不可知」的硬規矩。它自己也在本檔裡跑——
# 閘不進載體就是裝飾,而本張整張講的就是這件事。
$PY scripts/carrier_manifest_check.py --self-test > /dev/null
$PY scripts/carrier_manifest_check.py --repo . > /dev/null

echo "[18/19] plugin 隨附 skill 副本同步"
$PY plugins/build_suite.py --check > /dev/null

echo "✅ 治理閘通過(唯一真相源:.github/ci_local.sh)"
