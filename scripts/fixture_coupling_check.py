#!/usr/bin/env python3
"""
fixture_coupling_check.py — 夾具不得逐字引用規則自己的例句(唯讀;不改任何檔)

## 這道閘擋的是什麼

夾具引用規則文件的示範句,等於**用考古題驗考生**:lint 對那些句子必然綠燈,
因為規則就是照它們校準的。這不是單一 regex 抓不抓得到的問題,是整類
「夾具永遠測不到規則」的失效模式。

CHG-20260813-01 D-4 實錘四處:

| 夾具 | 與什麼逐字相同 |
|---|---|
| `writing/sample-good.md` | `voice.md` / `commentary.md` 的示範例句 |
| `writing/sample-issue.md` | `commentary.md` 的感受示範句 |
| `fiction-romance/sample-good.md` 結尾 | `zh_style_rules.json` 的 flat_ending 修正示範句 |
| `prose/sample-good.md` 結尾 | `zh_style_check.py` 的 self-test GOOD 字串 |

## 這道閘**擋不到**什麼(照 KN-001 的第二條路,明講而不假裝)

**只擋逐字層。骨架同構完全不在射程內。**

驗收審議在本閘上線後審新寫的 `writing/sample-good.md`,結論是:逐字重疊清乾淨了,
但它仍然是「照規則文件的示範例句**重新裝潢**出來的」——句級骨架(「省下的是 A,
賠掉的是 B」→「診所省下一個櫃檯,我媽付掉的是⋯」)、命題骨架、章法順序三層都能
回溯到 `references/`,而本閘一處都抓不到。

骨架同構同樣會讓夾具測不到規則,危害與逐字抄一樣。它判不了——比對的是結構不是字面,
現有做法都會誤殺正常寫作。**所以這一層靠人讀**,不要因為本閘綠燈就以為耦合這件事
已經有閘了。

## 判準

比對 `skills/*/assets/sample-*.md`(夾具)與規則側檔案
(`skills/*/references/*.md`、`skills/*/assets/*_rules.json`、`skills/*/scripts/*.py`),
找出**連續 N 個中文字元完全相同**的片段。N 預設 10——短於此的共用片語
(「這個房間」「他說」)是自然重合,不是抄。

只看中文字元:標點、空白、markdown 記號一律先剝掉,避免因為排版差異而漏抓。

## 退出碼

0 沒有耦合 | 1 有耦合 | 2 環境/參數錯誤
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# 中文字元**與數字**。數字要留(理由見 cjk_only)。
CJK = re.compile(r"[一-鿿0-9０-９]+")
DEFAULT_N = 10

# 法定固定用語:比對前先剝掉。
#
# 這**不是**豁免文體,是豁免**句子**——兩位審議者獨立收斂到同一個做法。
# 「請查照並轉知所屬依規定辦理」本身 12 字,兩份題材完全無關、各自獨立寫成的公文
# 都會一字不差地寫它,因為那是法定行文,不寫才是錯的。這種重合沒有任何資訊量。
#
# 與初版「整組豁免 bizdoc/techdoc」的差別:那個做法讓**整份文件**免檢,
# 只要包裝成公文就能夾帶抄來的示範句;這裡只拿掉逐字列舉的固定片語,
# 同一份公文的主旨內容、說明各款、辦法期限全部照常比對。
#
# 加新片語的門檻:必須是**法規或公文程式條例明定**的用語,不是「常見寫法」。
FORMAT_PHRASES = (
    "請查照並轉知所屬依規定辦理",
    "請查照並轉知所屬",
    "請查照辦理",
    "請查照",
    "函復本府備查",
    "本案奉核可後辦理",
)

# 夾具側
FIXTURE_GLOB = "skills/*/assets/sample-*.md"
# 規則側:寫規則與示範句的地方
RULE_GLOBS = ("skills/*/references/*.md", "skills/*/assets/*_rules.json",
              "skills/*/scripts/*.py", "skills/*/SKILL.md")

# 已知待清的耦合(**釘住的基準線,不是豁免**)
#
# 初版曾把 bizdoc / techdoc 家族整組豁免,理由是「格式即規則」。那個判準被驗收審議
# 判為**開後門**,而且理由成立:整組豁免等於只要把抄來的示範句包裝成公文,
# 就能繞過這道閘。已撤掉。
#
# 取而代之的是一份**逐對列舉**的基準線:這幾對是本閘上線時就存在的耦合,
# 清掉它們要重寫四份公文/技術文件夾具(讓夾具與 reference 的範本是同一種格式的
# **不同實例**),不在 CHG-20260813-01 的範圍內。
#
# 與豁免的差別有三:
#   1. 逐對列舉——換一個檔名就擋下來,包裝成公文也混不進去
#   2. **會印出來**,不是靜默跳過;掃描結果永遠說得出還欠幾對
#   3. 只准縮不准長:清單裡列了卻已經沒有耦合的項目,本閘會反過來要求你把它刪掉
#   4. 釘的是 **(檔案對, 片段數上限)**,不是只有檔案對。只釘對子的話,已釘住的兩個檔案
#      之間可以再抄十段新東西而閘依然綠——基準線會變成那一對的永久免死金牌。
#      片段數一超過上限就轉紅(V4 審議指出的最大洞)。
BASELINE = {
    ("skills/bizdoc/assets/sample-bad.md", "skills/bizdoc/references/press.md"): 2,
    ("skills/techdoc/assets/sample-arch-good.md", "skills/techdoc/references/architecture.md"): 2,
}


def cjk_only(text: str) -> str:
    """只留中文字元與數字。標點/空白/markdown 記號剝掉——排版差異不該讓抄襲逃掉。

    **數字必須保留。** 初版連數字一起剝,於是
    「依本府 115 年 7 月 30 日府資字第 1150073012 號函辦理」與
    「依本府 116 年 2 月 3 日府教字第 1160021001 號函辦理」
    被壓成同一串「依本府年月日府資字第號函辦理」——兩份引用**不同來函**的公文
    因此被判為逐字重合。那不是抄,是數字被剝掉後的格式殘影(CHG-20260813-01,V4 審議)。

    法定固定用語(FORMAT_PHRASES)在比對前剝掉——理由見該常數的註解。
    順序很重要:**先正規化再剝片語**。反過來做的話,片語裡的字會先被抽出來與鄰字黏在
    一起(join 用空字串),replace 就對不上了。

    **剝掉就是剝掉,不要插哨兵。** 初版把片語換成 `\x00` 想切斷 run,結果開了一個
    我自己造的後門:把抄來的句子**每 9 個字插一次「請查照」**,兩側殘段都短於 N,
    shingle 一個都配不上,閘全盲(V5 審議實測:38 字整句照抄 → 共用片段 0)。
    另外六個片語共用同一個哨兵,還會讓兩份引用**不同**法定用語、前後文相同的公文
    被判為重合(實測 15 個假片段),而且 `\x00` 會被印進 CI log。
    換成直接刪除之後,插入攻擊反而**自己失效**——插進去的字被移除,兩側重新對齊,
    照抄的部分照樣配得上。
    """
    s = "".join(CJK.findall(text))
    for ph in FORMAT_PHRASES:
        s = s.replace(ph, "")
    return s


def shingles(text: str, n: int) -> set[str]:
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def longest_run(body: str, rule_body: str, common: set[str], n: int) -> str:
    """從共用的 n 字片段往右延伸,找出實際最長的一段共用文字。

    所有 shingle 長度都是 n,所以直接比長度是沒有意義的——初版就寫成
    `max(common, key=len)` 加一個第一行就 break 的 while,整段是死碼,
    只是隨機挑一個片段來印。訊息因此常常從句子中間切開,讀起來像亂碼
    (例如「度資料匯出作業修正規」)。這裡真的把它延伸出來。
    """
    # 複雜度上限。初版對每個 shingle 都從頭延伸,每步做一次全文 `in rule_body` 搜尋——
    # O(|common| × run長 × |rule|)。V5 審議實測:3000 字整段抄自 20000 字規則檔,
    # **單一配對就要 29.1 秒**,而觸發它的輸入正是這道閘存在的理由(大段逐字抄)。
    # 訊息只是為了讓人讀懂,不值得二次方:取樣前 SAMPLE 個 shingle,延伸長度封頂。
    SAMPLE, MAX_RUN = 40, 200
    best = ""
    for c in sorted(common)[:SAMPLE]:
        start = body.find(c)
        if start < 0:
            continue
        end = start + n
        limit = min(len(body), start + MAX_RUN)
        while end < limit and body[start:end + 1] in rule_body:
            end += 1
        if end - start > len(best):
            best = body[start:end]
    return best or next(iter(sorted(common)))


def skill_of(p: Path, repo: Path) -> str:
    """skills/<name>/... → <name>"""
    parts = p.relative_to(repo).parts
    return parts[1] if len(parts) > 1 else ""


def scan(repo: Path, n: int) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    """回傳 (新耦合, 基準線內仍存在的耦合, 已消失但還列在基準線的項目)。"""
    fixtures = sorted(repo.glob(FIXTURE_GLOB))
    rule_files = []
    for g in RULE_GLOBS:
        rule_files.extend(sorted(repo.glob(g)))

    if not fixtures:
        # **錯誤,不是警告。** 初版在這裡 return 空清單、rc 0——夾具搬家或 glob 打錯,
        # 這道閘就靜默綠燈通過。規則側 glob 壞掉反而會紅(BASELINE 全變 stale),
        # 兩側不對稱正是最容易漏掉的那種洞(V4 審議)。
        raise LookupError(f"找不到任何夾具({FIXTURE_GLOB})——這道閘等於沒跑")

    rule_index: list[tuple[Path, set[str], str]] = []
    for rf in rule_files:
        try:
            body = cjk_only(rf.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        if len(body) >= n:
            rule_index.append((rf, shingles(body, n), body))

    problems, known, seen_pairs = [], [], set()
    for fx in fixtures:
        body = cjk_only(fx.read_text(encoding="utf-8", errors="ignore"))
        if len(body) < n:
            continue
        fx_sh = shingles(body, n)
        for rf, rule_sh, rule_body in rule_index:
            common = fx_sh & rule_sh
            if not common:
                continue
            longest = longest_run(body, rule_body, common, n)
            pair = (fx.relative_to(repo).as_posix(), rf.relative_to(repo).as_posix())
            seen_pairs.add(pair)
            line = (f"{pair[0]} ↔ {pair[1]}\n"
                    f"    共用 {len(common)} 個 {n} 字片段,例如「{longest}」")
            cap = BASELINE.get(pair)
            if cap is None:
                problems.append(line)
            elif len(common) > cap:
                # 釘住的對子**只准縮不准長**:在已釘住的兩個檔案之間再抄新的東西,
                # 同樣要轉紅,否則基準線就成了那一對的永久免死金牌。
                problems.append(line + f"\n    ← 基準線上限 {cap},現在 {len(common)}"
                                       f"——釘住的對子裡又長出新的耦合")
            elif len(common) < cap:
                # **降下來就要把上限一起調降,否則棘輪只鎖一半。**
                # 只印勸告不轉紅的話,2 → 1 是綠、之後再抄回 2 也是綠,cap 以內的
                # 回漲永遠不會紅(V5 審議)。所以這裡也擋。
                problems.append(line + f"\n    ← 已降到 {len(common)}(上限 {cap}),"
                                       f"請把 BASELINE 的上限一起改成 {len(common)}"
                                       f"——不改的話,以後抄回 {cap} 也不會有人發現")
            else:
                known.append(line + f"(上限 {cap})")

    stale = sorted(set(BASELINE) - seen_pairs)
    return problems, known, stale


def scan_draft(repo: Path, draft: Path, n: int) -> list[str]:
    """成品掃描:一篇新產出的稿子,對「規則檔 + references + 已收成的歷史樣稿」比對。

    **這是把「登記指紋」從人工追認改成機器自動的那一步。**
    前四輪的做法是:產文 → 審議席讀出跨題目重複的句子 → 回頭改示範句。
    那條路不收斂——實測換掉一個示範句就長出另一個指紋,而本輪**剛加進**的
    收尾示範,當輪就被新產出採用(CHG-20260814-01)。
    有了這個模式,任何新指紋**第一次重複就被抓**,不用等下一輪審議發現。
    """
    corpus: list[tuple[Path, set[str], str]] = []
    globs = list(RULE_GLOBS) + [FIXTURE_GLOB]
    for g in globs:
        for f in sorted(repo.glob(g)):
            body = cjk_only(f.read_text(encoding="utf-8", errors="ignore"))
            if len(body) >= n:
                corpus.append((f, shingles(body, n), body))
    if not corpus:
        raise LookupError("比對語料是空的——這道閘等於沒跑")

    body = cjk_only(draft.read_text(encoding="utf-8", errors="ignore"))
    if len(body) < n:
        return []
    dsh = shingles(body, n)
    out = []
    for f, csh, cbody in corpus:
        common = dsh & csh
        if common:
            out.append(f"{f.relative_to(repo).as_posix()}\n"
                       f"    共用 {len(common)} 個 {n} 字片段,"
                       f"例如「{longest_run(body, cbody, common, n)}」")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="夾具不得逐字引用規則自己的例句")
    ap.add_argument("--repo", default=".", help="repo 根目錄")
    ap.add_argument("-n", type=int, default=DEFAULT_N,
                    help=f"視為耦合的連續中文字元數(預設 {DEFAULT_N})")
    ap.add_argument("--draft", default=None,
                    help="成品掃描模式:給一篇新產出的稿子,對規則檔 + references + "
                         "歷史樣稿比對。抓的是「教材被當成句型抄走」")
    ap.add_argument("--self-test", action="store_true",
                    help="紅燈可達自檢:造一組必紅與一組必綠的輸入")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test(args.n)

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"ERROR: 找不到 {repo}", file=sys.stderr)
        return 2

    if args.draft:
        dp = Path(args.draft)
        if not dp.is_file():
            print(f"ERROR: 找不到 {dp}", file=sys.stderr)
            return 2
        try:
            hits = scan_draft(repo, dp, args.n)
        except LookupError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        if hits:
            print(f"\n✗ 這篇成品與教材/歷史樣稿有 {len(hits)} 處逐字重合:\n")
            for h in hits:
                print("  " + h)
            print("\n示範句是在教動作,不是給句型。把重合的部分改掉——"
                  "\n這些句子在其他產出裡也會出現,重複本身就是 AI 味。")
            return 1
        print(f"✅ 這篇成品與教材/歷史樣稿無 {args.n} 字以上的逐字重合。")
        return 0

    try:
        problems, known, stale = scan(repo, args.n)
    except LookupError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    rc = 0

    if stale:
        print(f"\n✗ 基準線有 {len(stale)} 對已經沒有耦合了,請從 BASELINE 刪掉:")
        for a, b in stale:
            print(f"    {a} ↔ {b}")
        print("  基準線只准縮不准長——留著已清乾淨的項目,下次就會有人拿它當豁免用。")
        rc = 1

    if problems:
        print(f"\n✗ 夾具與規則文件逐字耦合 {len(problems)} 處(基準線之外):\n")
        for p in problems:
            print("  " + p)
        print("\n夾具引用規則自己的示範句 = 用考古題驗考生:lint 對那些句子必然綠燈,"
              "\n因為規則就是照它們校準的。改寫夾具,不要改規則去遷就它。")
        rc = 1

    if known:
        # 基準線內的**印出來**,不靜默跳過——掃描結果永遠說得出還欠幾對。
        print(f"\n⚠ 基準線內既有耦合 {len(known)} 對(待另開 CHG 重寫,不擋本次):")
        for k in known:
            print("  " + k)

    if rc == 0:
        print(f"\n✅ 基準線之外無 {args.n} 字以上的逐字重疊。")
    return rc


def _mk(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def self_test(n: int) -> int:
    """端到端紅燈可達自檢。

    初版的自檢是 `shingles(same, n) & shingles(same, n)`——**一個集合跟它自己取交集**,
    只要字串長度 ≥ n 就不可能失敗。它宣稱證明了「紅燈可達」,實際只證明了 set 交集運算
    沒壞:`cjk_only` 剝標點、glob 掃檔、`scan()` 配對、BASELINE 分類、stale 偵測、rc 1
    ——真正的紅燈路徑一步都沒走到(V4 審議)。

    現在改成在暫存目錄造真的假 repo,跑完整 `scan()`,驗五件事:
      1. 逐字重疊 → 紅(且**排版與標點不同也要抓到**,這才驗到 cjk_only)
      2. 不同文字 → 綠
      3. 恰好 n-1 字 → 綠(邊界)
      4. 基準線列了卻已無耦合 → 紅(stale 分支,原本零覆蓋)
      5. 夾具 glob 落空 → **錯誤**,不是綠燈
    """
    import tempfile
    global BASELINE
    # 自己造的字串,不借任何夾具、任何引擎 self-test 的句子——本分支自己立的原則
    # (V5 審議附帶觀察:初版這裡與 zh_style_check.py 新造的 GOOD 字串同源)。
    shared = "鐵皮屋頂上的積水在半夜滑下來砸在雨遮邊緣然後安靜了"   # 25 字
    other = "廟裡的燈滅了兩個人誰也沒有先動雨還在下沒有停"
    fails = []

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # 規則側寫成一般散文;夾具側加上標點與 markdown——排版不同,內容相同。
        _mk(root, "skills/t/references/r.md", f"# 示範\n\n{shared}\n")
        _mk(root, "skills/t/assets/sample-copy.md", f"**{shared[:10]}**,{shared[10:]}。\n")
        _mk(root, "skills/t/assets/sample-clean.md", other + "\n")
        _mk(root, "skills/t/assets/sample-edge.md", shared[:n - 1] + "然後就走開了\n")

        saved, BASELINE = BASELINE, {}
        try:
            problems, known, stale = scan(root, n)
        finally:
            BASELINE = saved
        hit = {p.split(" ↔ ")[0] for p in problems}
        if "skills/t/assets/sample-copy.md" not in hit:
            fails.append("逐字重疊(標點與 markdown 不同)竟然沒被抓到——cjk_only 或配對壞了")
        if "skills/t/assets/sample-clean.md" in hit:
            fails.append("不相干的文字被判為耦合——判定過鬆")
        if "skills/t/assets/sample-edge.md" in hit:
            fails.append(f"只共用 {n - 1} 字竟然被判耦合——邊界錯了")

        # stale 分支:釘一對根本不存在耦合的,必須轉紅
        saved, BASELINE = BASELINE, {("skills/t/assets/sample-clean.md",
                                      "skills/t/references/r.md"): 99}
        try:
            _, _, stale2 = scan(root, n)
        finally:
            BASELINE = saved
        if not stale2:
            fails.append("基準線列了卻已無耦合,竟然沒轉紅——stale 分支不可達")

    # 夾具 glob 落空必須是錯誤,不是綠燈
    with tempfile.TemporaryDirectory() as td2:
        try:
            scan(Path(td2), n)
            fails.append("夾具一份都掃不到,竟然沒有報錯——這道閘會靜默通過")
        except LookupError:
            pass

    if fails:
        for f in fails:
            print(f"  ❌ {f}")
        print("\n✗ self-test 未通過:這道閘的紅燈或綠燈不可達。")
        return 1
    print("✅ self-test:逐字重疊(含排版不同)會紅、不相干文字會綠、"
          f"{n - 1} 字邊界不誤殺、stale 會紅、夾具掃不到會報錯——五端皆可達。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
