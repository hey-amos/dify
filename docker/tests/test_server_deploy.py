"""Test configuration completion in temporary directories; never start containers."""

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

DOCKER_DIR = Path(__file__).resolve().parents[1]
BASH = os.environ.get("DIFY_DEPLOY_TEST_BASH", shutil.which("bash"))
DOCKER = shutil.which("docker")


@unittest.skipUnless(BASH and DOCKER, "Bash and Docker Compose are required")
class ServerDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dify deploy-")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        for name in ("docker-compose.yaml", "deploy.sh"):
            shutil.copyfile(DOCKER_DIR / name, self.project / name)
        for source in (DOCKER_DIR / "envs").rglob("*.defaults"):
            target = self.project / source.relative_to(DOCKER_DIR)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        self.bin = self.project / "bin"
        self.bin.mkdir()
        self.log = self.project / "docker-calls"
        self.command("docker", '''#!/bin/sh
printf '%s\\n' "$*" >> "$DEPLOY_TEST_LOG"
[ "$*" = 'compose up -d' ] || exit 97
exit "${DEPLOY_TEST_EXIT:-0}"
''')
        for name in ("python", "python3", "jq", "openssl"):
            self.command(name, '#!/bin/sh\nexit 99\n')
        self.env = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "DEPLOY_TEST_LOG": str(self.log),
        }

    def command(self, name, content):
        path = self.bin / name
        path.write_text(content)
        path.chmod(0o755)

    def run_deploy(self, *args, expected=0, **environment):
        result = subprocess.run(
            [BASH, str(self.project / "deploy.sh"), *args],
            cwd=self.project.parent, env={**self.env, **environment},
            text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def configuration(self):
        # Only the developer test invokes the real CLI, for parsing without a daemon.
        result = subprocess.run(
            [DOCKER, "compose", "config", "--format", "json"],
            cwd=self.project, env=self.env, text=True, capture_output=True, check=True,
        )
        return json.loads(result.stdout)

    def saved_files(self):
        return {path: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
                for path in self.project.rglob("*.env")}

    def test_fresh_checkout_fills_required_configuration_and_starts_compose(self):
        result = self.run_deploy("--host", "192.0.2.10", "--port", "8080")
        config = self.configuration()
        services = config["services"]
        api = services["api"]["environment"]
        web = services["web"]["environment"]
        agent = services["agent_backend"]["environment"]
        self.assertEqual(config["name"], "dify")
        self.assertEqual(api["CONSOLE_API_URL"], "")
        for key in ("CONSOLE_WEB_URL", "SERVICE_API_URL", "APP_WEB_URL", "FILES_URL", "TRIGGER_URL"):
            self.assertEqual(api[key], "http://192.0.2.10:8080")
        self.assertEqual(api["INTERNAL_FILES_URL"], "http://api:5001")
        self.assertEqual(web["APP_API_URL"], "")
        self.assertEqual(web["NEXT_PUBLIC_SOCKET_URL"], "/")
        self.assertEqual(web["HOSTNAME"], "0.0.0.0")
        self.assertNotIn("HOSTNAME", api)
        self.assertEqual(services["nginx"]["ports"][0]["published"], "8080")
        token = agent["DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN"]
        self.assertRegex(token, r"^[0-9a-f]{64}$")
        self.assertEqual(token, services["local_sandbox"]["environment"]["SHELLCTL_AUTH_TOKEN"])
        self.assertNotIn(token, result.stdout + result.stderr)
        for _, mode in self.saved_files().values():
            self.assertEqual(mode, 0o600)
        self.assertNotIn("DB_PASSWORD=", (self.project / ".env").read_text())
        self.assertEqual(self.log.read_text(), "compose up -d\n")

    def test_repeated_run_preserves_all_values_permissions_and_token(self):
        self.run_deploy("--host", "192.0.2.10", "--port", "8080")
        (self.project / ".env").chmod(0o640)
        before = self.saved_files()
        self.run_deploy("--host", "192.0.2.20", "--port", "9090")
        self.assertEqual(before, self.saved_files())
        self.assertEqual(self.log.read_text(), "compose up -d\n" * 2)

    def test_partial_files_keep_existing_settings_and_only_append_missing_keys(self):
        original = (
            "# Existing deployment\nCOMPOSE_PROJECT_NAME=custom-dify\n"
            "EXPOSE_NGINX_PORT=18080\nexport CONSOLE_WEB_URL = 'https://dify.example.com'\n"
            "SERVICE_API_URL=\nDB_PASSWORD=existing-password\n"
            "DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN=existing-token"
        )
        env = self.project / ".env"
        env.write_text(original)
        web = self.project / "envs/core-services/web.env"
        web.write_text("HOSTNAME=existing-host\n# keep this comment\n")
        self.run_deploy("--host", "192.0.2.10", "--port", "8080")
        self.assertTrue(env.read_text().startswith(original + "\n"))
        self.assertEqual(web.read_text(), "HOSTNAME=existing-host\n# keep this comment\n")
        config = self.configuration()
        api = config["services"]["api"]["environment"]
        self.assertEqual(config["name"], "custom-dify")
        self.assertEqual(api["SERVICE_API_URL"], "")
        self.assertEqual(api["FILES_URL"], "https://dify.example.com")
        self.assertEqual(api["DB_PASSWORD"], "existing-password")
        self.assertEqual(config["services"]["nginx"]["ports"][0]["published"], "18080")
        self.assertEqual(env.read_text().count("DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN="), 1)

    def test_new_urls_use_existing_port_and_web_file_is_completed(self):
        (self.project / ".env").write_text("EXPOSE_NGINX_PORT=18080\n")
        web = self.project / "envs/core-services/web.env"
        web.write_text("ALLOW_EMBED=true")
        self.run_deploy("--host", "192.0.2.10")
        config = self.configuration()
        self.assertEqual(config["services"]["api"]["environment"]["CONSOLE_WEB_URL"], "http://192.0.2.10:18080")
        self.assertEqual(web.read_text(), "ALLOW_EMBED=true\nHOSTNAME=0.0.0.0\n")

    def test_existing_data_does_not_block_start_and_is_not_modified(self):
        data = self.project / "volumes/db/data/PG_VERSION"
        data.parent.mkdir(parents=True)
        data.write_text("15")
        self.run_deploy()
        self.assertEqual(data.read_text(), "15")
        self.assertEqual(self.log.read_text(), "compose up -d\n")

    def test_empty_values_remain_empty_and_env_is_not_executed(self):
        env = self.project / ".env"
        env.write_text("CONSOLE_API_URL=\nDIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN=\nCUSTOM=$(touch should-not-exist)\n")
        self.run_deploy()
        self.assertIn("DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN=\n", env.read_text())
        self.assertEqual(env.read_text().count("CONSOLE_API_URL="), 1)
        self.assertFalse((self.project / "should-not-exist").exists())

    def test_compose_failure_keeps_configuration_for_retry(self):
        self.run_deploy(expected=7, DEPLOY_TEST_EXIT="7")
        before = self.saved_files()
        self.run_deploy()
        self.assertEqual(before, self.saved_files())

    def test_bad_arguments_do_not_write_configuration_or_start_containers(self):
        for args in (("--host",), ("--host", "192.0.2.10\nDB_PASSWORD=x"), ("--port", "65536"), ("init",)):
            with self.subTest(args=args):
                self.run_deploy(*args, expected=1)
                self.assertFalse((self.project / ".env").exists())
                self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
