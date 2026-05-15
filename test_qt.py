import pytest

PySide6 = pytest.importorskip("PySide6")


def test_pyside6_imports():
    from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

    assert QApplication is not None
    assert QLabel is not None
    assert QMainWindow is not None
