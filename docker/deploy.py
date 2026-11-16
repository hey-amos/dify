#!/usr/bin/env python3
"""Prepare and start this checkout's single-server HTTP deployment."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

DOCKER_DIR = Path(__file__).resolve().parent
PROJECT = "dify"
PLUGIN_DEBUG_PORT = 5003


class DeploymentError(Exception):
    pass


def docker_env() -> dict[str, str]:
    """Use files in this checkout, not exported Compose/application overrides."""
    sources = [DOCKER_DIR / "docker-compose.yaml", DOCKER_DIR / ".env"]
    sources.extend((DOCKER_DIR / "envs").rglob("*.defaults"))
    sources.extend((DOCKER_DIR / "envs").rglob("*.env"))
    inputs = set()
    for path in sources:
        if path.is_file():
            content = path.read_text()
            inputs.update(re.findall(r"\$\{(\w+)", content))
            inputs.update(re.findall(r"^([A-Z][A-Z0-9_]*)=", content, re.M))
    return {
        key: value for key, value in os.environ.items()
        if key not in inputs and not key.startswith("COMPOSE_")
    }


def docker(*args: str, capture: bool = True, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], cwd=DOCKER_DIR, env=docker_env(),
        text=True, capture_output=capture, check=check,
    )


def compose(*args: str, capture: bool = True) -> subprocess.CompletedProcess:
    return docker(
        "compose", "--project-directory", str(DOCKER_DIR),
        "--env-file", str(DOCKER_DIR / ".env"),
        "-f", str(DOCKER_DIR / "docker-compose.yaml"),
        *args, capture=capture,
    )


def check_compose_version() -> None:
    version = docker("compose", "version", "--short").stdout.strip()
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", version)
    if not match or tuple(map(int, match.groups())) < (2, 35, 0):
        raise DeploymentError("需要 Docker Compose 2.35.0 或更高版本。")


def check_engine() -> None:
    if docker("info", "--format", "{{.OSType}}").stdout.strip() != "linux":
        raise DeploymentError("需要已运行且当前用户可访问的 Linux Docker Engine。")


def require_new_deployment() -> None:
    env_file = DOCKER_DIR / ".env"
    if env_file.exists() or env_file.is_symlink() or list((DOCKER_DIR / "envs").rglob("*.env")):
        raise DeploymentError("发现已有 .env 配置，未覆盖。已初始化的部署请使用 check / up。")
    for name in ("app", "db", "redis", "weaviate", "plugin_daemon", "sandbox/dependencies"):
        path = DOCKER_DIR / "volumes" / name
        if path.is_symlink() or (path.exists() and (not path.is_dir() or any(path.iterdir()))):
            raise DeploymentError(f"发现已有数据目录 volumes/{name}，请使用全新的部署目录。")
    check_engine()
    for args in (("ps", "--all", "--quiet"), ("volume", "ls", "--quiet")):
        if docker(*args, "--filter", f"label=com.docker.compose.project={PROJECT}").stdout.strip():
            raise DeploymentError("Docker 中已有 dify 项目的容器或命名卷，不能按全新部署初始化。")
    # Manually restored volumes may have the same names without Compose labels.
    existing_volumes = set(docker(
        "volume", "ls", "--quiet", "--filter", f"name={PROJECT}_dify_agent_local_sandbox_",
    ).stdout.splitlines())
    if any(f"{PROJECT}_dify_agent_local_sandbox_{suffix}" in existing_volumes for suffix in ("home", "workspace")):
        raise DeploymentError("Docker 中已有同名 Agent 沙箱卷，不能按全新部署初始化。")


def initialize(host: str, port: int) -> None:
    if port == PLUGIN_DEBUG_PORT:
        raise DeploymentError(f"HTTP 端口不能使用插件调试端口 {PLUGIN_DEBUG_PORT}，请选择其他端口。")
    address = ipaddress.ip_address(host)
    if address.is_unspecified or address.is_multicast:
        raise DeploymentError("--host 必须是客户端实际访问的服务器 IP。")
    if isinstance(address, ipaddress.IPv6Address) and address.scope_id is not None:
        raise DeploymentError("--host 不支持带 %接口名的 IPv6 地址，请使用客户端可直接访问的 IP。")
    host_part = f"[{address}]" if address.version == 6 else str(address)
    authority = host_part if port == 80 else f"{host_part}:{port}"
    origin = f"http://{authority}"
    require_new_deployment()

    code_key = secrets.token_hex(32)
    vector_key = secrets.token_hex(32)
    values = {
        "COMPOSE_PROJECT_NAME": PROJECT,
        "COMPOSE_PROFILES": "weaviate,postgresql,collaboration",
        "EXPOSE_NGINX_PORT": str(port),
        # Reserve neither public HTTPS nor the host's 443 port in HTTP mode.
        "EXPOSE_NGINX_SSL_PORT": "127.0.0.1:0",
        "EXPOSE_PLUGIN_DEBUGGING_PORT": f"127.0.0.1:{PLUGIN_DEBUG_PORT}",
        "CONSOLE_API_URL": "",
        "CONSOLE_WEB_URL": origin,
        "SERVICE_API_URL": origin,
        "APP_API_URL": "",
        "APP_WEB_URL": origin,
        "FILES_URL": origin,
        "INTERNAL_FILES_URL": "http://api:5001",
        "TRIGGER_URL": origin,
        "NEXT_PUBLIC_SOCKET_URL": f"ws://{authority}",
        "SECRET_KEY": secrets.token_hex(32),
        "DB_PASSWORD": secrets.token_hex(32),
        "REDIS_PASSWORD": secrets.token_hex(32),
        "PLUGIN_DAEMON_KEY": secrets.token_hex(32),
        "PLUGIN_DIFY_INNER_API_KEY": secrets.token_hex(32),
        "DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN": secrets.token_hex(32),
        "DIFY_AGENT_SERVER_SECRET_KEY": secrets.token_urlsafe(32),
        "SANDBOX_API_KEY": code_key,
        "CODE_EXECUTION_API_KEY": code_key,
        "WEAVIATE_API_KEY": vector_key,
        "WEAVIATE_AUTHENTICATION_APIKEY_ALLOWED_KEYS": vector_key,
        "WEAVIATE_AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED": "false",
    }
    files = {
        DOCKER_DIR / "envs/core-services/web.env": "# Web listener only.\nHOSTNAME=0.0.0.0\n",
        DOCKER_DIR / ".env": (
            "# Generated by deploy.py for a NEW server; keep this file private.\n"
            "# Empty CONSOLE_API_URL / APP_API_URL deliberately use the browser origin.\n"
            + "".join(f"{key}={value}\n" for key, value in values.items())
        ),
    }
    created = []
    try:
        for path, content in files.items():
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(descriptor, "w") as target:
                target.write(content)
    except OSError:
        for path in reversed(created):
            path.unlink()
        raise
    print(f"已生成 .env 和 envs/core-services/web.env（权限 600），访问地址：{origin}")


def configuration() -> dict:
    if not (DOCKER_DIR / ".env").is_file():
        raise DeploymentError("缺少 .env，请先运行 init 或 deploy。")
    # Never print the rendered model: it includes deployment secrets.
    config = json.loads(compose("config", "--format", "json").stdout)
    if config["name"] != PROJECT:
        raise DeploymentError("本脚本用于 COMPOSE_PROJECT_NAME=dify 的部署，请核对 .env。")
    print("Compose 配置解析通过。")
    return config


def start(config: dict, wait_timeout: int) -> None:
    check_engine()
    directories = docker(
        "ps", "--all", "--filter", f"label=com.docker.compose.project={PROJECT}",
        "--format", '{{.Label "com.docker.compose.project.working_dir"}}',
    ).stdout.splitlines()
    if any(not directory or Path(directory).resolve() != DOCKER_DIR for directory in directories):
        raise DeploymentError("发现其他目录启动的 dify 容器，请先核对现有部署及其数据路径。")
    # Inspect first so even mutable tags such as latest keep the local image on retry.
    for image in sorted({service["image"] for service in config["services"].values()}):
        if docker("image", "inspect", "--format", "{{.Id}}", image, check=False).returncode:
            print(f"拉取缺失镜像：{image}", flush=True)
            docker("pull", image, capture=False)
    print("启动服务并等待运行状态／已有健康检查……", flush=True)
    compose(
        "up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", str(wait_timeout),
        capture=False,
    )
    compose("ps", "--all", capture=False)
    origin = config["services"]["api"]["environment"].get("CONSOLE_WEB_URL", "")
    print(f"服务启动检查通过。首次部署请打开 {origin}/install 创建管理员账号。")


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("必须为正整数")
    return number


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("init", "check", "up", "deploy"),
        help="init 只配置；check 只校验；up 启动；deploy 初始化并启动",
    )
    parser.add_argument("--host", help="客户端访问的服务器 IP，不带协议或端口")
    parser.add_argument("--port", type=positive_int, help="对外 HTTP 端口，首次部署默认 80")
    parser.add_argument("--wait-timeout", type=positive_int, default=600, help="启动等待秒数，默认 600")
    args = parser.parse_args()
    if args.action in ("init", "deploy"):
        if not args.host or (args.port and args.port > 65535):
            parser.error("init / deploy 需要 --host，--port 范围为 1–65535")
    elif args.host or args.port:
        parser.error("check / up 读取已有 .env；修改 IP 或端口请先编辑配置文件")
    try:
        check_compose_version()
        if args.action in ("init", "deploy"):
            initialize(args.host, args.port or 80)
        config = configuration()
        if args.action in ("up", "deploy"):
            start(config, args.wait_timeout)
        else:
            print("未拉取镜像、未启动容器。准备好后运行：python3 deploy.py up")
        return 0
    except (DeploymentError, OSError, ValueError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            print(f"Docker 命令失败（退出码 {error.returncode}）；未输出可能包含密钥的诊断内容。", file=sys.stderr)
        else:
            print(f"部署未完成：{error}", file=sys.stderr)
        print("保留已有配置和数据。参见 SERVER_DEPLOYMENT.md 的排障与重试说明。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
