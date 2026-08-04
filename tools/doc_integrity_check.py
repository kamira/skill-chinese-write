#!/usr/bin/env python3
"""
doc_integrity_check.py — 文檔抗漂移的機器檢查 / doc-integrity enforcement

把 doc-integrity 從「靠自律遵守」變成「CI / pre-commit 可擋」。它不替你寫文件的語意內容
(那需要人/agent),但會把可機器判斷的漂移擋下,逼你補齊。

檢查項:
  1) 結構漂移:本次(staged)改了結構性程式(預設比對 models / schema / migration / .proto),
     卻沒有一併更動 docs/structure/ → 失敗。(對應「改結構就要同步結構文件」)
  2) CHG↔ACC 連結:docs/changes/ 內狀態為「已實作 / Implemented」(非草稿、非暫停)的 CHG,
     若 docs/acceptance/ 沒有任何 ACC 提到它 → 失敗。(對應「當場驗收、不可懸空」;
     「暫停 / Paused」為合法 WIP,跳過)
  3) 模板欄位 lint:CHG 必填 風險分級/Risk、實作者/Implemented by、狀態/Status;
     ACC 必填 驗收者/Verifier、結論/Conclusion、風險分級/Risk。缺 → 失敗。
     (--require-branch / --require-commit 額外強制 Branch、Commit/PR 欄)
  4) secrets 掃描:docs/ 內出現疑似金鑰/token/私鑰 → 失敗。(文件長存共用,不可含 secrets)
  5) commit 治理掃描(--commits-since <ref>):<ref>..HEAD 的每個 commit message 都應
     引用 CHG/XCHG 編號;沒有 → 失敗。(對應「commit 粒度 / commit 錨定」)
  6) 知識庫先建:受治理 repo(有 docs/changes/)必有 docs/knowledge/ → 缺 = 失敗。
     (對應 knowledge「先建」與 handshake 進場補建;容器不存在,自主記錄永遠不會發生)
  7) 重複性檢查欄:Skill ≥ v1.17 的 CHG 必有「重複性檢查/Recurrence check」欄 → 缺 = 失敗。
     (前瞻適用;對應 modification-guide 第 7 步收尾比對)

用法 / usage:
  # pre-commit(staged 結構漂移 + CHG/ACC + 欄位 + secrets):
  python3 doc_integrity_check.py --staged
  # 全 repo 掃描(CI / 手動):
  python3 doc_integrity_check.py --repo .
  # 進場 handshake 的 commit 掃描(錨點=最後治理 commit / tag):
  python3 doc_integrity_check.py --repo . --commits-since <anchor>
  # 自訂結構性路徑(regex,可多個):
  python3 doc_integrity_check.py --staged --structural 'models/' 'schema' '\\.proto$'
  # 逃生口:--no-field-lint / --no-secret-scan

退出碼:0 = 通過;1 = 偵測到問題;2 = 環境/參數錯誤。
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# 釘住輸出編碼(CHG-20260803-01 T1):不依賴主控台/locale 的 ambient 編碼。
# 非 UTF-8 主控台(如 Windows cp932)印 CJK/emoji 會 UnicodeEncodeError;
# 釘住後同一份程式在任何平台的輸出行為一致。errors="replace" 確保永不因輸出而崩潰。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_STRUCTURAL = [r"models?/", r"schema", r"migrations?/", r"\.proto$", r"entities?/"]
CHG_RE = re.compile(r"X?CHG-\d{8}-\d+", re.IGNORECASE)
# 視為「已實作、應有 ACC」的狀態字樣
IMPLEMENTED_HINTS = ["已實作", "已驗收", "implemented", "accepted", "待驗收", "待 acceptance", "pending acceptance"]
DRAFT_HINTS = ["草稿", "draft"]
PAUSED_HINTS = ["暫停", "paused"]
# CHG-lite:低風險 + 內嵌自驗 → 豁免獨立 ACC 檔(見 modification-guide「CHG-lite」)
SELF_ACC_RE = re.compile(r"自驗|self-?verified", re.IGNORECASE)
LOW_RISK_RE = re.compile(r"(風險分級|Risk)\s*[::]\s*[^\n]{0,40}?(低|low)", re.IGNORECASE)
# 審議會:高風險已實作 CHG 必附審議判決(見 review-panel)
HIGH_RISK_RE = re.compile(r"(風險分級|Risk)\s*[::]\s*[^\n]{0,40}?(高|high)", re.IGNORECASE)
VERDICT_RE = re.compile(r"\[verdict\]|審議判決|Review verdicts", re.IGNORECASE)

# --- 欄位 lint(雙語;pattern 命中任一即算有該欄) ---
CHG_REQUIRED_FIELDS = {
    # Risk 允許行首或 lite 單行式的「| Risk:」位置
    "風險分級/Risk": re.compile(r"(風險分級|(^|\|)\s*\-?\s*Risk)\s*[::]", re.MULTILINE),
    "實作者/Implemented by": re.compile(r"(實作者|Implemented by)\s*[::]"),
    "狀態/Status": re.compile(r"^##\s*(狀態|Status)\b", re.MULTILINE),
}
ACC_REQUIRED_FIELDS = {
    "驗收者/Verifier": re.compile(r"(驗收者|Verifier)\s*[::]"),
    "結論/Conclusion": re.compile(r"(結論|Conclusion)\s*[::]"),
    "風險分級/Risk": re.compile(r"(風險分級|(^|\|)\s*\-?\s*Risk)\s*[::]", re.MULTILINE),
}
# 雙語(CHG-20260803-02):原本只認英文 "Branch",而本套件的 CHG 模板中文寫「分支」——
# 於是 `--require-branch` 對任何中文 CHG 都必然失敗,是一道永遠無法通過的閘。
# 其餘每個欄位樣式都是雙語的,這裡是漏網。變更方向只放寬不收緊:原本能過的仍然能過。
BRANCH_FIELD = re.compile(r"(Branch|分支)\s*[::]?")
COMMIT_FIELD = re.compile(r"Commit/PR\s*[::]")

# --- secrets 掃描(保守樣式,避免誤殺) ---
SECRET_PATTERNS = [
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("GitHub token", re.compile(r"(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,})")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.")),
    ("credential assignment", re.compile(
        r"(?i)(password|passwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*['\"][A-Za-z0-9+/_\-]{12,}['\"]")),
]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=True).stdout


def git_staged_files(repo: Path) -> list[str]:
    try:
        out = git(repo, "diff", "--cached", "--name-only")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [l.strip() for l in out.splitlines() if l.strip()]


def check_structural_sync(changed: list[str], structural: list[str]) -> list[str]:
    pats = [re.compile(p, re.IGNORECASE) for p in structural]
    structural_changed = [f for f in changed
                          if any(p.search(f) for p in pats) and not f.startswith("docs/")]
    docs_structure_changed = any(f.startswith("docs/structure/") for f in changed)
    problems = []
    if structural_changed and not docs_structure_changed:
        problems.append("改了結構性程式卻未同步 docs/structure/ — 觸發檔:\n    "
                        + "\n    ".join(structural_changed))
    return problems


def classify_status(text: str) -> str:
    low = text.lower()
    if any(h in low for h in PAUSED_HINTS):
        return "paused"
    is_draft = any(h in low for h in DRAFT_HINTS) and not any(
        h in low for h in ("已實作", "已驗收", "implemented", "accepted"))
    if is_draft:
        return "draft"
    if any(h.lower() in low for h in IMPLEMENTED_HINTS):
        return "implemented_or_accepted"
    return "unknown"


def check_chg_acc(repo: Path) -> list[str]:
    changes = sorted((repo / "docs" / "changes").glob("CHG-*.md")) if (repo / "docs" / "changes").is_dir() else []
    acc_dir = repo / "docs" / "acceptance"
    acc_text = ""
    if acc_dir.is_dir():
        for a in acc_dir.glob("ACC-*.md"):
            acc_text += a.read_text(encoding="utf-8", errors="ignore") + "\n"
    problems = []
    for chg in changes:
        text = chg.read_text(encoding="utf-8", errors="ignore")
        status = classify_status(text)
        if status in ("draft", "paused"):  # 草稿與暫停(合法 WIP)不要求 ACC
            continue
        if status == "unknown":
            continue
        if SELF_ACC_RE.search(text) and LOW_RISK_RE.search(text):
            continue  # CHG-lite:低風險內嵌自驗,免獨立 ACC
        m = CHG_RE.search(chg.stem) or CHG_RE.search(text)
        chg_id = m.group(0) if m else chg.stem
        if chg_id.lower() not in acc_text.lower():
            problems.append(f"{chg.name}({chg_id})已實作但 docs/acceptance/ 找不到對應 ACC — 驗收懸空")
        if HIGH_RISK_RE.search(text) and not VERDICT_RE.search(text):
            problems.append(f"{chg.name}({chg_id})為高風險且已實作,但無審議判決([verdict] / 審議判決節)— 高風險必須全席審議(見 review-panel)")
    return problems


def check_fields(repo: Path, require_branch: bool, require_commit: bool) -> list[str]:
    problems = []

    def lint(files, required, kind):
        for f in files:
            text = f.read_text(encoding="utf-8", errors="ignore")
            missing = [name for name, pat in required.items() if not pat.search(text)]
            if require_branch and not BRANCH_FIELD.search(text):
                missing.append("Branch")
            if require_commit and not COMMIT_FIELD.search(text):
                missing.append("Commit/PR")
            if missing:
                problems.append(f"{f.name}({kind})缺必填欄:{', '.join(missing)}")

    ch_dir = repo / "docs" / "changes"
    ac_dir = repo / "docs" / "acceptance"
    if ch_dir.is_dir():
        lint(sorted(ch_dir.glob("CHG-*.md")), CHG_REQUIRED_FIELDS, "CHG")
    if ac_dir.is_dir():
        lint(sorted(ac_dir.glob("ACC-*.md")), ACC_REQUIRED_FIELDS, "ACC")
    return problems


def check_secrets(repo: Path) -> list[str]:
    docs = repo / "docs"
    if not docs.is_dir():
        return []
    problems = []
    for f in sorted(docs.rglob("*.md")):
        text = f.read_text(encoding="utf-8", errors="ignore")
        for name, pat in SECRET_PATTERNS:
            m = pat.search(text)
            if m:
                shown = m.group(0)[:12] + "…"
                problems.append(f"{f.relative_to(repo)} 疑似含 secret({name}:{shown})— 文件不可含 secrets,改以名稱/位置引用")
                break  # 一檔報一次即可
    return problems


def check_regression_pointers(repo: Path) -> list[str]:
    """迴歸集腐爛檢查:regression.md 反引號內的檔案指向必須存在(被刪的測試=靜默作廢的承諾)。"""
    reg = repo / "docs" / "acceptance" / "regression.md"
    if not reg.is_file():
        return []
    problems = []
    for token in re.findall(r"`([^`\n]+)`", reg.read_text(encoding="utf-8", errors="ignore")):
        cand = token.split("::")[0].split()[0].strip()  # 去掉 pytest ::節點與參數
        if cand.startswith(("http://", "https://")):
            continue
        if "/" not in cand and "." not in cand:
            continue  # 純指令名(如 `make`)不驗
        if not (repo / cand).exists():
            problems.append(f"docs/acceptance/regression.md 指向的 `{cand}` 不存在 — 迴歸承諾已腐爛(補檔或更新指向)")
    return problems


KN_TIERS = {"shallow", "deep", "user-confirmed"}
KN_STATUS = {"observing", "active", "retired"}
KN_KNOWN_FIELDS = {"id", "tier", "rule", "tags", "keywords", "status", "branch", "date",
                   "evidence", "counters", "source_quote", "reason", "note", "history"}


def check_knowledge_entries(repo: Path) -> list[str]:
    """JSON 條目 fail-loud 驗證:解析不了/缺必填/enum 錯/id≠檔名/未知欄位(打錯欄名=資料靜默消失)→ 擋。"""
    entries = repo / "docs" / "knowledge" / "entries"
    if not entries.is_dir():
        return []
    problems = []
    vocab = None
    vocab_file = repo / "docs" / "knowledge" / "vocabulary.json"
    if vocab_file.is_file():
        try:
            vocab = json.loads(vocab_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            problems.append(f"docs/knowledge/vocabulary.json 解析失敗(fail-loud):{e}")
    for f in sorted(entries.glob("*.json")):
        rel = f"docs/knowledge/entries/{f.name}"
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            problems.append(f"{rel} JSON 解析失敗(fail-loud,不跳過):{e}")
            continue
        missing = [k for k in ("id", "tier", "rule", "tags", "status") if k not in d]
        if missing:
            problems.append(f"{rel} 缺必填欄:{', '.join(missing)}(schema:assets/knowledge_entry.schema.json)")
            continue
        if d["id"] != f.stem:
            problems.append(f"{rel} id「{d['id']}」≠ 檔名「{f.stem}」— 檔名即 id")
        if d["tier"] not in KN_TIERS:
            problems.append(f"{rel} tier「{d['tier']}」不在 {sorted(KN_TIERS)}")
        if d["status"] not in KN_STATUS:
            problems.append(f"{rel} status「{d['status']}」不在 {sorted(KN_STATUS)}")
        if not isinstance(d["tags"], list) or not d["tags"]:
            problems.append(f"{rel} tags 須為非空陣列(小寫英文檢索鍵)")
        elif isinstance(vocab, dict):
            unregistered = [t for t in d["tags"] if t not in vocab or str(t).startswith("_")]
            if unregistered:
                problems.append(f"{rel} tags {unregistered} 未註冊於 vocabulary.json — 先登記再用(擋 tag 增殖)")
        if "keywords" in d and (not isinstance(d["keywords"], list)
                                or not all(isinstance(x, str) for x in d["keywords"])):
            problems.append(f"{rel} keywords 須為字串陣列(自由語言命中詞)")
        unknown = set(d) - KN_KNOWN_FIELDS
        if unknown:
            problems.append(f"{rel} 未知欄位 {sorted(unknown)} — 打錯欄名=資料靜默消失(schema 為準)")
    return problems


STUB_FILES = ["CLAUDE.md", "GEMINI.md", ".cursorrules", ".windsurfrules",
              ".github/copilot-instructions.md"]


def check_entry_point(repo: Path) -> list[str]:
    """進入點在 root、適用任何 AI:治理專案必有 AGENTS.md;工具專屬檔只准當指向它的 stub。"""
    problems = []
    governed = (repo / "docs" / "changes").is_dir()
    agents = repo / "AGENTS.md"
    if governed and not agents.is_file():
        problems.append("治理專案缺 root 進入點 AGENTS.md — 進入點要在 root、讓任何 AI 最快識別(見 SKILL 入口錨點)")
    if agents.is_file():
        for s in STUB_FILES:
            f = repo / s
            if f.is_file() and "AGENTS.md" not in f.read_text(encoding="utf-8", errors="ignore"):
                problems.append(f"{s} 存在但未指向 AGENTS.md — 工具檔只放兩行 stub,內容不得分岔")
    return problems


RECURRENCE_RE = re.compile(r"(重複性檢查|Recurrence check)\s*[::]", re.IGNORECASE)
SKILL_VER_RE = re.compile(r"Skill\s*[::]\s*ai-sdlc\s*v(\d+)\.(\d+)", re.IGNORECASE)
RECURRENCE_SINCE = (1, 17)


def check_knowledge_bootstrap(repo: Path) -> list[str]:
    """知識庫先建(v1.16)+存量補建(v1.17):受治理 repo 必有 docs/knowledge/——容器不存在,自主記錄永遠不會發生。"""
    if (repo / "docs" / "changes").is_dir() and not (repo / "docs" / "knowledge").is_dir():
        return ["治理專案缺 docs/knowledge/ — 知識庫要先建(空 INDEX 也是合法知識庫):"
                "建 knowledge.md(INDEX)+ vocabulary.json(見 knowledge「先建」;存量專案進場補建見 handshake)"]
    return []


def check_recurrence_field(repo: Path) -> list[str]:
    """收尾「重複性檢查」欄(v1.17 起前瞻強制):散文步驟無欄位對應=實測次次被略過(見 modification-guide 第 7 步)。"""
    ch_dir = repo / "docs" / "changes"
    if not ch_dir.is_dir():
        return []
    problems = []
    for chg in sorted(ch_dir.glob("CHG-*.md")):
        text = chg.read_text(encoding="utf-8", errors="ignore")
        m = SKILL_VER_RE.search(text)
        if not m or (int(m.group(1)), int(m.group(2))) < RECURRENCE_SINCE:
            continue  # 新規則只往後適用(見 doc-integrity):舊版記錄與缺 Skill 欄者豁免
        if not RECURRENCE_RE.search(text):
            problems.append(f"{chg.name} 依 v1.17+ 寫成但缺「重複性檢查/Recurrence check」欄 — "
                            "收尾必比對動機是否重複並記結果,「無重複」也要寫(見 modification-guide 第 7 步)")
    return problems


def check_knowledge_index(repo: Path) -> list[str]:
    """拆檔模式的輕量交叉檢查:條目檔 id ↔ INDEX.md 雙向存在(完整比對交給 knowledge_index.py --check)。"""
    entries = repo / "docs" / "knowledge" / "entries"
    if not entries.is_dir():
        return []
    index = repo / "docs" / "knowledge" / "INDEX.md"
    if not index.is_file():
        return ["docs/knowledge/entries/ 存在但無 INDEX.md — 拆檔模式的 INDEX 是生成物:跑 scripts/knowledge_index.py"]
    idx_text = index.read_text(encoding="utf-8", errors="ignore")
    problems = []
    file_ids = {f.stem for f in entries.glob("*.md")} | {f.stem for f in entries.glob("*.json")}
    for fid in sorted(file_ids):
        if fid not in idx_text:
            problems.append(f"knowledge 條目 {fid} 不在 INDEX.md — INDEX 過期,重跑 knowledge_index.py")
    for iid in re.findall(r"\|\s*((?:KN|DIR)-[\w.]+)\s*\|", idx_text):
        if iid not in file_ids:
            problems.append(f"INDEX.md 列了 {iid} 但 entries/ 無此檔 — INDEX 過期或條目被移走未重生")
    return problems



COVERAGE_ID_RE = re.compile(r"^\|\s*(?:~~)?([ABCD]-\d+)", re.MULTILINE)
COVERAGE_CLOSED_RE = re.compile(r"^#+\s*([^\n]*?)收尾", re.MULTILINE)


def check_coverage_registry(repo: Path) -> list[str]:
    """未涵蓋登記簿不得自相矛盾(CHG-20260804-06;CHG-20260804-09 修誤報)。

    這份檔案的用途是讓「測試全綠」不被讀成「全部都驗過了」。
    那它自己就不能說謊——而它踩過兩種說謊:

      · **重複的 ID**:同一個編號指兩件事,讀的人不知道哪個才算
      · **宣告收尾卻還列著**:某節標題寫「C-23 收尾」,別處卻仍有一列 C-23 未涵蓋

    第二種特別隱蔽:兩邊都是真話,但合起來是假的。

    **收尾小節裡的表不算未涵蓋項**——那是「已收了什麼」的摘要,不是待辦。
    第一版沒有分開這兩者,結果第一次有人在收尾小節裡放摘要表就誤報了
    (而那個人是這道檢查的作者)。寬鬆的比對把摘要讀成待辦,是 KN-003 的形狀。
    """
    problems = []
    for path in sorted(repo.glob("docs/*/acceptance/verification-coverage.md")):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(repo).as_posix()

        # 依 `##` 標題切節:標題含「收尾」的那一節,其表格是已收摘要,不是待辦
        open_ids, closed = [], set()
        heading, in_closed = "", False
        for line in text.splitlines():
            if line.startswith("#"):
                heading = line
                in_closed = "收尾" in heading
                if in_closed:
                    closed |= set(re.findall(r"[ABCD]-\d+", heading))
                continue
            m = re.match(r"\|\s*(?:~~)?([ABCD]-\d+)", line)
            if m and not in_closed:
                open_ids.append(m.group(1))

        dup = sorted({i for i in open_ids if open_ids.count(i) > 1})
        if dup:
            problems.append(f"{rel}:登記簿有重複的 ID {', '.join(dup)}"
                            f"——同一個編號指兩件事,讀的人不知道哪個才算")
        still = sorted(closed & set(open_ids))
        if still:
            problems.append(f"{rel}:{', '.join(still)} 已於某節標題宣告收尾,"
                            f"卻仍以未涵蓋項列著——兩邊都是真話,合起來是假的")
    return problems


def check_commits(repo: Path, since: str) -> list[str]:
    if not (repo / ".git").exists():
        return [f"--commits-since 需要 git repo(未偵測到 .git)— 無 git 模式下 commit 錨定不適用(見 handshake 降級模式)"]
    try:
        out = git(repo, "log", "--pretty=%h\t%s", f"{since}..HEAD")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        hint = ";偵測到 shallow clone,請 `git fetch --unshallow` 或在完整 clone 執行" \
            if (repo / ".git" / "shallow").exists() else ""
        return [f"無法讀取 {since}..HEAD 的 commits(錨點存在嗎?{hint}):{e}"]
    problems = []
    for line in out.splitlines():
        if not line.strip():
            continue
        h, _, subject = line.partition("\t")
        try:
            body = git(repo, "log", "-1", "--pretty=%B", h)
        except (subprocess.CalledProcessError, FileNotFoundError):
            body = subject
        if not CHG_RE.search(body):
            problems.append(f"commit {h}「{subject[:60]}」未引用任何 CHG/XCHG 編號 — 未治理工作(見 commit 粒度)")
    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--staged", action="store_true", help="檢查 git staged 變更的結構漂移")
    ap.add_argument("--structural", nargs="*", default=DEFAULT_STRUCTURAL)
    ap.add_argument("--commits-since", metavar="REF", help="掃描 REF..HEAD 的 commit 是否都引用 CHG 編號")
    ap.add_argument("--require-branch", action="store_true", help="欄位 lint 額外強制 Branch 欄(多分支專案)")
    ap.add_argument("--require-commit", action="store_true", help="欄位 lint 額外強制 Commit/PR 欄")
    ap.add_argument("--no-field-lint", action="store_true")
    ap.add_argument("--no-secret-scan", action="store_true")
    args = ap.parse_args(argv[1:])
    repo = Path(args.repo).resolve()

    problems: list[str] = []
    if args.staged:
        changed = git_staged_files(repo)
        problems += check_structural_sync(changed, args.structural)
    problems += check_chg_acc(repo)
    if not args.no_field_lint:
        problems += check_fields(repo, args.require_branch, args.require_commit)
    if not args.no_secret_scan:
        problems += check_secrets(repo)
    problems += check_regression_pointers(repo)
    problems += check_entry_point(repo)
    problems += check_knowledge_bootstrap(repo)
    problems += check_recurrence_field(repo)
    problems += check_knowledge_entries(repo)
    problems += check_knowledge_index(repo)
    problems += check_coverage_registry(repo)
    if args.commits_since:
        problems += check_commits(repo, args.commits_since)

    if problems:
        print("❌ doc-integrity 檢查未通過:")
        for p in problems:
            print(f"  - {p}")
        print("\n請補齊(改結構→更新 docs/structure;已實作 CHG→補 ACC;缺欄→補模板欄;"
              "secret→改名稱/位置引用;未治理 commit→補開 CHG)後再提交。")
        return 1
    print("✅ doc-integrity 檢查通過(結構同步 + CHG↔ACC + 欄位 + secrets"
          + (" + commit 治理" if args.commits_since else "") + ")。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
