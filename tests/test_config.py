"""Regression coverage for importing existing production configuration."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class ProductionConfigurationTests(unittest.TestCase):
    def load_config(self, secret):
        environment = os.environ.copy()
        environment.update(APP_ENV="production", RENDER="false",
                           DATABASE_URL="postgresql://example.invalid/test", SECRET_KEY=secret)
        config = Path(__file__).resolve().parents[1] / "backend" / "config.py"
        return subprocess.run([sys.executable, str(config)], env=environment,
                              capture_output=True, text=True, timeout=10)

    def test_existing_private_key_is_accepted_without_length_requirement(self):
        result = self.load_config("existing-private-key")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_empty_and_known_development_keys_are_rejected(self):
        for secret in ("", "smart-bus-system-dev-secret-change-me"):
            with self.subTest(secret=bool(secret)):
                result = self.load_config(secret)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Set SECRET_KEY to a private value", result.stderr)


if __name__ == "__main__":
    unittest.main()
