# Docker 目录 Agent 协作指南

本文件适用于 `docker/` 目录，配合仓库根目录的 [AGENTS.md](../AGENTS.md) 使用。开始任何修改前，先确认当前分支和工作区状态，保留用户已有的本地改动。

## 当前分支与基线

- **当前分支**：`v1.20.0`
- **上游基线**：官方 tag `1.20.0`（commit `7bef4e1b2d`）
- **相对上游的改动范围**：仅在 `docker/` 下新增了本仓库维护的文档，未改动上游代码、默认环境变量模板和 Compose 编排文件。可用 `git diff --name-status refs/tags/1.20.0..HEAD` 核对。

## 新增文档索引

| 文件 | 用途 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 本文件：向 Agent 说明当前分支基线、新增文档用途以及 `docker/` 目录的修改与验证规范 |
| [LOCAL_CHANGES.md](LOCAL_CHANGES.md) | 记录当前分支相对于上游基线 `1.20.0` 的改动清单与版本升级验证日志 |
| [LOCAL_DEPLOYMENT.md](LOCAL_DEPLOYMENT.md) | 记录本地及服务器部署步骤、容器启停方法与 `docker/.env` 编写规范 |
| [MODEL_RECOMMENDATIONS.md](MODEL_RECOMMENDATIONS.md) | 记录本项目使用的模型供应商推荐参数、应用生成参数及实测结果 |

上游官方文档见 [README.md](README.md)（包含完整的环境变量加载优先级、HTTPS、可信代理、Middleware 等说明）。

## 配置与编排规范

- **保护本地 `.env`**：`docker/.env` 与 `docker/envs/**/*.env` 均被 Git 忽略。切勿用模板覆盖已有 `.env`，但应与 `.env.example` 及 [LOCAL_DEPLOYMENT.md](LOCAL_DEPLOYMENT.md) 中的模板对比，按需补齐缺少的变量；编辑时保留原有凭据和 `600` 文件权限，排查或输出配置时不要打印敏感密钥。
- **配置分层**：
  - `.env.example` 仅保留必须手工填写的最小项。
  - `docker/.env` 存放当前部署的 Compose 参数与显式覆盖，优先级高于 `envs/**/*.env` 与 `envs/**/*.defaults`（详见 [README.md#configure-dify](README.md#configure-dify)）。
  - 服务专属的可选覆盖写入 `envs/` 下对应的 `.env` 文件；`docker/.env` 中复用相同公开地址时，优先使用 `${CONSOLE_WEB_URL}` 引用，避免多处硬编码。
- **修改 Compose 编排**：不要直接手工改 `docker-compose.yaml`。先编辑 `docker-compose-template.yaml`，再在 `docker/` 目录运行以下命令同步生成：
  ```sh
  python3 generate_docker_compose --compose-only
  ```

## 验证与变更记录

修改配置或编排后，在 `docker/` 目录按需运行检查：

```sh
docker compose config -q
python3 tests/test_compose_environment.py
git diff --check
```

- 改动 `.env` 或编排后，可用 `docker compose config` 核对关键非敏感字段的展开结果。
- 涉及启停容器、重建服务或数据库迁移的操作，仅在用户明确授权时执行，且必须保留现有数据卷、凭据和模型配置。
- 若对当前分支做了新的基线外改动或完成版本升级验证，同步更新 [LOCAL_CHANGES.md](LOCAL_CHANGES.md)。
