# 本地部署变更记录

## 2026-11-23 建立 Dify 1.20.0 基线

分支 `v1.20.0` 基于官方 tag `1.20.0`，基线提交为 `7bef4e1b2d`。建档时，相对该 tag 仅新增以下四份文档。

| 文件 | 用途 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Docker 目录的配置、生成和验证约定 |
| `LOCAL_CHANGES.md` | 部署基线、分支改动及验证结果 |
| [LOCAL_DEPLOYMENT.md](LOCAL_DEPLOYMENT.md) | 从仓库根目录配置并启动本地实例 |
| [MODEL_RECOMMENDATIONS.md](MODEL_RECOMMENDATIONS.md) | 三种 Qwen 模型的供应商推荐配置、两套应用生成参数和本版本的实测记录 |

在仓库根目录运行 `git diff --name-status refs/tags/1.20.0 HEAD`，可复核分支相对基线的文件差异。

### 基线验证

在 `docker/` 目录使用 Docker Compose v5.5.0 验证。默认部署配置通过 `docker compose config -q`，`python3 tests/test_compose_environment.py` 的 28 项测试全部通过。在临时目录按指南生成 `.env`，核实了默认 HTTP 端口 `80`、示例端口 `8080` 和公共 URL 覆盖配置。

建档时已对照项目参数记录、供应商插件字段和 Qwen 模型卡核对推荐值。OrbStack 实例的运行结果记录如下。

## 2026-11-23 OrbStack 升级与验收

沿用本机的 Compose 配置和挂载，将 API、Web、Worker、Agent 后端和 Agent 本地沙箱升级到 `1.20.0`，插件守护进程升级到 `0.6.15-local`。15 个常驻容器运行正常，`init_permissions` 以状态码 0 退出，Celery Worker 响应 `pong`，控制台初始化接口返回 `finished`。登录页返回 HTTP 200，管理员登录尚待单独验证。

| 项目 | 实机验证结果 |
| --- | --- |
| 备份与恢复 | 停写后导出 `dify` 和 `dify_plugin`，在独立的 PostgreSQL 15 中分别还原并核对数据。冷备覆盖全部本地持久化目录，另保存了部署配置。两个 Agent 命名卷的归档已与原卷比对。Home 包含 4 个普通文件，tar 跳过了运行时 Unix 套接字 `tmux.sock`，Workspace 当时为空。整套备份通过 SHA-256 校验。 |
| 数据库与向量索引 | 主库自动从 `53c10126d551` 迁移到 `f8b6e2c4a901`。核实新增的 9 张表、评估框架列和 IM 同步记录约束。发起验收问答前，应用、会话、消息、知识库、文档和插件数量与备份一致。205 个知识分段的索引 ID 与 Weaviate 对象 ID 逐条匹配。 |
| 已发布 Chatflow | 通过 WebApp 发起一次真实流式问答，7 个节点全部成功。应用关闭了前台引用，检索节点的执行记录显示共返回 5 个分段，预期原文排第 1。回答的两项金额和餐点说明均与原文一致。本次验收新增 1 个会话和 1 条消息。[模型实测记录](MODEL_RECOMMENDATIONS.md#1200-实测记录) |

验收后已删除本次升级前的本地备份（含两个 Agent 命名卷的归档）和 5 个无容器引用的旧 Dify 镜像。OrbStack 镜像层占用减少约 6.34 GB。清理后 15 个常驻服务持续运行，Web 和控制台 API 均返回 HTTP 200。

本次更新了本文件与 [MODEL_RECOMMENDATIONS.md](MODEL_RECOMMENDATIONS.md) 的实测记录。

## 2026-11-23 复核 1.20.0 配置说明

在隔离目录用 Compose 验证了根 `.env` 中显式空值和非空值的覆盖顺序，补充本实例切换域名时应修改的公开地址。对照本版本的控制台和已安装的供应商插件 `0.0.84`，核对了三种模型共 20 个供应商配置字段及表中选项，并验证了插件用单行或带换行的查询前缀构造请求时的文本。[部署指南](LOCAL_DEPLOYMENT.md) · [模型配置](MODEL_RECOMMENDATIONS.md)
