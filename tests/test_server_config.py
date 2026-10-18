import os
import unittest
from unittest.mock import patch

from scanner_service.server import _allowed_codes, _load_factory


class LocalServerConfigTests(unittest.TestCase):
    def test_allowlist_keeps_only_exact_twelve_digit_codes(self):
        with patch.dict(os.environ, {"SHINY_ATLAS_ALLOWED_CODES": "035287579185, bad,1234567890123, 000000000001"}):
            self.assertEqual(_allowed_codes(), {"035287579185", "000000000001"})

    def test_missing_factory_fails_closed(self):
        self.assertIsNone(_load_factory(""))
        self.assertIsNone(_load_factory("not-a-module-path"))


if __name__ == "__main__":
    unittest.main()
