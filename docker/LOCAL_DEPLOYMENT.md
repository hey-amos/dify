# Dify 1.20.0 本地部署

部署机至少需要 2 核 CPU 和 4 GiB 内存。启动 Docker，确认已安装 Docker Compose v2.35.0 或更高版本及 OpenSSL。在仓库根目录打开终端。[官方部署说明](README.md#start-dify)

## 1. 准备启动配置

```sh
cd docker
test -f .env || cp -n .env.example .env
chmod 600 .env
```

默认使用 PostgreSQL、Weaviate 和协作服务，在 `.env` 保留 `COMPOSE_PROFILES=weaviate,postgresql,collaboration`。如果 `DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN` 为空，运行以下命令，把生成的令牌填入该项并保存。Agent 后端和本地沙箱共用这个令牌。

```sh
openssl rand -hex 32
```

### 可选端口和访问地址

默认 HTTP 端口为 `80`。若要改用 `8080`，在 `.env` 中添加或修改下列配置。HTTPS 和插件调试端口可分别通过 `EXPOSE_NGINX_SSL_PORT` 和 `EXPOSE_PLUGIN_DEBUGGING_PORT` 调整。

```dotenv
EXPOSE_NGINX_PORT=8080
```

现有 OrbStack 部署在 `docker/.env` 中设置了多项 `http://localhost:18080` 地址。给这套实例换域名时，直接在该文件中更新对应的公开地址。同名项以 `docker/.env` 为准，显式空值也会覆盖服务文件。新部署可按下表配置。[1.20.0 公共 URL 加载顺序](README.md#change-public-urls)

| 新部署的配置文件 | 公开地址 |
| --- | --- |
| `envs/core-services/urls.env` | `CONSOLE_API_URL`、`CONSOLE_WEB_URL`、`SERVICE_API_URL`、`APP_API_URL`、`APP_WEB_URL` 填站点地址，如 `https://dify.example.com`。Dify 会拼接相应路径。 |
| `envs/core-services/api-worker.env` | 文件下载用 `FILES_URL`，触发器用 `TRIGGER_URL`。使用插件端点时，另设 `ENDPOINT_URL_TEMPLATE=https://dify.example.com/e/{hook_id}`，保留占位符。[API 与 worker 配置项](envs/core-services/api-worker.defaults) |

`CONSOLE_API_URL` 和 `APP_API_URL` 留空时，浏览器会使用当前站点。部署 HTTPS 控制台时，把 `CONSOLE_API_URL` 和 `CONSOLE_WEB_URL` 都设为实际 HTTPS 地址，Dify 才会给登录 Cookie 设置 `Secure`。[Cookie 实现](../api/libs/token.py)

容器间访问沿用内部地址，本实例的 `SERVER_CONSOLE_API_URL` 和 `INTERNAL_FILES_URL` 均为 `http://api:5001`。工作流多人协作使用同一域名时，沿用本实例的 `NEXT_PUBLIC_SOCKET_URL=/`。新部署可在 `envs/core-services/web.env` 设置该项，默认值为 `ws://localhost`。[Web 配置项](envs/core-services/web.defaults)

## 2. 启动并检查服务

在同一个 `docker/` 目录执行以下命令。

```sh
docker compose config -q
docker compose up -d
docker compose ps --all
```

等待 `api` 显示 `healthy`，一次性任务 `init_permissions` 显示 `Exited (0)`。若 `agent_backend` 或 `local_sandbox` 反复重启，核对第 1 步的令牌，再运行 `docker compose up -d` 应用配置。

## 3. 创建管理员账户

在部署机上打开安装页面，按提示创建管理员账户并登录。从其他电脑访问时，将 `localhost` 换成部署机可访问的 IP 或域名。[默认端口安装页面](http://localhost/install) · [8080 端口安装页面](http://localhost:8080/install)

完成后访问同一站点的 `/console/api/setup`，确认响应中的 `step` 为 `finished`。
