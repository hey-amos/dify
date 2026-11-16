"""Validate server setup in temporary directories; never start containers."""

import base64
import contextlib
import importlib.util
import io
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

DOCKER_DIR = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("server_deploy", DOCKER_DIR / "deploy.py")
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class ServerDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dify-server-deploy-")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        shutil.copyfile(DOCKER_DIR / "docker-compose.yaml", self.project / "docker-compose.yaml")
        for source in (DOCKER_DIR / "envs").rglob("*.defaults"):
            target = self.project / source.relative_to(DOCKER_DIR)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        self.directory_patch = patch.object(deploy, "DOCKER_DIR", self.project)
        self.directory_patch.start()
        self.addCleanup(self.directory_patch.stop)
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    @staticmethod
    def empty_engine(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, "linux\n" if args[0] == "info" else "", "")

    def initialize(self, host="192.0.2.10", port=8080):
        with patch.object(deploy, "docker", self.empty_engine):
            deploy.initialize(host, port)

    def test_real_compose_receives_urls_secrets_and_bindings(self):
        self.initialize()
        original = (self.project / ".env").read_bytes()
        # Simulate unrelated values exported by the invoking shell.
        shell_overrides = {"COMPOSE_PROJECT_NAME": "other", "COMPOSE_PROFILES": "mysql", "DB_PASSWORD": "wrong"}
        with patch.dict(os.environ, shell_overrides):
            services = deploy.configuration()["services"]
        self.assertEqual((self.project / ".env").read_bytes(), original)
        api = services["api"]["environment"]
        web = services["web"]["environment"]
        self.assertEqual(api["CONSOLE_API_URL"], "")
        self.assertEqual(api["CONSOLE_WEB_URL"], "http://192.0.2.10:8080")
        self.assertEqual(api["FILES_URL"], api["CONSOLE_WEB_URL"])
        self.assertEqual(web["NEXT_PUBLIC_SOCKET_URL"], "ws://192.0.2.10:8080")
        self.assertEqual(web["HOSTNAME"], "0.0.0.0")
        self.assertNotIn("HOSTNAME", api)
        postgres = services["db_postgres"]["environment"]
        redis = services["redis"]["environment"]
        plugin = services["plugin_daemon"]["environment"]
        agent = services["agent_backend"]["environment"]
        for name in ("api", "api_websocket", "worker", "worker_beat", "plugin_daemon"):
            values = services[name]["environment"]
            self.assertEqual(values["DB_PASSWORD"], postgres["POSTGRES_PASSWORD"])
            self.assertEqual(values["REDIS_PASSWORD"], redis["REDIS_PASSWORD"])
        self.assertIn(redis["REDIS_PASSWORD"], api["CELERY_BROKER_URL"])
        self.assertIn(redis["REDIS_PASSWORD"], agent["DIFY_AGENT_REDIS_URL"])
        self.assertEqual(api["PLUGIN_DAEMON_KEY"], plugin["SERVER_KEY"])
        self.assertEqual(agent["DIFY_AGENT_PLUGIN_DAEMON_API_KEY"], plugin["SERVER_KEY"])
        self.assertEqual(api["PLUGIN_DIFY_INNER_API_KEY"], plugin["DIFY_INNER_API_KEY"])
        self.assertEqual(agent["DIFY_AGENT_INNER_API_KEY"], plugin["DIFY_INNER_API_KEY"])
        self.assertEqual(api["CODE_EXECUTION_API_KEY"], services["sandbox"]["environment"]["API_KEY"])
        self.assertEqual(
            agent["DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN"],
            services["local_sandbox"]["environment"]["SHELLCTL_AUTH_TOKEN"],
        )
        self.assertEqual(len(base64.urlsafe_b64decode(agent["DIFY_AGENT_SERVER_SECRET_KEY"] + "=")), 32)
        weaviate = services["weaviate"]["environment"]
        self.assertEqual(api["WEAVIATE_API_KEY"], weaviate["AUTHENTICATION_APIKEY_ALLOWED_KEYS"])
        self.assertEqual(weaviate["AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED"], "false")
        self.assertEqual(len(postgres["POSTGRES_PASSWORD"]), 64)
        self.assertNotEqual(postgres["POSTGRES_PASSWORD"], redis["REDIS_PASSWORD"])
        self.assertEqual(services["plugin_daemon"]["ports"][0]["host_ip"], "127.0.0.1")
        http, https = services["nginx"]["ports"]
        self.assertEqual(http["published"], "8080")
        self.assertEqual((https["host_ip"], https["published"]), ("127.0.0.1", "0"))
        self.assertEqual(
            services["plugin_daemon"]["depends_on"]["init_permissions"]["condition"],
            "service_completed_successfully",
        )
        for name in (".env", "envs/core-services/web.env"):
            self.assertEqual(stat.S_IMODE((self.project / name).stat().st_mode), 0o600)

    def test_second_init_preserves_files_and_secrets(self):
        self.initialize()
        before = {path: path.read_bytes() for path in self.project.rglob("*.env")}
        with self.assertRaises(deploy.DeploymentError):
            self.initialize(host="192.0.2.20", port=80)
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_existing_service_env_is_preserved(self):
        path = self.project / "envs/core-services/web.env"
        path.write_text("HOSTNAME=existing\n")
        with self.assertRaises(deploy.DeploymentError):
            self.initialize()
        self.assertEqual(path.read_text(), "HOSTNAME=existing\n")
        self.assertFalse((self.project / ".env").exists())

    def test_existing_database_is_preserved_without_env(self):
        path = self.project / "volumes/db/data/PG_VERSION"
        path.parent.mkdir(parents=True)
        path.write_text("15")
        with self.assertRaises(deploy.DeploymentError):
            self.initialize()
        self.assertEqual(path.read_text(), "15")
        self.assertFalse((self.project / ".env").exists())

    def test_existing_docker_resources_block_initialization(self):
        for resource in ("ps", "volume"):
            with self.subTest(resource=resource):
                def occupied(*args, **kwargs):
                    if args[0] == resource:
                        return subprocess.CompletedProcess(args, 0, "existing-resource\n", "")
                    return self.empty_engine(*args, **kwargs)
                with patch.object(deploy, "docker", occupied), self.assertRaises(deploy.DeploymentError):
                    deploy.initialize("192.0.2.10", 80)
                self.assertFalse((self.project / ".env").exists())

    def test_unlabelled_sandbox_volume_blocks_initialization(self):
        def engine(*args, **kwargs):
            if args[:2] == ("volume", "ls") and args[-1].startswith("name="):
                return subprocess.CompletedProcess(args, 0, "dify_dify_agent_local_sandbox_home\n", "")
            return self.empty_engine(*args, **kwargs)
        with patch.object(deploy, "docker", engine), self.assertRaises(deploy.DeploymentError):
            deploy.initialize("192.0.2.10", 8080)
        self.assertFalse((self.project / ".env").exists())

    def test_http_port_cannot_conflict_with_plugin_debug_port(self):
        with self.assertRaises(deploy.DeploymentError):
            self.initialize(port=5003)
        self.assertFalse((self.project / ".env").exists())

    def test_invalid_host_never_creates_config(self):
        for host in (
            "http://192.0.2.10", "192.0.2.10\nDB_PASSWORD=x", "0.0.0.0",
            "fe80::1%eth0", "fe80::1%eth0\nCOMPOSE_PROFILES=other",
        ):
            with self.subTest(host=host), self.assertRaises((ValueError, deploy.DeploymentError)):
                self.initialize(host=host)
        self.assertFalse((self.project / ".env").exists())

    def test_ipv6_and_default_http_port(self):
        self.initialize(host="2001:db8::10", port=80)
        services = deploy.configuration()["services"]
        self.assertEqual(services["api"]["environment"]["CONSOLE_WEB_URL"], "http://[2001:db8::10]")
        self.assertEqual(services["web"]["environment"]["NEXT_PUBLIC_SOCKET_URL"], "ws://[2001:db8::10]")

    def test_old_compose_rejected(self):
        for version, accepted in (("2.34.0", False), ("v2.35.0", True), ("5.5.0", True)):
            with patch.object(deploy, "docker", return_value=subprocess.CompletedProcess([], 0, version, "")):
                if accepted:
                    deploy.check_compose_version()
                else:
                    with self.assertRaises(deploy.DeploymentError):
                        deploy.check_compose_version()

    def test_up_only_pulls_missing_images_and_uses_saved_config(self):
        calls = []
        def engine(*args, **kwargs):
            calls.append(args)
            if args[:2] == ("image", "inspect"):
                return subprocess.CompletedProcess(args, int(args[-1] == "missing:1"), "", "")
            return self.empty_engine(*args, **kwargs)
        config = {"services": {
            "api": {"image": "cached:latest", "environment": {"CONSOLE_WEB_URL": "http://192.0.2.10"}},
            "web": {"image": "missing:1"},
        }}
        with patch.object(deploy, "docker", engine), patch.object(deploy, "compose") as compose:
            deploy.start(config, 600)
        self.assertEqual([call for call in calls if call[0] == "pull"], [("pull", "missing:1")])
        self.assertEqual(
            compose.call_args_list[0].args,
            ("up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "600"),
        )
        self.assertFalse((self.project / ".env").exists())

    def test_pull_failure_never_starts_containers(self):
        def engine(*args, **kwargs):
            if args[0] == "pull":
                raise subprocess.CalledProcessError(1, ["docker", *args])
            if args[:2] == ("image", "inspect"):
                return subprocess.CompletedProcess(args, 1, "", "")
            return self.empty_engine(*args, **kwargs)
        with patch.object(deploy, "docker", engine), patch.object(deploy, "compose") as compose:
            with self.assertRaises(subprocess.CalledProcessError):
                deploy.start({"services": {"api": {"image": "unavailable:1"}}}, 600)
        compose.assert_not_called()

    def test_same_project_from_another_directory_is_not_recreated(self):
        def engine(*args, **kwargs):
            if args[0] == "ps":
                return subprocess.CompletedProcess(args, 0, "/another/deployment\n", "")
            return self.empty_engine(*args, **kwargs)
        with patch.object(deploy, "docker", engine), patch.object(deploy, "compose") as compose:
            with self.assertRaises(deploy.DeploymentError):
                deploy.start({"services": {}}, 600)
        compose.assert_not_called()


if __name__ == "__main__":
    unittest.main()
