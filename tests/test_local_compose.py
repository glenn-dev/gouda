from pathlib import Path
import re

from django.conf import settings
from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[1]


class LocalComposeContractTests(SimpleTestCase):
    databases = set()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.compose = (ROOT / "docker-compose.yml").read_text()
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
        publications = re.findall(r'^\s+- "([^"\n]+:[0-9]+:[0-9]+)"$', self.compose, re.MULTILINE)
        self.assertEqual(
            sorted(publications),
            ["127.0.0.1:5173:5173", "127.0.0.1:5432:5432"],
        )
        self.assertTrue(all(value.startswith("127.0.0.1:") for value in publications))
        self.assertNotIn('"0.0.0.0:', self.compose)
        self.assertNotIn('":::', self.compose)

    def test_backend_is_unpublished_and_uses_only_validated_bootstrap(self):
        self.assertNotIn("\n    ports:\n", self.backend)
        self.assertIn("python manage.py runlocal --host 0.0.0.0 --port 8000", self.backend)
        self.assertIn("--trusted-container-network", self.backend)
        self.assertNotRegex(self.backend, r"manage\.py runserver")

    def test_frontend_proxies_to_only_the_literal_compose_backend(self):
        self.assertIn(
            "GOUDA_VITE_API_PROXY_TARGET: http://backend:8000", self.frontend
        )
        vite_config = (ROOT / "frontend" / "vite.config.ts").read_text()
        self.assertIn('API_PROXY_PATH = "/api"', vite_config)
        self.assertIn('CONTAINER_API_PROXY_TARGET = "http://backend:8000"', vite_config)
        self.assertNotIn("cors: true", vite_config)

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
