#!/usr/bin/env bash
# 把 git hooks 指向版控目錄 .githooks/。clone 之後跑一次。
#
# core.hooksPath 是本機設定、不隨 clone 過來,所以這一步沒辦法自動化——
# 這是撤掉 CI 之後留下的**已知缺口**,寫在這裡而不是假裝沒有:
# 沒跑這支的機器,push 時不會有任何閘。真正擋在 merge 前的是
# autopilot runner 的 local-gate(它自己會找 .github/ci_local.sh)。
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true
echo "✅ core.hooksPath → .githooks(pre-push 會跑 .github/ci_local.sh)"
