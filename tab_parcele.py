"""'Parcele' tab: find a parcel by K.O. and number, or all parcels under a layer."""
import html

from qgis.PyQt.QtCore import QStringListModel, Qt
from qgis.PyQt.QtWidgets import (
    QApplication, QCheckBox, QSizePolicy, QCompleter, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)
from qgis.core import Qgis, QgsApplication, QgsMapLayerProxyModel, QgsProject, QgsTask
from qgis.gui import QgsMapLayerComboBox

from . import parcele
from .externals import log

try:
    VECTOR_FILTER = Qgis.LayerFilter.VectorLayer
except AttributeError:
    VECTOR_FILTER = QgsMapLayerProxyModel.VectorLayer


def short(text, limit=300):
    """Error text for the status line: one paragraph, not too long."""
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + " …"


def status_label():
    """Status line that wraps, never widens the panel, and can be selected and copied."""
    label = QLabel()
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    label.setMinimumWidth(1)
    return label


def _completer(parent):
    c = QCompleter(parent)
    c.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    c.setFilterMode(Qt.MatchFlag.MatchContains)
    c.setModel(QStringListModel(c))
    return c


class TabParcele(QWidget):

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self._tasks = set()
        self._last = None               # last Result
        self._last_name = ""
        self._parcels_for = None        # K.O. id the parcel suggestions belong to
        self.ko = parcele.load_ko()

        layout = QVBoxLayout(self)
        self.sub_tabs = QTabWidget()
        layout.addWidget(self.sub_tabs)

        # --- one parcel ------------------------------------------------------
        box = QWidget()
        box_layout = QVBoxLayout(box)
        form = QFormLayout()
        box_layout.addLayout(form)
        box_layout.addStretch()
        self.ko_edit = QLineEdit()
        self.ko_edit.setPlaceholderText(self.tr("šifra ali ime, npr. 1722"))
        self.ko_completer = _completer(self.ko_edit)
        self.ko_edit.setCompleter(self.ko_completer)
        self._fill_ko_completer()
        self.ko_edit.editingFinished.connect(self._ko_changed)
        self.ko_completer.activated.connect(lambda _t: self._ko_changed())
        self.parc_edit = QLineEdit()
        self.parc_edit.setPlaceholderText(self.tr("npr. 123/4"))
        self.parc_completer = _completer(self.parc_edit)
        self.parc_completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        self.parc_edit.setCompleter(self.parc_completer)
        self.parc_edit.returnPressed.connect(lambda: self.find(load=False))
        form.addRow(self.tr("K.O.:"), self.ko_edit)
        form.addRow(self.tr("Parcela:"), self.parc_edit)
        row = QHBoxLayout()
        self.find_btn = QPushButton(self.tr("Poišči"))
        self.find_btn.clicked.connect(lambda: self.find(load=False))
        self.load_btn = QPushButton(self.tr("Naloži kot sloj"))
        self.load_btn.clicked.connect(lambda: self.find(load=True))
        row.addWidget(self.find_btn)
        row.addWidget(self.load_btn)
        form.addRow(row)
        self.sub_tabs.addTab(box, self.tr("Iskanje parcele"))

        # --- parcels under a layer --------------------------------------------
        box2 = QWidget()
        box2_layout = QVBoxLayout(box2)
        form2 = QFormLayout()
        box2_layout.addLayout(form2)
        box2_layout.addStretch()
        self.area_layer = QgsMapLayerComboBox()
        self.area_layer.setFilters(VECTOR_FILTER)
        self.selected_only = QCheckBox(self.tr("Samo izbrani objekti"))
        self.buffer = QDoubleSpinBox()
        self.buffer.setRange(-10000, 10000)
        self.buffer.setDecimals(1)
        self.buffer.setSuffix(" m")
        self.buffer.setToolTip(self.tr("Pozitiven odmik območje poveča, negativen ga zmanjša."))
        self.area_btn = QPushButton(self.tr("Naloži parcele"))
        self.area_btn.clicked.connect(lambda: self.parcels_under_layer(as_text=False))
        self.list_btn = QPushButton(self.tr("Izpiši seznam parcel"))
        self.list_btn.clicked.connect(lambda: self.parcels_under_layer(as_text=True))
        form2.addRow(self.tr("Sloj:"), self.area_layer)
        form2.addRow("", self.selected_only)
        form2.addRow(self.tr("Odmik:"), self.buffer)
        row2 = QHBoxLayout()
        row2.addWidget(self.area_btn)
        row2.addWidget(self.list_btn)
        form2.addRow(row2)
        self.sub_tabs.addTab(box2, self.tr("Parcele pod slojem"))

        self.status = status_label()
        layout.addWidget(self.status)

        if parcele.ko_needs_refresh():
            self._run("AGIS: seznam K.O.", parcele.refresh_ko, done=self._ko_refreshed, quiet=True)

    # ---------------------------------------------------------------- helpers

    def _run(self, description, fn, *args, done=None, quiet=False):
        """Run fn in the background; done(result) on success, errors shown in the status line."""
        def finished(exception, result=None):
            self._tasks.discard(task)
            self._busy(bool(self._tasks))
            if exception is not None:
                log(f"{description}: {exception}", Qgis.MessageLevel.Warning)
                if not quiet:
                    self._status(html.escape(short(exception)), error=True)
                return
            if done:
                done(result)

        task = QgsTask.fromFunction(description, fn, *args, on_finished=finished)
        self._tasks.add(task)
        if not quiet:
            self._busy(True)
        QgsApplication.taskManager().addTask(task)
        return task

    def _busy(self, busy):
        for b in (self.find_btn, self.load_btn, self.area_btn, self.list_btn):
            b.setEnabled(not busy)
        if busy:
            self._status(self.tr("Iščem…"))

    def _status(self, text, error=False):
        self.status.setText(f'<span style="color:{"#c62828" if error else "#333"}">{text}</span>')

    def _fill_ko_completer(self):
        self.ko_completer.model().setStringList([parcele.ko_label(k, self.ko) for k in sorted(self.ko)])

    def _ko_refreshed(self, n):
        self.ko = parcele.load_ko()
        self._fill_ko_completer()
        log(f"Seznam K.O. osvežen ({n}).", Qgis.MessageLevel.Info)

    def current_ko(self, show_choices=True):
        ko_id, matches = parcele.resolve_ko(self.ko_edit.text(), self.ko)
        if ko_id is None and show_choices:
            if matches:
                self._status(self.tr("Več K.O. s tem imenom – izberite s seznama."))
                self.ko_completer.setCompletionPrefix(self.ko_edit.text().strip())
                self.ko_completer.complete()
            elif self.ko_edit.text().strip():
                self._status(self.tr("K.O. »{}« ne obstaja.").format(html.escape(self.ko_edit.text().strip())), error=True)
        return ko_id

    def _ko_changed(self):
        ko_id = self.current_ko()
        if ko_id is None:
            return
        self.ko_edit.setText(parcele.ko_label(ko_id, self.ko))
        if ko_id == self._parcels_for:
            return
        self._parcels_for = ko_id
        self.parc_completer.model().setStringList([])
        own = parcele.own_layer()
        if own and parcele.own_settings()[3]:
            self._set_parcels(ko_id, parcele.parcel_numbers_layer(own[0], own[1], own[2], ko_id))
        else:
            self._run("AGIS: seznam parcel", parcele.parcel_numbers_remote, ko_id,
                      done=lambda numbers, k=ko_id: self._set_parcels(k, numbers), quiet=True)

    def _set_parcels(self, ko_id, numbers):
        if ko_id == self._parcels_for:
            self.parc_completer.model().setStringList(numbers)

    # ----------------------------------------------------------------- search

    def find(self, load=False):
        ko_id = self.current_ko()
        parcela = parcele.normalize_parcel(self.parc_edit.text())
        if ko_id is None or not parcela:
            if ko_id is not None:
                self._status(self.tr("Vpišite številko parcele."), error=True)
            return
        if not parcele.valid_parcel(parcela):
            self._status(self.tr("»{}« ni številka parcele (npr. 123 ali 123/4).").format(html.escape(parcela)), error=True)
            return
        name = self.tr("Parcela {}, K.O. {}").format(parcela, ko_id)
        own = parcele.own_layer()
        own_first = parcele.own_settings()[3]

        if own and own_first:
            r = parcele.find_layer(own[0], own[1], own[2], ko_id, parcela)
            if r.features:
                self._show(r, name, load)
                return
        self._run("AGIS: iskanje parcele", parcele.find_remote, ko_id, parcela,
                  done=lambda r: self._after_remote(r, name, load, own, own_first,
                                                    lambda: parcele.find_layer(own[0], own[1], own[2], ko_id, parcela)))

    def parcels_under_layer(self, as_text=False):
        layer = self.area_layer.currentLayer()
        if layer is None:
            self._status(self.tr("Izberite sloj."), error=True)
            return
        try:
            geom = parcele.area_geometry(layer, self.selected_only.isChecked(), self.buffer.value())
        except ValueError as e:
            self._status(html.escape(short(e)), error=True)
            return
        name = self.tr("Parcele pod slojem {}").format(layer.name())
        extra = []
        if self.selected_only.isChecked():
            extra.append(self.tr("izbrani"))
        if self.buffer.value():
            extra.append(self.tr("odmik {:g} m").format(self.buffer.value()))
        if extra:
            name += f" ({', '.join(extra)})"
        own = parcele.own_layer()
        own_first = parcele.own_settings()[3]
        load = "text" if as_text else True
        if own and own_first:
            self._show(parcele.intersect_layer(own[0], geom, own[1], own[2]), name, load)
            return
        self._run("AGIS: parcele pod slojem", parcele.intersect_remote, geom,
                  done=lambda r: self._after_remote(r, name, load, own, own_first,
                                                    lambda: parcele.intersect_layer(own[0], geom, own[1], own[2])))

    def _after_remote(self, result, name, load, own, own_first, own_query):
        if result is not None and (result.features or result.authoritative):
            self._show(result, name, load)
            return
        if own and not own_first:
            r = own_query()
            if r.features or result is None:
                self._show(r, name, load)
                return
        if result is not None:
            self._show(result, name, load)
            return
        self._status(self.tr("Baza CPA in GURS WFS nista dosegljiva. V zavihku Nastavitve "
                             "izberite svoj sloj s polji za K.O. in parcelo."), error=True)

    def _show(self, result, name, load):
        self._last, self._last_name = result, name
        n = len(result.features)
        if n == 0:
            if result.authoritative:
                self._status(self.tr("Parcela ne obstaja. <i>Vir: {}</i>").format(result.label), error=True)
            else:
                self._status(self.tr("Ni najdeno. <i>Vir: {}</i>").format(result.label), error=True)
            return
        if load == "text":
            try:
                text = parcele.parcel_list_text(parcele.parcel_pairs(result), self.ko)
            except ValueError as e:
                self._status(html.escape(short(e)), error=True)
                return
            parcele.zoom_and_flash(self.iface.mapCanvas(), result)
            self._status(self.tr("Parcel: {}. <i>Vir: {}</i>").format(n, result.label))
            ParcelListDialog(text, name, result.label, self).exec()
            return
        parcele.zoom_and_flash(self.iface.mapCanvas(), result)
        if load:
            layer = parcele.to_memory_layer(result, name)
            QgsProject.instance().addMapLayer(layer)
        text = self.tr("Najdenih: {}.").format(n) if n > 1 else self.tr("Najdeno.")
        self._status(f"{text} <i>Vir: {result.label}</i>")


class ParcelListDialog(QDialog):
    """Text list of parcels with a copy button."""

    def __init__(self, text, title, source, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(520, 300)
        layout = QVBoxLayout(self)
        self.text = QPlainTextEdit(text)
        self.text.setReadOnly(True)
        layout.addWidget(self.text)
        note = QLabel(self.tr("Vir: {}").format(source))
        note.setStyleSheet("color: #666;")
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        copy_btn = buttons.addButton(self.tr("Kopiraj"), QDialogButtonBox.ButtonRole.ActionRole)
        copy_btn.clicked.connect(self.copy)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def copy(self):
        QApplication.clipboard().setText(self.text.toPlainText())
