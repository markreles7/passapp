from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.auth import AuthError, AuthenticatedUser, authenticate
from qt_app.widgets import page_header


class LoginDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.user: AuthenticatedUser | None = None
        self.setWindowTitle("Accesso PassApp")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)
        layout.addWidget(page_header("Accesso", "Inserisci username e password per entrare in PassApp."))

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QGridLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setHorizontalSpacing(12)
        card_layout.setVerticalSpacing(10)

        username_label = QLabel("Username")
        username_label.setObjectName("Muted")
        self.username_field = QLineEdit()
        self.username_field.setPlaceholderText("Username")
        self.username_field.returnPressed.connect(self._try_login)

        password_label = QLabel("Password")
        password_label.setObjectName("Muted")
        self.password_field = QLineEdit()
        self.password_field.setPlaceholderText("Password")
        self.password_field.setEchoMode(QLineEdit.Password)
        self.password_field.returnPressed.connect(self._try_login)

        card_layout.addWidget(username_label, 0, 0)
        card_layout.addWidget(self.username_field, 0, 1)
        card_layout.addWidget(password_label, 1, 0)
        card_layout.addWidget(self.password_field, 1, 1)
        layout.addWidget(card)

        login_button = QPushButton("Accedi")
        login_button.clicked.connect(self._try_login)
        layout.addWidget(login_button, alignment=Qt.AlignRight)

    def _try_login(self) -> None:
        try:
            self.user = authenticate(self.username_field.text(), self.password_field.text())
        except AuthError as exc:
            QMessageBox.warning(self, "Accesso non riuscito", str(exc))
            self.password_field.clear()
            self.password_field.setFocus()
            return

        self.accept()
