# 服务器 Docker 部署

适用于本仓库 `v1.19.0` 及本地部署修复。服务器准备好 Bash、Docker Engine 和 Docker Compose 2.35.0 或更高版本即可，不需要 Python。拉取包含这些修改的代码后，使用完整的 `docker/` 目录。

## 使用

进入仓库的 `docker/` 目录，填写客户端实际访问的服务器 IP 或域名，以及 HTTP 端口：

```bash
cd /path/to/dify/docker
bash deploy.sh --host 192.0.2.10 --port 8080
```

脚本只做三件事：

1. 缺少 `.env` 或 `envs/core-services/web.env` 时创建文件。
2. 补上这些文件里尚未定义的部署变量，已有值保留。
3. 执行 `docker compose up -d`。

默认地址为 `localhost`，HTTP 端口为 `80`；服务器部署时填写实际可达的地址。脚本支持域名和 IPv4；IPv6 直接传入地址，不带方括号。HTTP 端口需避开插件调试使用的 `5003`。

重复运行同一条命令即可补齐遗漏并启动容器。`--host` 和 `--port` 只为缺失项提供初始值，不会覆盖已有配置。已补齐的部署也可以直接运行：

```bash
bash deploy.sh
```

首次启动后，访问 `http://服务器IP:端口/install` 初始化账号，再按 [MODEL_RECOMMENDATIONS.md](MODEL_RECOMMENDATIONS.md) 配置插件和模型。

## 补充的配置

| 位置 | 缺失时补充的内容 |
| --- | --- |
| `.env` | 项目名 `dify`、默认 profiles、Nginx 端口及插件调试端口 |
| `.env` | 同源控制台 API、WebSocket `/`、公开访问地址和内部文件地址 |
| `.env` | 必填的 `DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN`，仅在未定义时生成随机值 |
| `envs/core-services/web.env` | `HOSTNAME=0.0.0.0` |

新文件权限为 `600`，已有文件的权限不变。已有变量按名称判断，包括显式空值，都不会被替换；被注释的行不算已定义。脚本只追加缺失项，保留原有注释和其他设置。

公开 URL 使用 Compose 自带的变量引用：`CONSOLE_WEB_URL` 引用 `EXPOSE_NGINX_PORT`，其余新补的公开 URL 引用 `CONSOLE_WEB_URL`。这样已有的公开入口和端口能继续被复用；控制台 API 使用相对路径，WebSocket 跟随浏览器入口。

数据库、Redis、插件等其他设置沿用现有配置或项目默认值，脚本不会额外生成或替换它们的密码。旧脚本已生成的自定义密钥也会保留。根 `.env` 和服务专属 `.env` 的优先级仍遵循 [原部署说明](README.md#configure-dify)，调用终端的环境变量也按 Compose 原有规则生效。

缺失时，HTTPS 映射设为 `127.0.0.1:0`，插件调试端口设为 `127.0.0.1:5003`；默认使用 HTTP。修改已存在的访问地址或端口时，直接编辑 `.env` 后再次运行脚本。已有的绝对 URL 需要一起调整，新补的变量引用则会随其引用值变化。

## 查看状态或重试

```bash
docker compose ps --all
docker compose logs --tail 100 api web nginx plugin_daemon
```

镜像处理、容器启动和错误信息直接交给 Docker Compose。启动出错时，修正报错后重新运行脚本，已补齐的配置会保留。脚本不额外扫描数据卷、判断部署归属、拉取镜像或等待健康检查。

脚本执行结束表示 Compose 启动命令已完成；页面访问和模型调用需在服务启动后确认。持久化路径见 [本地存储说明](LOCAL_CHANGES.md#compose-项目名与本地存储)。
