import unittest

import pytest

pytest.importorskip("PySide6")

from core.segnalazioni import Segnalazione
from qt_app.segnalazioni import SegnalazioniPage


class TestSegnalazioniWorkflow(unittest.TestCase):
    def test_qt_workflow_state_exposes_next_action(self):
        page = SegnalazioniPage.__new__(SegnalazioniPage)
        seg = Segnalazione(
            numero_progressivo=987654,
            anno="2026",
            mese="05",
            giorno="05",
            ora="10:00",
            stato="in_corso",
        )

        state = page.workflow_state(seg)

        self.assertEqual(state["total"], 9)
        self.assertEqual(state["next_step"]["action"], "edit_report")
        self.assertIn("steps", state)


if __name__ == "__main__":
    unittest.main()
