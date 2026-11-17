#!/usr/bin/env bash
# Fill missing deployment settings, preserve existing values, then start Compose.
set +x
set -euo pipefail
umask 077
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

deploy_host=localhost
deploy_port=80
while (( $# )); do
    case "$1" in
        --host|--port)
            if [[ $# -lt 2 || -z "$2" ]]; then printf '%s 缺少参数值。\n' "$1" >&2; exit 1; fi
            if [[ "$1" == --host ]]; then deploy_host=$2; else deploy_port=$2; fi
            shift 2 ;;
        -h|--help)
            printf '用法：bash deploy.sh [--host 服务器IP或域名] [--port HTTP端口]\n缺失项才补充，已有配置不覆盖；随后执行 docker compose up -d。\n'
            exit 0 ;;
        *) printf '未知参数：%s\n' "$1" >&2; exit 1 ;;
    esac
done
# Only reject values that cannot safely form a URL or a port setting.
[[ "$deploy_host" =~ ^[A-Za-z0-9.:-]+$ ]] || { printf '请填写不带协议的 IP 或域名。\n' >&2; exit 1; }
[[ "$deploy_port" =~ ^[0-9]{1,5}$ ]] || { printf '端口必须为 1–65535。\n' >&2; exit 1; }
deploy_port=$((10#$deploy_port))
(( deploy_port >= 1 && deploy_port <= 65535 )) || { printf '端口必须为 1–65535。\n' >&2; exit 1; }
if [[ "$deploy_host" == *:* ]]; then deploy_host="[$deploy_host]"; fi

mkdir -p envs/core-services
for deploy_file in .env envs/core-services/web.env; do
    if [[ ! -e "$deploy_file" ]]; then : > "$deploy_file"; fi
done

has_setting() {
    grep -Eq "^[[:space:]]*(export[[:space:]]+)?$2[[:space:]]*[:=]" "$1"
}

add_setting() {
    if ! has_setting "$1" "$2"; then
        # The leading newline also handles an existing file without a final newline.
        printf '\n%s=%s\n' "$2" "$3" >> "$1"
    fi
}

add_setting .env COMPOSE_PROJECT_NAME dify
add_setting .env COMPOSE_PROFILES weaviate,postgresql,collaboration
add_setting .env EXPOSE_NGINX_PORT "$deploy_port"
add_setting .env EXPOSE_NGINX_SSL_PORT 127.0.0.1:0
add_setting .env EXPOSE_PLUGIN_DEBUGGING_PORT 127.0.0.1:5003
add_setting .env CONSOLE_API_URL ''
add_setting .env CONSOLE_WEB_URL "http://${deploy_host}:\${EXPOSE_NGINX_PORT}"
for deploy_key in SERVICE_API_URL APP_WEB_URL FILES_URL TRIGGER_URL; do
    add_setting .env "$deploy_key" '${CONSOLE_WEB_URL}'
done
add_setting .env INTERNAL_FILES_URL http://api:5001
add_setting .env NEXT_PUBLIC_SOCKET_URL /
add_setting envs/core-services/web.env HOSTNAME 0.0.0.0

if ! has_setting .env DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN; then
    deploy_token=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
    add_setting .env DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN "$deploy_token"
fi

printf '缺失配置已补齐，正在启动容器……\n'
exec docker compose up -d
