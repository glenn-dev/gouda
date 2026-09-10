"""Private connections must not send statement data to PostgreSQL diagnostics."""

import json
import os
import subprocess
import sys

from django.test import SimpleTestCase


class PrivateDatabaseLoggingTests(SimpleTestCase):
    def test_private_database_disables_server_statement_and_error_logging(self):
        result = subprocess.run(
            [sys.executable, "-c", "import json; from config.settings import DATABASES; "
             "print(json.dumps(DATABASES['default'].get('OPTIONS', {})))"],
            env={**os.environ, "POSTGRES_DB": "gouda_private"},
            capture_output=True, text=True, check=True,
        )
        options = json.loads(result.stdout).get("options", "")
        for setting in (
            "log_min_messages=panic", "log_min_error_statement=panic",
            "log_statement=none", "log_duration=off", "log_min_duration_statement=-1",
            "log_min_duration_sample=-1", "log_transaction_sample_rate=0",
            "log_parameter_max_length=0", "log_parameter_max_length_on_error=0",
        ):
            self.assertIn("-c " + setting, options)
