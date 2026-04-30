import sys
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

app = QApplication(sys.argv)

window = QMainWindow()
window.setWindowTitle("PassApp Qt Test")
window.resize(1000, 700)

label = QLabel("PySide6 funziona correttamente")
label.setStyleSheet("font-size: 24px; padding: 40px;")
window.setCentralWidget(label)

window.show()
sys.exit(app.exec())