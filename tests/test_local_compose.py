from pathlib import Path
import re
import subprocess
import tempfile

from django.conf import settings
from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[1]


class LocalComposeContractTests(SimpleTestCase):
    databases = set()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.compose = (ROOT / "docker-compose.yml").read_text()
        cls.host_db_override = (ROOT / "docker-compose.host-db.yml").read_text()
        cls.private_override = (ROOT / "docker-compose.private.yml").read_text()
        cls.makefile = (ROOT / "Makefile").read_text()
        cls.postgres = cls.compose.split("  postgres:\n", 1)[1].split(
            "  backend:\n", 1
        )[0]
        cls.backend = cls.compose.split("  backend:\n", 1)[1].split(
            "  frontend:\n", 1
        )[0]
        cls.frontend = cls.compose.split("  frontend:\n", 1)[1].split(
            "\nvolumes:\n", 1
        )[0]

    def test_all_host_publications_are_explicit_numeric_ipv4_loopback(self):
        publications = re.findall(
            r'^\s+- "([^"\n]+:[0-9]+:[0-9]+)"$', self.compose, re.MULTILINE
        )
        self.assertEqual(
            sorted(publications),
            ["127.0.0.1:5173:5173"],
        )
        self.assertTrue(all(value.startswith("127.0.0.1:") for value in publications))
        self.assertNotIn('"0.0.0.0:', self.compose)
        self.assertNotIn('":::', self.compose)

    def test_postgres_host_access_requires_the_explicit_loopback_override(self):
        self.assertNotIn("127.0.0.1:5432:5432", self.compose)
        self.assertIn('"127.0.0.1:5432:5432"', self.host_db_override)
        self.assertNotIn('"0.0.0.0:', self.host_db_override)
        self.assertNotIn('":::', self.host_db_override)

    def test_backend_is_unpublished_and_uses_only_validated_bootstrap(self):
        self.assertNotIn("\n    ports:\n", self.backend)
        self.assertIn("python manage.py runlocal --host 0.0.0.0 --port 8000", self.backend)
        self.assertIn("--trusted-container-network", self.backend)
        self.assertNotIn("--enable-classification-writes", self.backend)
        self.assertNotIn("--classification-write-origin", self.backend)
        self.assertNotIn("--enable-financial-imports", self.backend)
        self.assertNotIn("--financial-import-origin", self.backend)
        self.assertNotRegex(self.backend, r"manage\.py runserver")

    def test_frontend_proxies_to_only_the_literal_compose_backend(self):
        self.assertIn(
            "GOUDA_VITE_API_PROXY_TARGET: http://backend:8000", self.frontend
        )
        vite_config = (ROOT / "frontend" / "vite.config.ts").read_text()
        self.assertIn('API_PROXY_PATH = "/api"', vite_config)
        self.assertIn('CONTAINER_API_PROXY_TARGET = "http://backend:8000"', vite_config)
        self.assertNotIn("cors: true", vite_config)
        self.assertIn("cors: false", vite_config)
        self.assertIn("changeOrigin: false", vite_config)

    def test_application_network_is_internal_and_service_networks_are_scoped(self):
        self.assertRegex(
            self.compose,
            r"networks:\n  edge:\n  application:\n    internal: true\n  data:\n",
        )
        self.assertIn("- application\n      - data", self.backend)
        self.assertIn("- edge\n      - application", self.frontend)
        self.assertNotIn("- application", self.postgres)
        self.assertNotIn("- edge", self.backend)
        self.assertNotIn("- data", self.frontend)

    def test_backend_settings_do_not_enable_broad_cors_or_permissive_hosts(self):
        self.assertFalse(any("cors" in item.lower() for item in settings.INSTALLED_APPS))
        self.assertNotIn("*", settings.ALLOWED_HOSTS)
        requirements = (ROOT / "requirements.txt").read_text().lower()
        self.assertNotIn("django-cors", requirements)

    def test_images_and_dependency_installers_are_version_pinned(self):
        self.assertIn("image: postgres:16.15-alpine3.24", self.compose)
        self.assertIn("FROM python:3.12.14-slim-bookworm", (ROOT / "Dockerfile").read_text())
        frontend_dockerfile = (ROOT / "frontend" / "Dockerfile").read_text()
        self.assertIn("FROM node:22.23.2-alpine3.23", frontend_dockerfile)
        self.assertIn("RUN npm ci", frontend_dockerfile)
        requirements = (ROOT / "requirements.txt").read_text().splitlines()
        self.assertTrue(all("==" in line for line in requirements if line))

    def test_compose_requires_explicit_local_secrets(self):
        self.assertIn("${DJANGO_SECRET_KEY:?Set DJANGO_SECRET_KEY in .env}", self.compose)
        self.assertIn("${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}", self.compose)

    def test_make_demo_uses_a_fixed_isolated_project_and_health_wait(self):
        self.assertIn("-p gouda-demo", self.makefile)
        self.assertIn("up --build --detach --force-recreate", self.makefile)
        self.assertIn("--wait --wait-timeout 180", self.makefile)
        self.assertIn("exec -T backend python manage.py seed_demo", self.makefile)
        self.assertIn("http://127.0.0.1:5173/", self.makefile)

    def test_make_teardown_preserves_data_and_reset_names_only_demo_volume(self):
        down_recipe = self.makefile.split("\ndown:\n", 1)[1].split("\nstatus:\n", 1)[0]
        reset_recipe = self.makefile.split("\ndemo-reset:\n", 1)[1]
        self.assertIn("down --remove-orphans", down_recipe)
        self.assertNotIn("--volumes", down_recipe)
        self.assertNotIn("down -v", down_recipe)
        self.assertIn("docker volume rm gouda-demo_gouda-postgres-data", reset_recipe)
        self.assertNotIn("gouda_gouda-postgres-data", reset_recipe)
        self.assertNotRegex(reset_recipe, r"docker volume rm .*\$[{(]")

    def test_private_stack_is_fixed_separate_and_has_no_seed_or_reset(self):
        self.assertIn("-p gouda-private", self.makefile)
        self.assertIn("-f \"$(CURDIR)/docker-compose.private.yml\"", self.makefile)
        self.assertIn("POSTGRES_DB: gouda_private", self.private_override)
        self.assertIn("gouda-private-postgres-data:/var/lib/postgresql/data", self.private_override)
        self.assertIn("--enable-financial-imports", self.private_override)
        self.assertIn(
            "--financial-import-origin http://127.0.0.1:5173",
            self.private_override,
        )
        self.assertNotIn("seed_demo", self.private_override)
        private_recipe = self.makefile.split("\nprivate: private-check\n", 1)[1].split(
            "\nprivate-down:\n", 1
        )[0]
        self.assertNotIn("seed_demo", private_recipe)
        private_down = self.makefile.split("\nprivate-down:\n", 1)[1].split(
            "\ndown:\n", 1
        )[0]
        self.assertNotIn("--volumes", private_down)
        self.assertNotIn("volume rm", private_down)
        reset_recipe = self.makefile.split("\ndemo-reset:\n", 1)[1]
        self.assertNotIn("gouda-private", reset_recipe)

    def test_environment_check_rejects_missing_and_blank_values_without_leaks(self):
        checker = ROOT / "scripts" / "check-local-env.sh"
        cases = (
            ("POSTGRES_PASSWORD=synthetic-password\n", "DJANGO_SECRET_KEY"),
            (
                "DJANGO_SECRET_KEY=synthetic-secret\nPOSTGRES_PASSWORD=\n",
                "POSTGRES_PASSWORD",
            ),
            (
                'DJANGO_SECRET_KEY=""\nPOSTGRES_PASSWORD=synthetic-password\n',
                "DJANGO_SECRET_KEY",
            ),
        )
        for contents, expected_name in cases:
            with self.subTest(expected_name=expected_name), tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8"
            ) as env_file:
                env_file.write(contents)
                env_file.flush()
                result = subprocess.run(
                    ["/bin/sh", checker, env_file.name],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected_name, result.stderr)
                self.assertNotIn("synthetic-secret", result.stdout + result.stderr)
                self.assertNotIn("synthetic-password", result.stdout + result.stderr)

    def test_environment_check_accepts_required_nonempty_values(self):
        checker = ROOT / "scripts" / "check-local-env.sh"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as env_file:
            env_file.write(
                "DJANGO_SECRET_KEY=synthetic-secret\n"
                "POSTGRES_PASSWORD=synthetic-password\n"
            )
            env_file.flush()
            result = subprocess.run(
                ["/bin/sh", checker, env_file.name],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("synthetic-secret", result.stdout + result.stderr)
        self.assertNotIn("synthetic-password", result.stdout + result.stderr)
