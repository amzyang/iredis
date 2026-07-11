# iredis

## 发布流程注意事项

- 发布统一走本地命令 `just release [X.Y.Z]`(即 `bash scripts/release.sh`,
  不带版本号时默认 patch 递增):自动 `uv version` 升级 `pyproject.toml`/
  `uv.lock`、commit、打 tag、一次推送 main 与 tag;本地凭证推的 tag 会正常
  触发 Homebrew workflow。
- 如手动打 release tag(`vX.Y.Z`),必须先把 `pyproject.toml` 的 `version` 升级为
  `X.Y.Z`,并运行 `uv lock` 同步 `uv.lock`,提交后再在该提交(或其后)打 tag。
- `.github/workflows/homebrew.yaml` 会下载 tag 对应的 tarball,校验其中
  `pyproject.toml` 版本与 tag 一致,不一致则直接失败(v2.2.0、v2.2.1 首次发布
  均因漏掉 bump 而失败过)。
- 仓库只用 tag、不建 GitHub Release;workflow 失败导致 formula 未发布时,
  可以安全地删除并重打同名 tag,或用 `workflow_dispatch` 手动重跑。

## CI 注意事项

- push 到 main 时,若 head commit message 前缀为 `docs:`/`ci:`/`chore:`(含带
  scope 的 `docs(…)` 等),Test workflow 的两个 job 会整体跳过;PR 始终会跑。
- GitHub 只按一次 push 的最后一个 commit 判断:混合推送时把代码 commit 放最后,
  或分开推,避免代码改动被跳过测试。
