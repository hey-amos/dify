# 本地分支变更记录

本文件记录当前分支相对于上游官方基线的改动清单，以及版本升级与验证结果。

> 仅记录**分支级改动**和**升级验证结论**；单机未入库的临时 `.env` 参数调整不写进本文件，以各部署环境实际的 `docker/.env` 为准。

## 基线信息

- **分支**：`v1.20.0`
- **上游基线**：官方 tag `1.20.0`（`7bef4e1b2d`）
- **差异核对命令**（仓库根目录执行）：
  ```sh
  git diff --name-status refs/tags/1.20.0..HEAD
  ```

## 相对上游 `1.20.0` 的文件清单

当前分支未修改任何上游应用代码、Compose 编排文件或 `envs/**/*.defaults`，仅在 `docker/` 目录新增以下四份文档：

| 文件 | 状态 | 说明 |
| --- | --- | --- |
| [AGENTS.md](AGENTS.md) | 新增 | `docker/` 目录的 Agent 协作约定、基线说明与文档索引 |
| [LOCAL_CHANGES.md](LOCAL_CHANGES.md) | 新增 | 本文件：相对上游基线的变更清单与升级验证日志 |
| [LOCAL_DEPLOYMENT.md](LOCAL_DEPLOYMENT.md) | 新增 | 容器部署步骤、启停操作与 `docker/.env` 编写指南 |
| [MODEL_RECOMMENDATIONS.md](MODEL_RECOMMENDATIONS.md) | 新增 | 模型供应商推荐配置、应用生成参数与本版本实测记录 |

## 升级与维护日志

### 2026-11-23：升级至 Dify 1.20.0

- **镜像版本**：API、Web、Worker、Agent 后端与本地沙箱升级至 `1.20.0`，Plugin Daemon 升级至 `0.6.15-local`。
- **升级前备份**：备份了数据库与持久化卷目录，并在独立的 PostgreSQL 实例中完成还原校验。
- **升级后验证**：
  - 全部 15 个容器正常运行，`api` 健康检查通过，`init_permissions` 正常退出（`Exited (0)`）。
  - 主库迁移至版本 `f8b6e2c4a901`。
  - 升级前后应用、知识库和文档数量一致。
  - 通过已发布的 Chatflow 完成一次真实问答，知识库检索与模型回复结果正常（模型实测详情见 [MODEL_RECOMMENDATIONS.md](MODEL_RECOMMENDATIONS.md)）。
