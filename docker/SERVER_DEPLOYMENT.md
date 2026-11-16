# 服务器 Docker 部署（IP + HTTP）

适用日期：2026-11-16。基于本仓库 `v1.19.0` 分支及其本地修复，面向一台 Linux 服务器的全新部署，使用自带 PostgreSQL、Redis、Weaviate、插件服务和 Agent 沙箱。项目名称固定为 `dify`，访问方式为 `http://服务器IP:端口`。

[deploy.py](deploy.py) 只使用 Python 标准库，可以生成配置并一键启动。它依赖整个 `docker/` 部署目录，不能只复制这一个脚本。不会安装 Docker、修改系统防火墙、配置 HTTPS，或导入本机的账号、插件、模型及知识库数据。

## 1. 服务器准备

- 安装 Python 3（建议使用发行版维护的 Python 3.10 或更高版本）、Docker Engine 和 **Docker Compose 2.35.0 或更高版本**。当前用户必须能访问 Docker daemon。按服务器发行版使用 [Docker 官方安装说明](https://docs.docker.com/engine/install/)。
- [Dify 官方最低要求](https://docs.dify.ai/en/self-host/deploy/quick-start/docker-compose)为 2 核 CPU、4 GiB RAM；实际部署建议从 4 核、8 GiB RAM 起步，并按并发量和知识库大小增加资源。磁盘需要同时容纳镜像、上传文件、数据库和向量数据。
- 能访问 Compose 中的镜像仓库；安装插件时还需要访问 Dify Marketplace 及其依赖源。模型服务单独提供，当前三套机房模型不会被部署到这台机器。
- 选择未被占用的 HTTP 端口，例如 `8080`，不要使用已预留给插件调试的 `5003`。在云安全组及主机防火墙中放行给需要访问的客户端。HTTP 不加密账号和文档传输，初期宜限制在可信网络或指定来源 IP。

先在服务器检查：

```bash
python3 --version
docker info
docker compose version
```

脚本使用当前 Docker context／`DOCKER_HOST` 指向的引擎。在目标服务器本机运行，确认没有指向另一台 Docker 主机。

## 2. 传输部署文件

本分支的修复尚未推送，直接克隆上游的 `v1.19.0` 不会得到这些修改。可使用配套的 `dify-server-1.19.0.tar.gz` 和 `.sha256` 校验文件，或在本机仓库根目录按下面的方式从最新提交重新打包。需要包含的新修改应先提交，未提交的工作区内容不会进入部署包。

```bash
python3 - <<'PY'
import hashlib
from pathlib import Path
import subprocess

package = Path("/tmp/dify-server-1.19.0.tar.gz")
subprocess.run([
    "git", "archive", "--format=tar.gz", "-o", str(package), "HEAD", "docker",
], check=True)
checksum = package.with_name(package.name + ".sha256")
digest = hashlib.sha256(package.read_bytes()).hexdigest()
checksum.write_text(f"{digest}  {package.name}\n")
print(package)
print(checksum)
PY
```

部署包只包含最新提交中的 `docker/` 部署文件，不包含被忽略的本机 `.env`、服务 `.env`、真实密钥、下载的插件或运行数据，也不包含 Docker 镜像。仓库自带的 `volumes/sandbox/conf/config.yaml` 等配置模板会保留。

将文件传到服务器，例如：

```bash
scp /tmp/dify-server-1.19.0.tar.gz \
  /tmp/dify-server-1.19.0.tar.gz.sha256 \
  deploy@SERVER_IP:/tmp/
```

下面的解压、配置和启动命令都在服务器上执行。假设两个文件已上传到 `/tmp/`，部署目录为全新的 `/opt/dify`，HTTP 端口为 `8080`；每一步成功后再继续下一步。

先校验部署包，再创建目录、将目录交给当前部署用户并解压。校验应显示 `OK`。以下命令在子 shell 中执行，任一步失败都会停止；如果 `/opt/dify` 已存在，先核对是否有旧部署，不要直接覆盖：

```bash
(
  set -e

  cd /tmp
  sha256sum -c dify-server-1.19.0.tar.gz.sha256

  sudo mkdir /opt/dify
  sudo chown "$(id -u):$(id -g)" /opt/dify

  tar -xzf dify-server-1.19.0.tar.gz -C /opt/dify
)
```

路径将是 `/opt/dify/docker/`。后续数据也会写入此目录，部署后不要随意移动它。

## 3. 生成配置、检查和启动

将下列示例 IP `192.0.2.10` 替换为客户端实际访问的服务器 IP，端口可改。支持 IPv4 和不带 `%接口名` 的 IPv6 地址。

### 生成配置

```bash
cd /opt/dify/docker

python3 deploy.py init \
  --host 192.0.2.10 \
  --port 8080
```

`init` 检查 Compose 版本、Docker Engine，以及已有配置、默认服务的数据目录和同名 `dify` 容器／命名卷；同名 Agent 沙箱卷即使没有 Compose 标签，也会阻止初始化。检查通过后，新建 `.env` 和 `envs/core-services/web.env`，权限均为 `600`，生成独立随机密钥并验证配置，不在终端打印密钥。

这一步不会拉取镜像或启动容器。

### 检查配置和文件权限

```bash
python3 deploy.py check

stat -c '%a %n' .env envs/core-services/web.env
```

应提示 Compose 配置解析通过，两个文件的权限都应为 `600`。`check` 只解析现有配置，不拉取镜像、不启动容器。

### 启动并查看状态

```bash
python3 deploy.py up --wait-timeout 600

docker compose ps --all
```

`up` 使用已保存的配置，只拉取本地不存在的镜像，再启动服务并等待运行状态及已有健康检查。一次性 `init_permissions` 服务显示 `Exited (0)` 是正常情况；其他服务应为运行状态，有健康检查的服务应为 `healthy`。`--wait` 不代表所有业务能力已通过验证，详见 [Compose up 文档](https://docs.docker.com/reference/cli/docker/compose/up/)。

### 访问并初始化管理员

确认云安全组和主机防火墙允许客户端访问所选的 HTTP 端口（本例为 **TCP 8080**），然后在浏览器打开 `http://192.0.2.10:8080/install`，创建管理员账号。地址中的 IP 和端口必须与 `init` 时填写的值一致。之后再按第 5 节安装插件、配置模型。

### 可选：一次完成初始化和启动

对于尚未执行 `init` 的全新部署，可用下面一条命令替代以上生成配置、检查和启动步骤：

```bash
cd /opt/dify/docker
python3 deploy.py deploy --host 192.0.2.10 --port 8080
```

`deploy` 会立即执行初始化、配置检查和启动。已运行 `init` 后应使用 `up`，重复执行 `init` 或 `deploy` 会因已有配置而退出；首次启动失败时应修正原因后用 `up` 重试，保留已有配置和密钥。

## 4. 自动生成的配置

| 位置／配置 | 用途 |
| --- | --- |
| `.env`：`COMPOSE_PROJECT_NAME=dify` | 使用稳定的容器、网络和命名卷前缀 |
| `.env`：`COMPOSE_PROFILES=weaviate,postgresql,collaboration` | 启用默认数据库、向量库及协作服务 |
| `.env`：`EXPOSE_NGINX_PORT` | 对外 HTTP 端口 |
| `.env`：`CONSOLE_API_URL=`、`APP_API_URL=` | 显式使用浏览器同域地址，包含已验证的供应商图标修复 |
| `.env`：`CONSOLE_WEB_URL`、`APP_WEB_URL`、`SERVICE_API_URL`、`FILES_URL`、`TRIGGER_URL` | 使用输入的 HTTP 地址，覆盖镜像或应用中的 localhost 默认值 |
| `.env`：`NEXT_PUBLIC_SOCKET_URL` | 对应的 `ws://服务器IP:端口`，用于远程协作 |
| `.env`：`INTERNAL_FILES_URL=http://api:5001` | 容器之间通过内部 API 地址访问文件 |
| `.env` 中的密钥与密码 | 为应用、PostgreSQL、Redis、插件、两种沙箱及 Agent 生成密钥，并保持客户端与服务端一致 |
| `.env` 中的 Weaviate 设置 | 生成并共享 API Key，关闭匿名访问 |
| `envs/core-services/web.env` | 仅设置 Web 的 `HOSTNAME=0.0.0.0` |

插件调试端口绑定 `127.0.0.1:5003`。本方案不启用 Nginx HTTPS；Compose 仍声明的 SSL 端口映射到回环地址的随机宿主端口，不占用公网或宿主 `443`。对客户端只需开放所选的 HTTP 端口。

脚本显式选择本目录的 `.env` 和 `docker-compose.yaml`，忽略 shell 中同名的 Compose／应用配置变量，避免覆盖文件值。需要调整时编辑文件；后续直接运行 `docker compose` 时，也应避免 shell 中残留的同名变量。

镜像标签由现有 Compose 定义，脚本不修改标签、不构建镜像。已缓存的镜像包括 `latest` 都会复用，只有缺失镜像才拉取。不同时间首次部署得到的可变标签内容仍可能不同；需要严格一致的部署时，应另外固定镜像 digest。

修改 IP 或 HTTP 端口后，要同步调整上表中的公开地址和 WebSocket 地址，再运行 `python3 deploy.py check` 与 `python3 deploy.py up`。单纯 `docker compose restart` 不会重新加载环境变量。

## 5. 初始化模型及验证

在新服务中安装 OpenAI-API-compatible 插件，再根据 [模型配置记录](MODEL_RECOMMENDATIONS.md)填写服务器能访问的模型地址、API Key 和推荐参数。文档基于插件 `0.0.83`；安装其他版本时先核对字段含义。两套生成参数需要在应用或工作流中选择。

机房 `Qwen3-Reranker-4B` 的评分异常仍未解决，不能因为新部署成功就视为已修复。它的处理条件与复测要求见模型配置记录。

初次登录后确认：供应商图标可见，模型能通过服务器真实调用，文件能上传和访问，工作流可以保存／运行。若使用协作功能，检查浏览器的 WebSocket 连接。这些业务检查需要实际运行环境，脚本不会创建测试账号、应用或知识库。

## 6. 排障、重试和数据维护

在 `/opt/dify/docker/` 中检查状态与必要日志：

```bash
cd /opt/dify/docker

docker compose ps --all
docker compose logs --tail 100 \
  init_permissions api worker web nginx plugin_daemon
```

修正问题后使用已有配置重试，需要时将启动等待时间增加到 1200 秒，不要重新执行 `init`：

```bash
python3 deploy.py up --wait-timeout 1200
```

- Docker 不可访问：先检查 `docker info`、当前 context 和用户权限；脚本不会自动安装 Docker 或调整用户组。
- Compose 配置失败：运行 `docker compose config -q` 查看错误，修正文件后重试。不要公开完整 `docker compose config` 的输出，其中包含密钥。
- 镜像拉取失败：检查报错的仓库、网络、架构支持和所需登录。配置和已拉取镜像保留，修正后运行 `python3 deploy.py up`。
- 端口冲突：修改 `.env` 的发布端口，并同步所有公开 URL；或者处理已占用该端口的服务。
- 启动等待超时或部分服务失败：已启动的容器会保留，脚本不会删除数据或自动回滚。检查日志并修复后用 `up` 重试。
- 提示已有配置／数据／同名资源：先确认是否是原有 Dify。原有部署应在原目录维护，不要删除 `.env` 来强行重新初始化；数据库有数据后，单改 `.env` 中的数据库密码也不会替数据库修改账号密码。

持久化包括 `volumes/` 下的绑定目录，以及 `dify_dify_agent_local_sandbox_home`、`dify_dify_agent_local_sandbox_workspace` 两个 Docker 命名卷。路径明细见 [本地存储记录](LOCAL_CHANGES.md#compose-项目名与本地存储)。备份需同时覆盖配置密钥、数据库一致性备份、文件、向量数据和命名卷；只备份源码或部署包无法恢复业务数据。不要用 `docker compose down -v` 作为普通重试操作。

这是一份全新部署脚本，后续升级或从本机迁移数据需单独制定备份及迁移步骤。
