# iredis

## 发布流程注意事项

- 打 release tag(`vX.Y.Z`)前,必须先把 `pyproject.toml` 的 `version` 升级为 `X.Y.Z`,
  并运行 `uv lock` 同步 `uv.lock`,提交后再在该提交(或其后)打 tag。
- `.github/workflows/homebrew.yaml` 会下载 tag 对应的 tarball,校验其中
  `pyproject.toml` 版本与 tag 一致,不一致则直接失败(v2.2.0、v2.2.1 首次发布
  均因漏掉 bump 而失败过)。
- 仓库只用 tag、不建 GitHub Release;workflow 失败导致 formula 未发布时,
  可以安全地删除并重打同名 tag,或用 `workflow_dispatch` 手动重跑。
