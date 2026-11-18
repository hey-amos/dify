# Dify 1.19.0 本地部署配置

准备至少 2 核 CPU、4 GiB 内存的部署机。启动 Docker，确认已安装 Docker Compose（v2.35.0 或更高版本）和 OpenSSL。在项目根目录打开终端。

## 1. 填写启动配置

```sh
cd docker
test -f .env || cp -n .env.example .env
chmod 600 .env
```

打开 `.env`，保留 `COMPOSE_PROFILES=weaviate,postgresql,collaboration`。如果 `DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN=` 为空，运行以下命令，把输出粘贴到等号后并保存。已有令牌可直接沿用。

```sh
openssl rand -hex 32
```

<details>
<summary>更改端口、分享地址或 Web 监听地址（可选）</summary>

只更改 HTTP 端口时，在 `.env` 设置 `EXPOSE_NGINX_PORT=18080`。如果宿主机的 `443` 或 `5003` 已被占用，分别将 `EXPOSE_NGINX_SSL_PORT` 或 `EXPOSE_PLUGIN_DEBUGGING_PORT` 设为可用端口。

需要固定应用、文件和触发器的分享地址时，将下列配置填入 `.env`，同名项直接修改。供其他电脑访问时，将 `CONSOLE_WEB_URL` 中的 `localhost` 换成服务器 IP 或域名。已有实例沿用原来的 `COMPOSE_PROJECT_NAME`。

```dotenv
COMPOSE_PROJECT_NAME=dify
EXPOSE_NGINX_PORT=18080
EXPOSE_NGINX_SSL_PORT=18443

CONSOLE_API_URL=
CONSOLE_WEB_URL=http://localhost:${EXPOSE_NGINX_PORT}
SERVICE_API_URL=${CONSOLE_WEB_URL}
APP_WEB_URL=${CONSOLE_WEB_URL}
FILES_URL=${CONSOLE_WEB_URL}
TRIGGER_URL=${CONSOLE_WEB_URL}
INTERNAL_FILES_URL=http://api:5001
NEXT_PUBLIC_SOCKET_URL=/
```

需要指定 Web 监听地址时，新建或编辑 `envs/core-services/web.env`，填入 `HOSTNAME=0.0.0.0`。

</details>

## 2. 启动服务

```sh
docker compose config -q
docker compose up -d
docker compose ps --all
```

等待 `api` 显示 `healthy`、`init_permissions` 显示 `Exited (0)`。若 `agent_backend` 或 `local_sandbox` 反复重启，核对第 1 步的令牌，再执行 `docker compose up -d`。

## 3. 创建管理员并登录

1. 在浏览器中打开 [http://localhost/install](http://localhost/install)。如果使用 `18080` 端口，打开 [http://localhost:18080/install](http://localhost:18080/install)。从其他电脑访问时，将 `localhost` 换成服务器 IP 或域名。
2. 按页面提示创建管理员账户，并登录控制台。
3. 打开同一站点的 `/console/api/setup`，确认返回的 `step` 为 `finished`。
