# 本地部署修改记录

基线：`v1.19.0`（`8e689e868b`），更新日期：2026-11-17。

## 修改文件

以下路径均相对于 `docker/`：

| 文件 | 修改内容 | Git 管理 |
| --- | --- | --- |
| [docker-compose-template.yaml](docker-compose-template.yaml) | `init_permissions` 增加插件存储目录初始化；`plugin_daemon` 增加 `init_permissions` 依赖 | 跟踪 |
| [docker-compose.yaml](docker-compose.yaml) | 由 `python3 generate_docker_compose --compose-only` 重新生成 | 跟踪 |
| [MODEL_RECOMMENDATIONS.md](MODEL_RECOMMENDATIONS.md) | 新增模型参数配置与验证记录 | 跟踪 |
| [.env](.env) | 配置项目名、profiles、端口、访问地址及同源 `CONSOLE_API_URL` | 忽略 |
| [envs/core-services/web.env](envs/core-services/web.env) | 新增 `HOSTNAME=0.0.0.0` | 忽略 |

## 具体配置修改

### 1. `docker-compose-template.yaml` / `docker-compose.yaml`

回移上游提交 [18ff0c9ef1](https://github.com/langgenius/dify/commit/18ff0c9ef17fdcbceec181d1f59a4d2a74cf57d9)：

- `init_permissions`：
  - 挂载新增 `./volumes/plugin_daemon:/app/plugin_daemon/storage`
  - 遍历 `/app/api/storage` 与 `/app/plugin_daemon/storage`，分别使用 `.init_permissions` 标记并执行 `chown -R 1001:1001`，失败时 `exit 1`
- `plugin_daemon`：
  - `depends_on` 新增 `init_permissions`（`condition: service_completed_successfully`）

### 2. `.env`

除保留原有 `DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN`（文件权限 `600`）外，配置如下：

```dotenv
COMPOSE_PROJECT_NAME=dify
COMPOSE_PROFILES=weaviate,postgresql,collaboration

EXPOSE_NGINX_PORT=18080
EXPOSE_NGINX_SSL_PORT=18443

CONSOLE_API_URL=
CONSOLE_WEB_URL=http://localhost:18080
SERVICE_API_URL=http://localhost:18080
APP_WEB_URL=http://localhost:18080
FILES_URL=http://localhost:18080
INTERNAL_FILES_URL=http://api:5001
TRIGGER_URL=http://localhost:18080
NEXT_PUBLIC_SOCKET_URL=/
```

- `CONSOLE_API_URL=` 有意留空，覆盖镜像内默认的 `http://127.0.0.1:5001`。
- 未设置 `HOSTNAME`（避免覆盖 `web.env` 且影响其他服务）。

### 3. `envs/core-services/web.env`

```dotenv
HOSTNAME=0.0.0.0
```
