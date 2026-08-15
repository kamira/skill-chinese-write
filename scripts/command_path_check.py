#!/usr/bin/env python3
"""command 引用路徑的雙住址閘——寫在 command 裡的路徑,兩個住址都要指得到。

## 這道閘補的洞

`CHG-20260814-05` 自己列了一種失敗模式:「相對路徑在兩個住址不等價」。
當時我是**手跑**證明 `../skills/fiction/references/dialogue.md` 在
`commands/` 與 `plugins/fiction/commands/` 兩處都解析得到——**那是佈局巧合,
不是斷言保證**,而批量搬遷的五支每支都會帶這類路徑。

## 兩類引用,兩種基準

審議席(codex)裁定兩類都要驗:「markdown 連結與文中可執行的 lint 指令路徑,
兩者都是使用者依賴的介面」。但它們的**基準不同**:

| 載體 | 基準 | 雙住址的意思 |
|---|---|---|
| markdown 連結 `](target)` | **該實體自己所在的目錄** | 檔案的兩個所在地 |
| 程式碼載體裡的 token | **根** | repo root 與 `plugins/<p>/` 兩個根 |

硬併成一條規則會掩蓋錯誤(codex),所以判準寫成**帶基準的分類條款**。

## 抽取順序是判準的一部分

`fiction-long.md` 第 49 行是:

    [`references/dialogue.md`](../skills/fiction/references/dialogue.md)

**連結文字本身是一個路徑狀的 code span。** 抽取器若先掃反引號,
`references/dialogue.md` 會被當成程式碼載體 token、以根為基準、解析不到、
**在一份完全正確的檔案上假紅**。

審議席稱它是 R4 的孿生:「不是規則恆真,是**規則對正確輸入恆假**。」
所以順序是規範:**先消費 markdown 連結**(連結全文——含文字裡的 code span
——從掃描流移除),殘餘文字再掃程式碼載體。

## 範圍是封閉文法,不是列舉

`CHG-20260814-07` 的 R3 被否掉過列舉式寫法(「plugin.json、README **等**」),
理由是列舉會讓下一個東西靜默漏網。這裡同理:範圍列的是**載體文法**,
而載體文法是封閉的——markdown 連結、程式碼載體(圍籬 + 行內 code span)。
過濾用**判定式**不用名單。

**不設 ignore 名單。** 閘側的豁免名單就是列舉式的鏡像,下一個真缺陷會住進名單裡。
要寫刻意不存在的路徑,用**不可抽取形**表達(角括號佔位、含 CJK 段),
豁免因此在文本裡看得見,審稿的人一眼知道那是刻意的假。

## 不在契約內的東西也要具名

**裸文路徑**(不在連結、不在反引號)不在本閘的契約內。
使用者要依賴的路徑必須放進兩種載體之一——這把逃逸路徑變成**寫作規範違規**,
而不是閘的靜默盲區。

`commands/` 裡未登記的檔、名冊裡缺來源的條目,是 `build_suite.sync_commands`
反向斷言的轄區,本閘只迭代名冊配對。寫在這裡免得兩閘互以為對方在管。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# markdown 連結/圖片:整類全收,過濾在下面用判定式
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
# 程式碼載體:圍籬與行內 code span
FENCE = re.compile(r"```.*?```", re.S)
CODESPAN = re.compile(r"`([^`\n]+)`")

SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
PLACEHOLDER = re.compile(r"[<>]")          # 角括號佔位 = 刻意的假,與 PLACEHOLDER_RE 同慣例
CJK = re.compile(r"[一-鿿]")                # 含中文段的示意路徑同理
VAR = re.compile(r"\$")                    # $ARGUMENTS 之類


def _is_pathish(tok: str) -> bool:
    """程式碼載體裡哪些 token 算路徑。**判定式,不是名單。**

    至少一個 `/`、純 ASCII 路徑字元、無 scheme、無角括號佔位、無變數。
    `稿件.md`(無斜線)、`--genre long`、`fiction_rules.json`(單檔名)、
    `$ARGUMENTS` 因此天然不進場——不是被名單排除的。
    """
    if "/" not in tok:
        return False
    if SCHEME.search(tok) or PLACEHOLDER.search(tok) or CJK.search(tok) or VAR.search(tok):
        return False
    return bool(re.fullmatch(r"[\w./-]+", tok))


def extract(text: str) -> tuple[list[str], list[str]]:
    """回傳 (markdown 連結目標, 程式碼載體路徑 token)。

    **順序是規範,不是實作細節。** 先消費連結(連結全文移出掃描流),
    殘餘文字再掃程式碼載體。反過來的話,連結文字裡的路徑狀 code span
    會被當成 token,在一份完全正確的檔案上假紅。
    """
    links: list[str] = []
    for m in LINK.finditer(text):
        t = m.group(1).split("#", 1)[0].strip()
        if t and not SCHEME.search(t) and not PLACEHOLDER.search(t):
            links.append(t)
    rest = LINK.sub(" ", text)          # 連結全文(含文字裡的 code span)整段移除

    toks: list[str] = []
    for blk in FENCE.findall(rest):
        for w in re.split(r"\s+", blk):
            if _is_pathish(w):
                toks.append(w)
    for blk in FENCE.sub(" ", rest).split("\n"):
        for m in CODESPAN.finditer(blk):
            # **span 內容要再切詞。** 初版把整段當一個 token,於是
            # `python3 skills/s/run.py` 這種多字 span 因為含空白而被判定式否掉
            # ——行內 code span 這條支路對多字內容是死的。案 R7 抓到的。
            for w in re.split(r"\s+", m.group(1).strip()):
                if _is_pathish(w):
                    toks.append(w)
    return links, toks


def check_one(repo: Path, plugin: str, name: str) -> list[str]:
    """一組 (plugin, 命令檔) 的雙住址斷言。

    兩份實體都查,**不依賴「sync 保證 byte-identical 所以查一份就好」**
    ——那是把本閘的正確性掛在另一道閘上。成本為零,自足。
    """
    bad: list[str] = []
    homes = {
        "頂層": repo / "commands" / name,
        f"plugin({plugin})": repo / "plugins" / plugin / "commands" / name,
    }
    roots = {"repo root": repo, f"plugin root({plugin})": repo / "plugins" / plugin}

    for where, f in homes.items():
        if not f.is_file():
            bad.append(f"{name}:{where} 實體不存在({f.relative_to(repo).as_posix()})")
            continue
        links, toks = extract(f.read_text(encoding="utf-8", errors="ignore"))
        # (a) 連結以**該實體自己所在目錄**為基準
        for t in links:
            if t.startswith("/"):
                bad.append(f"{name}({where}):連結「{t}」是絕對路徑,兩個住址都不成立")
                continue
            if not (f.parent / t).resolve().is_file():
                bad.append(f"{name}({where}):連結「{t}」以自身目錄為基準解析不到")
        # (b)(c) 程式碼載體 token 以**兩個根**為基準
        for t in toks:
            if t.startswith("../"):
                bad.append(f"{name}({where}):程式碼裡的「{t}」用了 ../"
                           "——指令是從某個根執行的,不是從檔案目錄")
                continue
            for rname, root in roots.items():
                if not (root / t).is_file():
                    bad.append(f"{name}({where}):程式碼路徑「{t}」在 {rname} 下不存在")
    return bad


def load_commands(repo: Path) -> dict[str, tuple[str, ...]]:
    """讀 `build_suite.py` 的 COMMANDS——**單一登記簿,不另抄一份**。"""
    src = (repo / "plugins" / "build_suite.py").read_text(encoding="utf-8")
    m = re.search(r"^COMMANDS[^=]*=\s*\{(.*?)^\}", src, re.S | re.M)
    if m is None:
        raise SystemExit("讀不到 build_suite.py 的 COMMANDS——名冊形狀變了,本閘失效")
    out: dict[str, tuple[str, ...]] = {}
    for e in re.finditer(r"""["']([\w.-]+)["']\s*:\s*\(([^)]*)\)""", m.group(1)):
        out[e.group(1)] = tuple(x.strip().strip("'\"")
                                for x in e.group(2).split(",") if x.strip())
    if not out and re.search(r"\S", m.group(1)):
        raise SystemExit("COMMANDS 區塊有內容卻一個條目都 parse 不出來"
                         "——**空 dict 不得與『解析失敗』同義**")
    return out


def check(repo: Path) -> list[str]:
    bad: list[str] = []
    for plugin, names in sorted(load_commands(repo).items()):
        for n in sorted(names):
            bad += check_one(repo, plugin, n)
    return bad


# ---------------------------------------------------------------- self-test
_REG = ('EXCLUDE = ("__pycache__", ".DS_Store")\n'
        'PLUGINS = {\n    "p": (\'s\',),\n}\n'
        'COMMANDS = {\n    "p": ("c.md",),\n}\n')


def _w(root: Path, rel: str, body: str = "x\n") -> None:
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body, encoding="utf-8")


def _tree(root: Path, cmd_body: str, root_side: list[str], plug_side: list[str]) -> None:
    """造一棵最小假樹。`root_side` / `plug_side` 分別是只存在於該側的目標檔。

    兩份 command 實體 **byte-identical**(sync 後的真實狀態),
    差別只在周邊檔案存不存在——這樣才驗得到「同一份內容在兩個住址不等價」。
    """
    _w(root, "plugins/build_suite.py", _REG)
    _w(root, "commands/c.md", cmd_body)
    _w(root, "plugins/p/commands/c.md", cmd_body)
    for rel in root_side:
        _w(root, rel)
    for rel in plug_side:
        _w(root, rel)


def self_test() -> int:
    import tempfile

    ran: list[str] = []
    fails: list[str] = []

    def case(label, cmd_body, root_side, plug_side, want):
        ran.append(label)
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            _tree(r, cmd_body, root_side, plug_side)
            got = check(r)
            hit = any(want in g for g in got) if want else not got
            if not hit:
                fails.append(f"{label}:want={want!r} got={got}")

    # 兩側齊備的目標(綠案用)
    BOTH_LINK = ["skills/s/ref.md", "plugins/p/skills/s/ref.md"]
    BOTH_TOK = ["skills/s/run.py", "plugins/p/skills/s/run.py"]

    # ---- G1 基準判別性綠案:`../` 連結,兩個住址都通。
    # **實作若誤用根基準,`../` 會逃出根 → 本案立刻紅。**
    # 一個在兩種基準下都解析得到的夾具什麼都證明不了,不准出現在這裡。
    case("G1 綠:../ 連結雙住址皆通",
         "[參考](../skills/s/ref.md)\n", BOTH_LINK, [], None)

    # ---- G2 基準判別性綠案:根錨定 token,兩個根都通。
    # **實作若誤用檔案目錄基準,`commands/skills/s/run.py` 不存在 → 立刻紅。**
    case("G2 綠:根錨定 token 雙根皆通",
         "```\npython3 skills/s/run.py\n```\n", BOTH_TOK, [], None)

    # ---- G3 抽取順序:連結文字本身是路徑狀 code span。
    # 這是真實 repo 現有的寫法。先掃反引號的實作會把 `skills/s/ref.md`
    # 當成根基準 token,而它在 plugin 根下也在——所以要用一個**只有連結側成立**
    # 的目標才驗得出來:`../skills/s/ref.md` 兩住址通,但同名 token 若被誤抽,
    # 會以根為基準去找 `skills/s/ref.md`,那個檔在兩根下都在……
    # 因此改用一個**連結文字與連結目標不同**的寫法,誤抽時目標不存在。
    case("G3 綠:連結文字是路徑狀 code span(抽取順序)",
         "[`refs/dialogue.md`](../skills/s/ref.md)\n", BOTH_LINK, [], None)

    # ---- R1:連結目標在 root 側有、plugin 側沒有
    case("R1 紅:連結 × plugin 住址",
         "[參考](../skills/s/ref.md)\n", ["skills/s/ref.md"], [], "以自身目錄為基準解析不到")

    # ---- R2:鏡像
    case("R2 紅:連結 × root 住址",
         "[參考](../skills/s/ref.md)\n", [], ["plugins/p/skills/s/ref.md"],
         "以自身目錄為基準解析不到")

    # ---- R3:token 在 repo root 下有、plugin root 下沒有。
    # **這是批量搬遷真正要抓的缺陷型**:command 引用了該 plugin 沒打包的 skill。
    case("R3 紅:token × plugin 根(引用了沒打包的 skill)",
         "```\npython3 skills/s/run.py\n```\n", ["skills/s/run.py"], [],
         "在 plugin root(p) 下不存在")

    # ---- R4':鏡像
    case("R4' 紅:token × repo 根",
         "```\npython3 skills/s/run.py\n```\n", [], ["plugins/p/skills/s/run.py"],
         "在 repo root 下不存在")

    # ---- R5:唯一引用只在圍籬內 → 抽取器的圍籬支路必須活著
    case("R5 紅:圍籬支路",
         "```\npython3 skills/s/gone.py\n```\n", BOTH_TOK, [], "程式碼路徑")

    # ---- R6:唯一引用只是 markdown 連結 → 連結支路必須活著
    case("R6 紅:連結支路", "[參考](../skills/s/gone.md)\n", BOTH_LINK, [], "連結")

    # ---- R7:行內 code span 的 token(非圍籬)
    case("R7 紅:行內 code span 支路",
         "跑 `python3 skills/s/gone.py` 交稿\n", BOTH_TOK, [], "程式碼路徑")

    # ---- R8:程式碼裡用 ../ 一律違規——指令是從根執行的
    case("R8 紅:程式碼裡的 ../",
         "```\npython3 ../skills/s/run.py\n```\n", BOTH_TOK, [], "用了 ..")

    # ---- R9:絕對路徑連結
    case("R9 紅:絕對路徑連結", "[參考](/skills/s/ref.md)\n", BOTH_LINK, [], "絕對路徑")

    # ---- G4:刻意的假路徑用不可抽取形表達,不靠閘側名單
    case("G4 綠:角括號佔位不進場",
         "```\npython3 <plugin>/commands/<命令>.md\n```\n", [], [], None)

    if fails:
        for f in fails:
            print(f"  ❌ {f}")
        print("\n✗ self-test 未通過:command 引用路徑閘的紅綠端不可達。")
        return 1
    print(f"✅ self-test:{len(ran)} 案全過——"
          "基準判別性綠端三條(../ 連結、根錨定 token、連結文字是 code span)、"
          "雙住址紅端四條(連結×兩住址、token×兩根)、"
          "抽取支路三條(圍籬 / 行內 code span / 連結)、"
          "形狀兩條(程式碼裡的 ../、絕對路徑連結)、"
          "不可抽取形一條。")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    repo = Path(".").resolve()
    if "--repo" in argv:
        repo = Path(argv[argv.index("--repo") + 1]).resolve()
    reg = load_commands(repo)
    bad = check(repo)
    if bad:
        print("✗ command 引用路徑閘:")
        for b in bad:
            print("  - " + b)
        print("\n  連結以**檔案自己的目錄**為基準,程式碼路徑以**兩個根**為基準。"
              "\n  要寫刻意不存在的路徑,用角括號佔位或含中文段的示意形"
              "——豁免要在文本裡看得見,本閘沒有 ignore 名單。")
        return 1
    pairs = sum(len(v) for v in reg.values())
    n_link = n_tok = 0
    for plugin, names in reg.items():
        for n in names:
            f = repo / "commands" / n
            if f.is_file():
                a, b = extract(f.read_text(encoding="utf-8", errors="ignore"))
                n_link += len(a); n_tok += len(b)
    # **印出抽取數。** 「抽出 0 條」是無聲空洞,而空洞與通過在退出碼上一樣。
    # 但不對真實語料訂最低條數——那是 CHG-20260810-10 拆掉的那種自己發明的下限。
    print(f"✅ command 引用路徑閘:{pairs} 組 (plugin, 命令) × 2 個住址;"
          f"抽到連結 {n_link} 條、程式碼路徑 {n_tok} 條(頂層實體計)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
