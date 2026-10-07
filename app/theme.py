"""Theme sombre premium (QSS) applique a toute l'app.

Palette calee sur l'identite Olympe : navy profond + accent cyan.
"""

QSS = """
* { font-family: 'Segoe UI', 'Inter', sans-serif; }

QWidget {
    background: #0f1623;
    color: #e6edf6;
    font-size: 13px;
}

QLabel { color: #aebccf; background: transparent; }
QLabel#titre { color: #ffffff; font-size: 17px; font-weight: 600; }
QLabel#sous  { color: #7d8ca1; font-size: 11px; }
QLabel#statut { color: #6f7f95; font-size: 11px; }
QLabel#section { color: #8fa0b6; font-size: 11px; font-weight: 600;
                 text-transform: uppercase; letter-spacing: 1px; }

QPlainTextEdit, QLineEdit {
    background: #161f2e;
    border: 1px solid #27374f;
    border-radius: 12px;
    padding: 10px 12px;
    color: #e9eff7;
    selection-background-color: #33c5f4;
    selection-color: #04222e;
}
QPlainTextEdit:focus, QLineEdit:focus { border: 1px solid #33c5f4; }
QLineEdit::placeholder, QPlainTextEdit::placeholder { color: #5e6d84; }

QPushButton {
    background: #1e2a3d;
    border: 1px solid #2c3d58;
    border-radius: 11px;
    padding: 9px 16px;
    color: #e6edf6;
    font-weight: 500;
}
QPushButton:hover { background: #26354c; border-color: #3b5078; }
QPushButton:pressed { background: #18222f; }

/* Action principale (dicter / inserer) */
QPushButton#primaire {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #33c5f4, stop:1 #2e9fce);
    border: none; color: #04222e; font-weight: 700;
}
QPushButton#primaire:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #49cef7, stop:1 #38a9d7);
}
QPushButton#primaire:pressed { background: #2a8fbb; }

/* Etat enregistrement */
QPushButton#rec { background: #e5484d; border: none; color: #ffffff; font-weight: 700; }
QPushButton#rec:hover { background: #ef5a5f; }

QMenu { background: #161f2e; border: 1px solid #27374f; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 8px 22px; border-radius: 6px; color: #e6edf6; }
QMenu::item:selected { background: #26354c; }
QMenu::separator { height: 1px; background: #27374f; margin: 6px 4px; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #2c3d58; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #3b5078; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }

QDialog { background: #0f1623; }
QComboBox {
    background: #161f2e; border: 1px solid #27374f; border-radius: 10px;
    padding: 7px 10px; color: #e9eff7;
}
QComboBox:focus { border: 1px solid #33c5f4; }
QComboBox QAbstractItemView {
    background: #161f2e; border: 1px solid #27374f; selection-background-color: #26354c;
    color: #e6edf6; outline: none;
}
QCheckBox { color: #c3d0e0; spacing: 8px; }
QProgressDialog { background: #0f1623; }
QProgressBar { border: 1px solid #27374f; border-radius: 8px; background: #161f2e; text-align: center; color:#cfe; }
QProgressBar::chunk { background: #33c5f4; border-radius: 7px; }
"""
