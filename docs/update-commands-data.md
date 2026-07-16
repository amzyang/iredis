# 更新 Redis 命令数据

iredis 的命令补全 / hint / HELP 文档由四个数据文件驱动，全部 vendor 在仓库内，
运行时不依赖任何 git submodule：

| 文件 | 作用 | 消费方 |
|------|------|--------|
| `iredis/data/commands.json` | 命令元数据（summary/since/arguments） | 补全 hint、底部工具栏、`HELP` |
| `iredis/data/command_syntax.csv` | 命令 → 语法规则名 → 渲染回调 | grammar、渲染 |
| `iredis/redis_grammar.py` | 语法规则（正则）与 CONST 补全词表 | 补全、高亮 |
| `iredis/data/commands/<name>.md` | `HELP <command>` 的文档正文 | markdown 渲染 |

一致性由 `tests/unittests/test_data_consistency.py` 守护。

## 数据来源

`commands.json` 的上游是 [redis/docs](https://github.com/redis/docs) 仓库的
`data/commands_core.json`，两者结构逐字段一致。注意上游 main 分支包含
**未发布版本**的命令（如 8.8.x），因此只做白名单增量合并，不做全量覆盖。

历史上的 antirez/redis-doc submodule 与 `scripts/download_redis_commands.py`
已废弃删除（上游仓库已死、redis.io 页面已改版）。

## 新增一个命令的步骤

1. **查看上游差异**（只读）：

   ```bash
   python scripts/update_commands_json.py --diff
   ```

2. **白名单合并元数据**：

   ```bash
   python scripts/update_commands_json.py --merge HEXPIRE,HTTL
   ```

   可用 `--ref <sha>` 固定上游版本。合并后 `git diff` 应只有纯新增块。

3. **手写帮助文档** `iredis/data/commands/<name>.md`（命令名小写、空格换
   `-`）。仿 `getex.md` 的纯 markdown 风格：描述 + `## Options` +
   `@return`（`@array-reply:` 等标记）+ `@examples`，文末附
   `https://redis.io/commands/<name>` 链接。**禁止** Hugo front
   matter、`{{< relref >}}` shortcode、`<details>` 等 HTML——prompt_toolkit
   渲染不了。

4. **语法规则**：在 `iredis/redis_grammar.py` 的 `GRAMMAR` 里复用或新建
   规则；新关键字加进 `CONST` 字典（自动获得补全与高亮），并在 const
   choices 区域加对应 token。在 `command_syntax.csv` 对应组内按字母序
   插入一行（渲染回调必须是 `OutputRender` 的已有方法名）。

5. **测试**：`tests/unittests/command_parse/` 加 `judge_command` 断言
   （完整形态 / 可选项 / 缺参 None / 互斥项 None）；需要真实 redis 的
   端到端行为放 `tests/cli_tests/`，用
   `version_parse(os.environ['REDIS_VERSION'])` 做版本 gate。

6. **验证**：

   ```bash
   just test-unit        # 含 test_data_consistency / markdown 渲染 / 语法遍历
   just run              # 手动确认补全、底部工具栏、HELP
   ```
