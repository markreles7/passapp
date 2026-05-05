import unittest

from segnalazioni import Segnalazione, SegnalazioniFrame
from qt_app.segnalazioni import SegnalazioniPage


class _NotebookStub:
    def __init__(self):
        self.last_selected = None

    def select(self, value):
        self.last_selected = value


class TestSegnalazioniWorkflow(unittest.TestCase):
    def _frame_stub(self):
        frame = SegnalazioniFrame.__new__(SegnalazioniFrame)
        frame.notebook = _NotebookStub()
        frame.tab_arch = object()
        frame._save_error_notified = False
        return frame

    def test_concludi_stops_if_save_current_fails(self):
        frame = self._frame_stub()
        seg = Segnalazione(
            numero_progressivo=3,
            anno="2026",
            mese="03",
            giorno="31",
            ora="10:00",
            nominativo="Mario Rossi",
            descrizione_segnalazione="Verifica",
            ricevente="Ufficio",
            agente_verificatore="Agente Uno",
            verifica_effettuata="Esito",
            data_verifica="31/03/2026",
            stato="in_corso",
        )

        save_calls = []
        frame._get_selected = lambda: seg
        frame._save_current = lambda: False
        frame._save_to_disk = lambda: save_calls.append("saved") or True
        frame._refresh_trees = lambda: None
        frame._select_report = lambda numero, stato: None

        frame._concludi_current()

        self.assertEqual(seg.stato, "in_corso")
        self.assertEqual(save_calls, [])

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
