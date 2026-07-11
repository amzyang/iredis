# iredis

## 发布流程注意事项

- 发布统一走 `.github/workflows/release.yaml`(Actions 页面 Run workflow,输入版本号):
  自动 `uv version` 升级 `pyproject.toml`/`uv.lock`、commit、打 tag、推送,
  并显式触发 Homebrew workflow(GITHUB_TOKEN 推的 tag 不会触发 `on.push`)。
- 如手动打 release tag(`vX.Y.Z`),必须先把 `pyproject.toml` 的 `version` 升级为
  `X.Y.Z`,并运行 `uv lock` 同步 `uv.lock`,提交后再在该提交(或其后)打 tag。
- `.github/workflows/homebrew.yaml` 会下载 tag 对应的 tarball,校验其中
  `pyproject.toml` 版本与 tag 一致,不一致则直接失败(v2.2.0、v2.2.1 首次发布
  均因漏掉 bump 而失败过)。
- 仓库只用 tag、不建 GitHub Release;workflow 失败导致 formula 未发布时,
  可以安全地删除并重打同名 tag,或用 `workflow_dispatch` 手动重跑。
