# Docker 协作约定

本文件适用于 `docker/`。开始前核对当前分支、工作区和部署基线，保留用户已有的修改。[仓库协作约定](../AGENTS.md) · [本地变更记录](LOCAL_CHANGES.md)

## 配置与生成

- 根 `.env` 保存 Compose 编排参数和显式覆盖，`.env.example` 仅列出需要手工配置的项。
- 服务默认值位于 `envs/**/*.defaults`。服务专属配置写入对应的 `.env`，Web、API 和 worker 共用的公共地址可写入 `envs/core-services/urls.env`。根 `.env` 中的显式设置优先。[配置加载说明](README.md#configure-dify)
- Git 会忽略本地 `.env` 和 `envs/**/*.env`。编辑已有配置时保留凭据和文件权限，核对渲染结果时只输出所需的非敏感字段。
- Compose 使用预构建镜像。排查运行时问题时，核对实例实际使用的镜像版本。

修改服务编排时先编辑 `docker-compose-template.yaml`，然后在 `docker/` 目录生成配套的 `docker-compose.yaml`，一并检查两份文件的差异。

```sh
python3 generate_docker_compose --compose-only
```

## 验证与记录

在 `docker/` 目录按变更范围执行检查。

```sh
docker compose config -q
python3 tests/test_compose_environment.py
git diff --check
```

文档变更核对链接和命令示例。配置变更检查 Compose 的实际渲染值。涉及持久化数据目录的改动，在临时目录中验证初始化和失败时的行为。

部署操作按用户当次授权执行，保留实例的数据卷、凭据和模型配置。完成变更后，将日期、基线、涉及文件和验证结果写入变更记录。容器运行状态和模型调用结果以对应实例的实测为准。[本地变更记录](LOCAL_CHANGES.md) · [本地部署指南](LOCAL_DEPLOYMENT.md) · [模型配置与验证记录](MODEL_RECOMMENDATIONS.md)
