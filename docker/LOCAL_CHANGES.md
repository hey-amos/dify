# 本地部署修改记录

初始记录日期：2026-11-14；最近更新：2026-11-16。

基线为 `v1.19.0` 分支的 `8e689e868b`，镜像标签保持不变。初始配置及项目名调整阶段未启动容器；用户随后已启动服务，完成管理员账户、插件和三个模型的初始配置。当前已进入运行验证阶段。

后续 agent 的协作入口为 [AGENTS.md](AGENTS.md)，其中记录配置维护规则、验证方式及操作范围。部署修改集中记录在本文，模型参数、两套生成方案和实测结果见 [MODEL_RECOMMENDATIONS.md](MODEL_RECOMMENDATIONS.md)。

## 修改清单

以下路径均相对于 `docker/`。

| 文件 | 修改内容 | Git 管理 |
| --- | --- | --- |
| [docker-compose-template.yaml](docker-compose-template.yaml) | 补齐插件存储目录权限初始化、初始化失败退出和插件启动依赖 | 跟踪 |
| [docker-compose.yaml](docker-compose.yaml) | 从模板重新生成，供 Docker Compose 实际读取 | 跟踪 |
| [.env](.env) | 设置项目名 `dify`，显式清空 `CONSOLE_API_URL` 以使用同域地址，保留默认 profiles 和沙箱 token；不设置 `HOSTNAME` | 忽略 |
| [envs/core-services/web.env](envs/core-services/web.env) | 仅为 Web 设置 `HOSTNAME=0.0.0.0` | 忽略 |
| [MODEL_RECOMMENDATIONS.md](MODEL_RECOMMENDATIONS.md) | 记录三个模型的已保存配置、问答和推理两套生成参数、真实调用结果及机房重排待办 | 跟踪 |

`.env` 和 `web.env` 属于本机部署配置，不会随 Git 提交或克隆传递。重新部署时需要单独准备它们；本文不记录任何真实 token。

## 插件存储权限修复

回移上游提交 [18ff0c9ef1](https://github.com/langgenius/dify/commit/18ff0c9ef17fdcbceec181d1f59a4d2a74cf57d9) 的 Compose 修改：

- `init_permissions` 同时挂载 API 存储和插件存储，分别初始化为 `1001:1001`。
- 两个目录分别使用 `.init_permissions` 标记。API 目录已初始化时，仍会处理尚未初始化的插件目录。
- `chown` 或创建标记失败时返回非零状态，阻止依赖该初始化的服务继续启动。
- `plugin_daemon` 等待 `init_permissions` 成功完成后再启动。

该修复处理新部署时插件目录不可写而导致安装插件失败的问题。初始配置阶段未操作真实持久化目录，权限由启动时的初始化服务设置；用户随后已启动部署并安装插件。

Compose 文件由模板生成。以后修改模板后，在 `docker/` 目录运行：

```bash
python3 generate_docker_compose --compose-only
```

该命令只生成 Compose 文件，不修改已有 `.env`，也不会启动容器。

## Web 监听地址配置

`envs/core-services/web.env` 的有效配置为：

```dotenv
HOSTNAME=0.0.0.0
```

Compose 的 `web.env_file` 已明确引用这个可选文件。它在现有 `1.19.0` 镜像启动时设置 Web 的环境变量，无需为这项配置重建镜像。

固定监听地址可避免 Next.js 使用 Docker 自动生成的容器 hostname，规避特定容器 ID 被 Node 当成数值处理而导致的并发请求超时。上游镜像修复见 [PR #45193](https://github.com/langgenius/dify/pull/45193)。

根 `.env` 中已移除 `HOSTNAME` 及对应注释。这样该变量只传给 Web，不再传给同样读取根 `.env` 的 API、worker、插件等服务。根 `.env` 的同名值优先级更高，后续不要在两处重复配置。

根 `.env` 继续负责：

- `COMPOSE_PROJECT_NAME=dify`。
- `COMPOSE_PROFILES=weaviate,postgresql,collaboration`。
- `CONSOLE_API_URL=`，显式覆盖 API 镜像的 localhost 默认值。
- `DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN`，由 Agent 后端和本地沙箱共同使用。

沙箱 token 在此次配置迁移中保持不变，根 `.env` 文件权限保持为 `600`。配置分工和覆盖规则见 [部署说明](README.md#configure-dify)。

## 已安装模型供应商图标修复

运行后发现 OpenAI-API-compatible 图标使用 `http://127.0.0.1:5001/console/api/...`，无法在当前 HTTPS 访问方式下加载。同一图标路径通过 `https://nginx.dify.orb.local` 请求返回 HTTP 200 和 SVG，因此图标文件本身正常。

实际运行的 `langgenius/dify-api:1.19.0` 镜像继承了 `CONSOLE_API_URL=http://127.0.0.1:5001`；来源可见 [API Dockerfile](../api/Dockerfile)。[供应商响应代码](../api/services/entities/model_provider_entities.py)使用该值拼接图标地址。

在根 `.env` 中增加：

```dotenv
# Use same-origin console API URLs instead of the API image localhost default.
CONSOLE_API_URL=
```

这里留空是有意的覆盖，不能直接删除该行，否则 API 容器会重新继承镜像的 localhost 值。当前为同域 Nginx 部署，生成的相对图标路径由浏览器按当前 HTTPS 域名解析；变量含义见 [Dify 环境变量文档](https://docs.dify.ai/en/self-host/deploy/configuration/environments#console-api-url)。

Compose 解析验证通过后，仅重建了读取该配置的 `api`、`api_websocket`、`worker` 和 `worker_beat`；未升级镜像或改动数据卷。Web 的有效 `CONSOLE_API_URL` 原本就是空值，无需重建。浏览器刷新后已确认供应商图标实际加载成功。

这项修复只处理控制台图标地址，没有配置 OAuth 回调、外部文件访问或其他公开服务地址。

## 模型配置与运行验证

已通过现有 Dify 的模型凭据接口保存三个模型的非敏感参数，并保留原有地址、名称和密钥。语言模型和 Embedding 的关键能力在保存后复测通过。温度、输出预算等应用级参数按“通用问答／知识库”和“复杂推理／Agent”分别记录，没有创建或修改用户应用。

Reranker 的上下文已改为端点实际开放的 8192，但普通请求的排序质量仍有异常。按官方评分格式构造输入的对照测试恢复正常排序，问题强烈指向机房评分模板；用户要求先记录，暂不处理机房服务。详细证据、待办和建议值见 [模型配置记录](MODEL_RECOMMENDATIONS.md)。

## Compose 项目名与本地存储

根 `.env` 已设置：

```dotenv
COMPOSE_PROJECT_NAME=dify
```

项目名统一使用不带版本号的 `dify`，作为长期部署标识，避免版本升级时一并改变资源前缀。该设置覆盖默认目录名 `docker`，无需修改 Compose 模板。命令行 `-p` 或调用进程中已有的同名环境变量仍可覆盖本地配置，详见 [Docker 项目名规则](https://docs.docker.com/compose/how-tos/project-name/)。

默认服务将使用类似 `dify-web-1` 的容器名，默认网络解析为 `dify_default`。后续升级镜像时保持项目名不变，才能继续按原名称使用同一组命名卷。

### 本地目录挂载

以下是默认 profiles 使用的主要数据目录；路径相对于 `docker/`，修改项目名不会改变这些挂载源。

| 用途 | 本地目录 | 容器内路径 |
| --- | --- | --- |
| API、worker 等共享文件存储 | `volumes/app/storage` | `/app/api/storage` |
| PostgreSQL 数据 | `volumes/db/data` | `/var/lib/postgresql/data` |
| Redis 数据 | `volumes/redis/data` | `/data` |
| Weaviate 数据 | `volumes/weaviate` | `/var/lib/weaviate` |
| 插件文件与运行数据 | `volumes/plugin_daemon` | `/app/storage` |
| Code 沙箱依赖 | `volumes/sandbox/dependencies` | `/dependencies` |
| Code 沙箱配置 | `volumes/sandbox/conf` | `/conf` |
| 证书和 ACME 文件 | `volumes/certbot/conf`、`volumes/certbot/www` | `/etc/letsencrypt`、`/var/www/html` |

插件目录还会挂载给初始化服务，用于设置权限。Nginx 和 SSRF 代理另外挂载仓库中的配置模板、脚本及配置目录，这些同样属于目录或文件绑定挂载。

### Docker 命名卷

默认 profiles 启用两个命名卷，由 Docker 引擎管理，不位于仓库的 `docker/volumes/` 下：

| 实际卷名 | 挂载服务 | 容器内路径 |
| --- | --- | --- |
| `dify_dify_agent_local_sandbox_home` | `local_sandbox` | `/home/dify` |
| `dify_dify_agent_local_sandbox_workspace` | `local_sandbox` | `/workspace` |

完整 Compose 还声明了 Oracle 的 `oradata` 和 Elasticsearch 的 `dify_es01_data`，仅在启用相应服务时使用。文件未显式配置匿名卷、外部卷或远程卷驱动；命名卷使用引擎默认配置，见 [Docker 卷定义](https://docs.docker.com/reference/compose-file/volumes/)。

改项目名不会自动重命名已有资源或迁移卷数据。新项目名会查找新前缀的命名卷，而本地绑定目录仍指向原路径，因此不能仅靠不同项目名隔离多套数据库数据；并行部署还需分别配置数据路径和主机端口。部分可选服务还使用固定的 `container_name`，启用它们时需要额外核对名称冲突。

此前项目名更正阶段仅更新本机配置和修改记录，并验证 Compose 解析结果。当时没有创建、移动或删除卷，也没有启动容器。

## 初始部署阶段验证记录

- 权限修复后，现有 26 项 Compose 配置测试通过。
- 使用临时目录和模拟命令验证了五种初始化情况：全新目录、API 已初始化但插件目录未初始化、插件权限设置失败、插件初始化标记创建失败、两个目录均已初始化。
- 本次迁移后重新解析实际部署配置：默认仍启用 16 个服务，只有 `web` 收到 `HOSTNAME=0.0.0.0`。
- Agent 后端与本地沙箱仍读取同一原有 token；插件服务仍等待权限初始化成功。
- 项目改名后，默认及全部 profiles 的配置均解析成功；项目名为 `dify`，服务选择和所有本地绑定路径保持不变，命名卷使用新的项目前缀。
- Compose 模板与生成文件保持一致，`git diff --check` 通过。

可从仓库根目录复查配置测试：

```bash
python3 docker/tests/test_compose_environment.py
```

可从 `docker/` 目录仅校验 Compose 配置：

```bash
docker compose config -q
```

这些配置检查不会启动容器。用户后续已安装插件；本次运行验证覆盖图标加载及模型调用，未重装插件，也未进行 Web 并发或整套服务的压力测试。

## 2026-11-16：服务器部署入口

新增 [服务器部署说明](SERVER_DEPLOYMENT.md)、[部署脚本](deploy.py) 和 [针对性测试](tests/test_server_deploy.py)，并在本地新增的 AGENTS 中增加入口。用户选择先通过服务器 IP 和 HTTP 端口访问。

按用户要求，已撤销原有 `README.md` 中新增的导航。后续本地部署说明和工具优先通过新增独立文件提供，尽量保持原项目文件不变。

- 面向全新 Linux 单机部署，沿用当前 Compose 和项目名 `dify`；不改 Compose 模板、生成文件或镜像标签。
- `deploy` 初始化并启动，`init` 只生成配置，`check` 只校验，`up` 使用现有配置启动或重试。脚本不安装 Docker，不自动修改主机网络设置。
- 在新服务器生成权限为 `600` 的根 `.env` 和 Web 专属 `.env`，生成独立的应用、数据库、Redis、插件及沙箱密钥，正确配对服务端与客户端；Weaviate 使用随机密钥并关闭匿名访问。
- 纳入同域图标地址和 Web `HOSTNAME` 修复，按服务器 IP／端口配置公开 URL 与协作 WebSocket；插件调试端口仅绑定回环地址，不启用 HTTPS。
- 遇到已有配置、默认服务数据或同名 Docker 容器／命名卷时拒绝初始化；保留凭据，重试不重新生成。只拉取缺失镜像，已有本地镜像继续使用。
- 提交前审查补齐边界：拒绝与插件调试冲突的 HTTP `5003` 端口，识别没有 Compose 标签的同名 Agent 沙箱卷，并拒绝带 scope ID 的 IPv6 输入，避免生成无效 URL 或混入额外环境配置行。
- 提供仅包含部署文件的传输包生成方法，排除本机 `.env`、插件缓存和运行数据；模型推荐参数通过文档在新实例中另行配置。
- 部署说明补充完整操作步骤：从最新提交打包并生成 SHA256 校验文件，上传、校验、新建目录和解压，再分步生成配置、检查权限、启动、查看状态及失败重试；原有 `README.md` 保持还原状态。本次仅更新文档，没有执行其中的启动命令。

新增 13 项部署脚本测试和现有 26 项 Compose 测试均通过。验证使用临时目录和合成密钥，覆盖真实 Compose 的变量传递、HTTP／WebSocket 地址、端口、已有数据保护、重复初始化、旧 Compose 版本及启动失败分支。未在本机或远端启动、重建容器，未修改当前正在使用的环境文件或模型配置；服务器实际镜像拉取、启动及业务验证需在目标环境执行。
