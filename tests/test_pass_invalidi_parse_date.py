import datetime
import unittest

from pass_invalidi import parse_date


class TestParseDate(unittest.TestCase):
    def test_parse_supported_formats(self):
        self.assertEqual(parse_date("10/03/2026"), datetime.date(2026, 3, 10))
        self.assertEqual(parse_date("2026-03-10"), datetime.date(2026, 3, 10))
        self.assertEqual(parse_date("10-03-2026"), datetime.date(2026, 3, 10))
        self.assertEqual(parse_date("10.03.2026"), datetime.date(2026, 3, 10))

    def test_parse_datetime_and_date(self):
        self.assertEqual(parse_date(datetime.datetime(2026, 3, 10, 9, 30)), datetime.date(2026, 3, 10))
        self.assertEqual(parse_date(datetime.date(2026, 3, 10)), datetime.date(2026, 3, 10))

    def test_parse_invalid_values(self):
        self.assertIsNone(parse_date(None))
        self.assertIsNone(parse_date("data non valida"))
        self.assertIsNone(parse_date("31/02/2026"))


if __name__ == "__main__":
    unittest.main()
