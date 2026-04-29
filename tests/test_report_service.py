import unittest

from core.report_service import ReportSources, build_monthly_report


class TestReportService(unittest.TestCase):
    def test_month_without_data(self):
        report = build_monthly_report(
            4,
            2026,
            ("segnalazioni", "sopralluoghi", "ospitalita"),
            sources=ReportSources(segnalazioni=[], sopralluoghi=[], ospitalita_records=[]),
        )

        self.assertIn("REPORT MENSILE ATTIVITA", report.text)
        self.assertIn("Totale segnalazioni ricevute nel mese: 0", report.text)
        self.assertIn("Totale comunicazioni/record nel mese: dato non disponibile", report.text)

    def test_segnalazioni_with_category_and_priority(self):
        report = build_monthly_report(
            4,
            2026,
            ("segnalazioni",),
            sources=ReportSources(
                segnalazioni=[
                    {
                        "numero_progressivo": 1,
                        "anno": "2026",
                        "mese": "04",
                        "giorno": "10",
                        "stato": "in_corso",
                        "priorità": "Alta",
                        "categoria": "Viabilita",
                    },
                    {
                        "numero_progressivo": 2,
                        "anno": "2026",
                        "mese": "04",
                        "giorno": "12",
                        "stato": "archiviata",
                        "priorita": "Bassa",
                        "categoria": "",
                    },
                ]
            ),
        )

        self.assertIn("Totale segnalazioni ricevute nel mese: 2", report.text)
        self.assertIn("Urgenti/alta priorita: 1", report.text)
        self.assertIn("Suddivisione per categoria: Viabilita: 1", report.text)
        self.assertIn("Segnalazioni senza categoria: 1", report.text)

    def test_missing_optional_fields_are_reported_unavailable(self):
        report = build_monthly_report(
            4,
            2026,
            ("segnalazioni",),
            sources=ReportSources(
                segnalazioni=[
                    {
                        "numero_progressivo": 1,
                        "anno": "2026",
                        "mese": "04",
                        "giorno": "10",
                        "stato": "in_corso",
                    }
                ]
            ),
        )

        self.assertIn("Urgenti/alta priorita: dato non disponibile", report.text)
        self.assertIn("Suddivisione per categoria: dato non disponibile", report.text)

    def test_source_unavailable_keeps_report_generation(self):
        report = build_monthly_report(
            4,
            2026,
            ("pass_invalidi", "ospitalita"),
            sources=ReportSources(
                pass_records=[],
                pass_errors=["Cartella pass non raggiungibile"],
                ospitalita_records=[],
                ospitalita_errors=["Cartella ospitalita non raggiungibile"],
            ),
        )

        self.assertIn("PASS INVALIDI", report.text)
        self.assertIn("OSPITALITA STRANIERI", report.text)
        self.assertIn("Cartella pass non raggiungibile", report.text)
        self.assertIn("Cartella ospitalita non raggiungibile", report.text)


if __name__ == "__main__":
    unittest.main()
