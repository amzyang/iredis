#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "用法: $0 X.Y.Z" >&2
    exit 1
fi

version="${1#v}" # 接受 2.2.2 或 v2.2.2

[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
    echo "版本号格式应为 X.Y.Z,收到: $1" >&2
    exit 1
}
[[ "$(git branch --show-current)" == "main" ]] || {
    echo "请在 main 分支发布" >&2
    exit 1
}
[[ -z "$(git status --porcelain)" ]] || {
    echo "工作区有未提交改动" >&2
    exit 1
}
if git ls-remote --exit-code --tags origin "v${version}" >/dev/null; then
    echo "tag v${version} 已存在" >&2
    exit 1
fi
# 本地 main 落后于远端时提前退出,避免 push 被拒后留下本地 commit+tag
git fetch origin main
git merge-base --is-ancestor origin/main main || {
    echo "本地 main 落后于 origin/main,先 pull" >&2
    exit 1
}

uv version "$version" # 同步更新 pyproject.toml 与 uv.lock
git commit -am "chore: 版本号升级至 ${version}"
git tag "v${version}"
# 一次推送 main 与 tag;本地凭证推的 tag 会触发 Homebrew workflow
git push origin main "refs/tags/v${version}"
