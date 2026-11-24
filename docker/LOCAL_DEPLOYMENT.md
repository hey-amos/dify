# Dify 1.20.0 容器部署指南

适用于 macOS 和 Linux。以下所有命令默认在仓库的 `docker/` 目录下执行。

## 前置要求

- Docker（守护进程已启动）
- Docker Compose **v2.35.0 及以上**（通过 `docker compose version` 确认；低于该版本时根 `.env` 覆盖优先级可能不符合预期）
- OpenSSL（用于生成随机令牌）

## 1. 编写 `docker/.env`

> 如果已有 `docker/.env`，请直接原地编辑，**不要**用模板覆盖；但应与下方模板及 `.env.example` 对比，按需补齐缺少的变量。

新部署时在 `docker/` 目录创建 `.env`，并设置仅当前用户可读写（`chmod 600 .env`）：

```dotenv
# Compose 编排：启用的内置组件与项目名称
# 如需开启工作流多人协作，在末尾追加 ,collaboration（启动 api_websocket）并将下方 ENABLE_COLLABORATION_MODE 改为 true
COMPOSE_PROFILES=weaviate,postgresql
COMPOSE_PROJECT_NAME=dify


# 关闭工作流多人协作（反向代理未正确转发 WebSocket 时，开启会导致应用同步数据持续重试）
ENABLE_COLLABORATION_MODE=false


# Agent 后端与本地沙箱共享令牌，使用 `openssl rand -hex 32` 生成
DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN=


# 对外暴露端口（80/443 被宿主机占用时可改为其他端口，如 18080/18443）
EXPOSE_NGINX_PORT=80
EXPOSE_NGINX_SSL_PORT=443


# 公开访问地址：浏览器通过 CONSOLE_WEB_URL 访问，其余地址统一复用该变量
CONSOLE_WEB_URL=http://localhost
# 留空走当前页面同源（HTTP/HTTPS 均可登录，支持多地址访问）；线上单一 HTTPS 域名建议改为 ${CONSOLE_WEB_URL}
CONSOLE_API_URL=
SERVICE_API_URL=${CONSOLE_WEB_URL}
APP_WEB_URL=${CONSOLE_WEB_URL}
FILES_URL=${CONSOLE_WEB_URL}
TRIGGER_URL=${CONSOLE_WEB_URL}
ENDPOINT_URL_TEMPLATE=${CONSOLE_WEB_URL}/e/{hook_id}

# 同源 WebSocket 路径（用于工作流多人协作）
NEXT_PUBLIC_SOCKET_URL=/


# 容器间内部文件访问地址（勿写成外部域名）
INTERNAL_FILES_URL=http://api:5001
```

### 关键配置说明

官方 `.env.example` 只包含 `COMPOSE_PROFILES` 和 `DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN`，其余常用覆盖项的作用如下：

| 变量 | 说明 |
| --- | --- |
| `COMPOSE_PROJECT_NAME` | 固定项目名为 `dify`，避免默认取目录名 `docker` 与其他项目冲突。 |
| `ENABLE_COLLABORATION_MODE` | 工作流多人协作总开关（后端默认 `true`）。设为 `false` 可关闭协作模式，避免反向代理未配好 WebSocket 时页面反复重试数据同步；同时从 `COMPOSE_PROFILES` 中去掉 `collaboration`，不再启动独立的 `api_websocket` 容器。 |
| `EXPOSE_NGINX_PORT` / `EXPOSE_NGINX_SSL_PORT` | 宿主机映射端口。若宿主机 nginx 已占用 80/443，可改为非默认端口（如 `18080`/`18443`）。 |
| `CONSOLE_WEB_URL` | 浏览器访问入口。本地/内网直连时写 `http://<IP或localhost>:${EXPOSE_NGINX_PORT}`（80/443 端口可省略）；上线套外层反向代理时写外部访问地址（如 `https://dify.example.com`），`EXPOSE_NGINX_PORT` 保持给反代转发的宿主机端口不变。其余公开 URL 均引用它，换环境只需改这一处。 |
| `CONSOLE_API_URL` | 留空时前端走当前页面同源路径，HTTP/HTTPS 均可正常登录且支持多地址同时访问（如本机 `localhost` 与 OrbStack 魔法域名）。线上使用单一固定 HTTPS 域名（或需要插件 OAuth 回调）时，建议设为 `${CONSOLE_WEB_URL}`，让登录 Cookie 带 `Secure` 标志并生成完整回调地址（设置后浏览器需通过 `CONSOLE_WEB_URL` 访问）。 |
| `ENDPOINT_URL_TEMPLATE` | **插件端点（Endpoint Plugin）**对外访问 URL 模板，必须保留 `{hook_id}` 占位符。Dify 会在展示/生成插件自定义 HTTP 入口（如 Webhook、扩展接口）时把 `{hook_id}` 替换为实际端点 ID。 |
| `NEXT_PUBLIC_SOCKET_URL` | 开启多人协作时的 WebSocket 地址。官方默认 `ws://localhost` 仅适用于 80 端口本机访问，改为 `/` 可自动跟随当前站点和端口。 |
| `INTERNAL_FILES_URL` | 容器内部（如插件、沙箱）拉取 API 文件的地址，固定为 `http://api:5001`。 |

更多服务级可选项位于 `envs/` 目录（如 `envs/core-services/`、`envs/databases/`、`envs/vectorstores/`），其中 `docker/.env` 优先级最高，详见 [README.md#configure-dify](README.md#configure-dify)。

## 2. 对外提供服务前的额外检查

如果部署在服务器上并开放给他人访问，首次启动前还应完成：

1. **替换默认凭据**：官方默认的数据库、Redis、插件和沙箱密钥为公开值，请参考 [envs/security.env.example](envs/security.env.example) 与 [README.md#start-dify](README.md#start-dify) 修改。注意：PostgreSQL 初始化后再修改 `DB_PASSWORD` 会导致连接失败。
2. **配置 HTTPS 与可信代理**：可使用内置 [Certbot](certbot/README.md) 或宿主机反向代理，并参考 [README.md#configure-https-and-telemetry](README.md#configure-https-and-telemetry) 与 [README.md#client-ip-and-trusted-proxies](README.md#client-ip-and-trusted-proxies)。

## 3. 启动与验证

```sh
# 校验 Compose 配置语法与变量展开
docker compose config -q

# 启动所有服务
docker compose up -d

# 查看容器状态
docker compose ps --all
```

确认以下状态：
- `api` 状态为 `healthy`
- 一次性初始化容器 `init_permissions` 状态为 `Exited (0)`

随后在浏览器打开 `${CONSOLE_WEB_URL}/install` 创建管理员账号。完成后访问 `${CONSOLE_WEB_URL}/console/api/setup`，返回中的 `step` 为 `finished` 即表示初始化成功。

## 4. 常用运维操作

- **使 `.env` 修改生效**：修改 `docker/.env` 后执行 `docker compose up -d`（`docker compose restart` **不会**重新加载环境变量）。
- **检查展开后的配置**：运行 `docker compose config` 核对实际注入容器的环境变量（注意勿将敏感密钥贴到日志或文档中）。
- **停止服务**：`docker compose down`（不加 `-v`，以保留数据库与文件持久化卷）。
- **模型配置**：服务就绪后，参考 [MODEL_RECOMMENDATIONS.md](MODEL_RECOMMENDATIONS.md) 在控制台配置模型供应商与生成参数。
