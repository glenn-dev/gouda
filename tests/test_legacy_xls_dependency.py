import unittest

import xlrd


class LegacyXlsDependencyTests(unittest.TestCase):
    def test_xlrd_is_pinned_to_the_supported_legacy_xls_major_version(self):
        self.assertEqual(xlrd.__version__, "2.0.1")
