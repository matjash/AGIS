"""Dialogs for the layer catalogue: entry form, CPA login, export of the official list."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout,
)
from qgis.core import QgsSettings

from .catalogue import normalize_tags

OK_CANCEL = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel


class EntryDialog(QDialog):
    """Name, description, origin … of a catalogue entry; optionally the target catalogue."""

    def __init__(self, entry, targets=None, warnings=(), title="Vir", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.target = None
        if targets:
            self.target = QComboBox()
            for key, label in targets:
                self.target.addItem(label, key)
            form.addRow(self.tr("Shrani v:"), self.target)

        self.naziv = QLineEdit(entry.get("naziv") or "")
        self.opis = QPlainTextEdit(entry.get("opis") or "")
        self.opis.setFixedHeight(70)
        self.izvor = QLineEdit(entry.get("izvor") or "")
        self.izvor.setPlaceholderText(self.tr("npr. GURS, ZVKDS, ARSO"))
        self.oznake = QLineEdit(entry.get("oznake") or "")
        self.oznake.setPlaceholderText(self.tr("ključne besede za iskanje, npr. lidar relief DMR"))
        self.oznake.setToolTip(self.tr("Ločite jih s presledkom ali vejico."))
        self.vrstni_red = QSpinBox()
        self.vrstni_red.setRange(-9999, 9999)
        self.vrstni_red.setValue(int(entry.get("vrstni_red") or 0))

        form.addRow(self.tr("Naziv:"), self.naziv)
        form.addRow(self.tr("Opis:"), self.opis)
        form.addRow(self.tr("Izvor podatkov:"), self.izvor)
        form.addRow(self.tr("Oznake:"), self.oznake)
        form.addRow(self.tr("Vrstni red:"), self.vrstni_red)
        layout.addLayout(form)

        if warnings:
            box = QLabel("<b>" + self.tr("Opozorila") + "</b><br>" + "<br>".join("• " + w for w in warnings))
            box.setWordWrap(True)
            box.setStyleSheet("color: #e65100;")
            layout.addWidget(box)

        self.buttons = QDialogButtonBox(OK_CANCEL)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.naziv.textChanged.connect(self._check)
        self._check()

    def _check(self):
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.naziv.text().strip()))

    def values(self):
        return {
            "naziv": self.naziv.text().strip(),
            "opis": self.opis.toPlainText().strip() or None,
            "izvor": self.izvor.text().strip() or None,
            "oznake": normalize_tags(self.oznake.text()),
            "vrstni_red": self.vrstni_red.value(),
        }

    def target_key(self):
        return self.target.currentData() if self.target else None


class LoginDialog(QDialog):
    """Curator login for the CPA catalogue. The password is kept only for this QGIS session."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Prijava v bazo CPA"))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr("Za urejanje kataloga CPA se prijavite z\nsvojim uporabniškim imenom za bazo CPA.")))
        form = QFormLayout()
        self.user = QLineEdit(QgsSettings().value("agis/cpa_last_user", ""))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(self.tr("Uporabnik:"), self.user)
        form.addRow(self.tr("Geslo:"), self.password)
        layout.addLayout(form)
        self.error = QLabel()
        self.error.setStyleSheet("color: #c62828;")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(OK_CANCEL)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if self.user.text():
            self.password.setFocus()

    def show_error(self, text):
        self.error.setText(text)
        self.error.show()

    def credentials(self):
        QgsSettings().setValue("agis/cpa_last_user", self.user.text().strip())
        return self.user.text().strip(), self.password.text()


class ExportDialog(QDialog):
    """Pick entries for a new official catalogue file."""

    TITLES = {"cpa": "CPA", "uradni": "AGIS", "moji": "Moji"}

    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Izvozi kot katalog"))
        self.resize(480, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self.tr("Izberite vire za datoteko kataloga AGIS\n"
                                        "(nato jo naložite na GitHub kot catalogue/agis_viri.db).")))
        self.list = QListWidget()
        for e in entries:
            item = QListWidgetItem(f"[{self.TITLES.get(e['katalog'], e['katalog'])}] {e['naziv']}")
            item.setData(Qt.ItemDataRole.UserRole, e)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            default = e["katalog"] in ("uradni", "moji") and e.get("omogocen", True)
            item.setCheckState(Qt.CheckState.Checked if default else Qt.CheckState.Unchecked)
            self.list.addItem(item)
        layout.addWidget(self.list)

        row = QHBoxLayout()
        all_btn, none_btn = QPushButton(self.tr("Vse")), QPushButton(self.tr("Nič"))
        all_btn.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        none_btn.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        row.addWidget(all_btn)
        row.addWidget(none_btn)
        row.addStretch()
        layout.addLayout(row)

        buttons = QDialogButtonBox(OK_CANCEL)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_all(self, state):
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(state)

    def selected(self):
        result = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result

    @staticmethod
    def ask_path(parent):
        path, _ = QFileDialog.getSaveFileName(parent, "Shrani katalog", "agis_viri.db", "Katalog AGIS (*.db)")
        return path
