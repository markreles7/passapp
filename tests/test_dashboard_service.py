import unittest

from core.dashboard_service import (
    UNAVAILABLE,
    count_incomplete_ospitalita,
    summarize_priority_fields,
)


class TestDashboardService(unittest.TestCase):
    def test_summarize_priority_fields_when_missing_schema(self):
        result = summarize_priority_fields([{"stato": "in_corso"}])

        self.assertEqual(result["high_priority"], UNAVAILABLE)
        self.assertEqual(result["missing"], UNAVAILABLE)

    def test_summarize_priority_fields_counts_high_and_missing_values(self):
        items = [
            {"priorità": "Alta", "categoria": "Viabilita"},
            {"priorita": "Bassa", "categoria": ""},
            {"priorita": "", "categoria": "Ambiente"},
        ]

        result = summarize_priority_fields(items)

        self.assertEqual(result["high_priority"], "1")
        self.assertEqual(result["missing"], "2")

    def test_count_incomplete_ospitalita(self):
        records = [
            {
                "protocollo": "1",
                "data_presentazione": "01/01/2026",
                "denunciante_dichiarante": "Mario Rossi",
                "cittadino_ospitato": "John Smith",
            },
            {
                "protocollo": "2",
                "data_presentazione": "",
                "denunciante_dichiarante": "Mario Rossi",
                "cittadino_ospitato": "John Smith",
            },
            {
                "protocollo": "3",
                "data_presentazione": "01/01/2026",
                "denunciante_dichiarante": "-",
                "cittadino_ospitato": "John Smith",
            },
        ]

        self.assertEqual(count_incomplete_ospitalita(records), 2)


if __name__ == "__main__":
    unittest.main()
