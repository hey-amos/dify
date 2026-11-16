# Docker 协作约定

本文件适用于 `docker/`，与仓库根目录的 [AGENTS.md](../AGENTS.md) 配合使用。当前用户的明确要求优先；本文件不扩大任务授权。

## 开始前

- 先读 [LOCAL_CHANGES.md](LOCAL_CHANGES.md)，了解本地修复、配置位置、上游依据和已有验证结果；配置加载与覆盖规则以 [README.md](README.md#configure-dify) 和实际 Compose 定义为准。
- 核对当前分支、`git status` 和相关差异，保留用户已有修改。修改记录是历史快照，不代表当前分支、配置或服务状态；仅按任务需要核实实际状态。
- `.env` 和服务专属的 `envs/**/*.env` 被 Git 忽略。Git 工作区没有变化不代表这些文件不存在，也不代表其中没有用户配置。
- 新服务器的 IP + HTTP 部署入口为 [SERVER_DEPLOYMENT.md](SERVER_DEPLOYMENT.md) 和 [deploy.py](deploy.py)。`init` / `deploy` 只用于全新部署；编写或验证脚本不等于获准在现有部署上执行它。

## 配置与生成规则

- `docker-compose-template.yaml` 是源模板，`docker-compose.yaml` 是生成文件。修改模板后，在 `docker/` 目录执行：

  ```bash
  python3 generate_docker_compose --compose-only
  ```

  保持两者同步，不只修改生成文件。此命令不会启动容器，也不会创建或覆盖根 `.env`。
- 根 `.env` 放 Compose 编排参数及跨服务共享配置；服务专属覆盖放在对应的 `envs/**/*.env`。当前 `HOSTNAME=0.0.0.0` 由 `envs/core-services/web.env` 提供，根 `.env` 不重复配置它。
- `envs/**/*.defaults` 是受 Git 管理的默认值。本机覆盖优先使用对应 `.env`；确需修改仓库默认行为时，再按任务范围调整 `.defaults`。
- 保留已有 token、凭据和文件权限，除非当前任务明确要求变更。不要输出完整的实际环境配置，不把真实密钥写入文档、日志或提交。
- Compose 引用预构建镜像。切换 Git 分支或修改 Dockerfile 不会自动更新镜像内的代码；涉及镜像修复时，区分源码变化与实际部署镜像。

## 验证与执行边界

当前部署阶段（2026-11-14）：用户已启动容器并完成管理员账户及三个模型的初始配置，已授权排查插件图标、实际测试和调整模型配置。可在该范围内调用现有服务，并按需重建受配置修改影响的服务；保留现有数据卷、凭据和模型，不自动升级镜像或重建整套部署。后续操作仍以用户当次授权为准。

在 `docker/` 目录可执行以下检查，它们不会启动容器：

```bash
docker compose config -q
python3 tests/test_compose_environment.py
git diff --check
```

- 按改动范围选择检查；纯文档修改只需核对内容、路径和格式。
- 修改服务器部署脚本时运行 `python3 tests/test_server_deploy.py`；测试在临时目录解析真实 Compose，并模拟 Docker 启动命令，不启动容器。
- `config -q` 仅验证配置可解析。需要核实变量是否生效时，解析 `config --format json` 的结果，只输出必要的非敏感字段，不直接展示完整配置。
- 修改权限初始化逻辑时，至少检查“API 已初始化但插件目录尚未初始化”和“权限设置失败”两种情况。可以使用临时目录模拟失败，不操作真实持久化数据目录。
- 区分配置解析、脚本验证与真实运行验证；没有实际启动服务时，不声称插件安装、Web 请求或整套服务健康状态已验证。

## 修改记录

完成部署调整后更新 [LOCAL_CHANGES.md](LOCAL_CHANGES.md)，记录日期、适用基线、最终文件位置、修改原因、已完成验证和仍未验证的部分。

本文件保留协作规则和入口；具体改动历史集中在修改记录中，避免两处重复维护。
