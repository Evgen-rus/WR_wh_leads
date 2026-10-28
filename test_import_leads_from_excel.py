import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from import_leads_from_excel import build_payload, read_payloads


class ExcelImportTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "id": 123,
            "Domain": "example.com",
            "Phone": 79990000000,
            "Created": "2026/10/28 16:38:08",
            "Referer": "https://example.com/page?utm_term=hello+world&yclid=123&empty=",
        }
        self.tz = ZoneInfo("Europe/Moscow")

    def test_webhook_mapping(self):
        payload = build_payload(self.row, self.tz)
        self.assertEqual(payload["vid"], "123")
        self.assertNotIn("uuid", payload)
        self.assertNotIn("ref", payload)
        self.assertEqual(payload["phones"], ["79990000000"])
        self.assertEqual(payload["utm"], {"utm_term": "hello world", "yclid": "123", "empty": ""})
        self.assertEqual(datetime.fromtimestamp(int(payload["time"]), timezone.utc),
                         datetime(2026, 10, 28, 13, 38, 8, tzinfo=timezone.utc))

    def workbook(self, rows):
        workbook = MagicMock()
        workbook.worksheets = [workbook.active]
        workbook.active.iter_rows.return_value = iter(rows)
        return workbook

    def test_repeated_id_merges_phones(self):
        other = {**self.row, "Phone": 79990000001}
        workbook = self.workbook([tuple(self.row), tuple(self.row.values()), tuple(other.values())])
        with patch("import_leads_from_excel.load_workbook", return_value=workbook):
            payloads, count = read_payloads(Path("unused.xlsx"), self.tz)
        self.assertEqual(count, 2)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["phones"], ["79990000000", "79990000001"])
        workbook.close.assert_called_once()

    def test_conflicting_duplicate_stops_validation(self):
        other = {**self.row, "Created": "2026/10/28 17:00:00"}
        workbook = self.workbook([tuple(self.row), tuple(self.row.values()), tuple(other.values())])
        with patch("import_leads_from_excel.load_workbook", return_value=workbook):
            with self.assertRaisesRegex(ValueError, "Conflicting time"):
                read_payloads(Path("unused.xlsx"), self.tz)
        workbook.close.assert_called_once()

    def test_bad_phone_or_page_rejected(self):
        for change in ({"Phone": None}, {"Referer": "https://other.example/"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                build_payload({**self.row, **change}, self.tz)


if __name__ == "__main__":
    unittest.main()
