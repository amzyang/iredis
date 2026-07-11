# 列出所有可用命令
default:
    @just --list

# 同步依赖（含 dev 组）
sync:
    uv sync

# 格式化代码并应用可自动修复的 lint 问题
fmt:
    uv run ruff format .
    uv run ruff check . --fix

# 静态检查：ruff lint、格式检查、ty 类型检查
lint:
    uv run ruff check .
    uv run ruff format --check .
    uv run ty check

# 运行单元测试（会 flush 本地 redis db15！）
test-unit version="8":
    REDIS_VERSION={{version}} uv run pytest tests/unittests

# 运行全部测试，含 pexpect CLI 测试（会 flush 本地 redis db15！）
test version="8":
    REDIS_VERSION={{version}} uv run pytest

# 从源码运行 iredis
run *args:
    uv run iredis {{args}}

# 构建 sdist 与 wheel
build:
    uv build

# 升级全部依赖至最新并同步
upgrade:
    uv lock --upgrade
    uv sync

# 安装 pre-commit 钩子
pre-commit:
    uv run pre-commit install

# 发布新版本：bump 版本、commit、打 tag 并推送（触发 Homebrew 发布）；不带版本号时 minor 递增
release version="":
    bash scripts/release.sh {{version}}
