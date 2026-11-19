"""'Nastavitve' tab: catalogue, own parcel layer, web service addresses, connections.
Every change is saved at once."""
from qgis.PyQt.QtWidgets import (
    QCheckBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QToolButton, QVBoxLayout, QWidget,
)
from qgis.core import Qgis, QgsApplication, QgsMapLayerProxyModel, QgsSettings, QgsTask
from qgis.gui import QgsFieldComboBox, QgsMapLayerComboBox

from . import config, parcele
from .externals import cpa_available

try:
    POLYGON_FILTER = Qgis.LayerFilter.PolygonLayer
except AttributeError:
    POLYGON_FILTER = QgsMapLayerProxyModel.PolygonLayer

KEY_OFFICIAL = "agis/official_catalogue"

URL_LABELS = [
    ("gurs_wfs_url", "GURS WFS (parcele)"),
    ("geohub_research_url", "eArheologija"),
    ("geohub_evrd_url", "eVRD"),
]


def official_catalogue_enabled():
    return QgsSettings().value(KEY_OFFICIAL, True, type=bool)


class TabNastavitve(QScrollArea):

    def __init__(self, on_changed=None, parent=None):
        super().__init__(parent)
        self._on_changed = on_changed       # called after a change that needs a refresh elsewhere
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        self.setWidget(inner)

        # --- Layer sources ---------------------------------------------------
        sources = QGroupBox(self.tr("Viri slojev"))
        sl = QVBoxLayout(sources)
        self.official = QCheckBox(self.tr("Uporabi katalog AGIS (prenos z GitHuba)"))
        self.official.setChecked(official_catalogue_enabled())
        self.official.toggled.connect(self._official_toggled)
        sl.addWidget(self.official)
        sl.addWidget(self._hint(self.tr(
            "Katalog AGIS je skupni seznam virov (oznaka s tremi pikami, vedno na vrhu seznama), objavljen na GitHubu. "
            "Ob zagonu se prenese najnovejša različica; brez povezave se uporabi zadnja prenesena.")))
        layout.addWidget(sources)

        # --- Parcels: own layer -----------------------------------------------
        own = QGroupBox(self.tr("Parcele – lasten sloj"))
        ol = QVBoxLayout(own)
        hint = QLabel(self.tr("Uporabi se, ko baza CPA in GURS WFS nista dosegljiva (ali vedno najprej, "
                              "če označite spodaj). AGIS si zapomni vir sloja, zato deluje v vsakem projektu."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        ol.addWidget(hint)

        row = QHBoxLayout()
        self.own_name = QLabel()
        self.own_name.setWordWrap(True)
        row.addWidget(self.own_name, 1)
        self.own_clear = QToolButton()
        self.own_clear.setText("✕")
        self.own_clear.setToolTip(self.tr("Pozabi lasten sloj"))
        self.own_clear.clicked.connect(self._clear_own)
        row.addWidget(self.own_clear)
        ol.addLayout(row)

        form = QFormLayout()
        self.own_layer = QgsMapLayerComboBox()
        self.own_layer.setFilters(POLYGON_FILTER)
        self.own_layer.setAllowEmptyLayer(True)
        self.own_layer.setLayer(None)
        self.own_layer.layerChanged.connect(self._own_layer_picked)
        self.ko_field = QgsFieldComboBox()
        self.parc_field = QgsFieldComboBox()
        self.ko_field.fieldChanged.connect(self._fields_changed)
        self.parc_field.fieldChanged.connect(self._fields_changed)
        form.addRow(self.tr("Izberi iz projekta:"), self.own_layer)
        form.addRow(self.tr("Polje ID K.O.:"), self.ko_field)
        form.addRow(self.tr("Polje št. parcele:"), self.parc_field)
        ol.addLayout(form)
        self.own_error = QLabel()
        self.own_error.setWordWrap(True)
        self.own_error.setStyleSheet("color: #c62828;")
        self.own_error.hide()
        ol.addWidget(self.own_error)
        self.own_first = QCheckBox(self.tr("Uporabi pred ostalimi viri"))
        self.own_first.setChecked(parcele.own_settings()[3])
        self.own_first.toggled.connect(lambda on: QgsSettings().setValue(parcele.KEY_FIRST, on))
        ol.addWidget(self.own_first)
        layout.addWidget(own)
        self._show_own()

        # --- Web services -------------------------------------------------------
        web = QGroupBox(self.tr("Spletni viri"))
        wf = QFormLayout(web)
        wf.addRow(self._hint(self.tr(
            "Uporabijo se, ko kopija v bazi CPA ni dosegljiva: GURS WFS za parcele, geohub.gov.si "
            "(Ministrstvo za kulturo) za eArheologijo in eVRD. Naslov spremenite le, če se storitev preseli; "
            "↺ vrne privzetega.")))
        self.url_edits = {}
        for key, label in URL_LABELS:
            edit = QLineEdit(config.get(key))
            edit.setToolTip(self.tr("Privzeto: {}").format(config.default(key)))
            edit.setCursorPosition(0)
            edit.editingFinished.connect(lambda k=key: self._url_changed(k))
            reset = QToolButton()
            reset.setText("↺")
            reset.setToolTip(self.tr("Ponastavi na privzeti naslov"))
            reset.clicked.connect(lambda _c=False, k=key: self._url_reset(k))
            line = QHBoxLayout()
            line.addWidget(edit)
            line.addWidget(reset)
            wf.addRow(label + ":", line)
            self.url_edits[key] = edit
        layout.addWidget(web)

        # --- Connections ----------------------------------------------------------
        status = QGroupBox(self.tr("Povezave"))
        self.status_layout = QVBoxLayout(status)
        self.cpa_status = QLabel()
        self.status_layout.addWidget(self.cpa_status)
        self.dev_info = QLabel()
        self.dev_info.setWordWrap(True)
        self.dev_info.setStyleSheet("color: #e65100;")
        self.status_layout.addWidget(self.dev_info)
        self.reset_btn = QPushButton(self.tr("Ponastavi na produkcijsko bazo CPA"))
        self.reset_btn.clicked.connect(self._reset_dev)
        self.status_layout.addWidget(self.reset_btn)
        layout.addWidget(status)
        layout.addStretch()
        self.update_status(refresh=False)

    @staticmethod
    def _hint(text):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("color: #666;")
        return label

    # ----------------------------------------------------------------- events

    def showEvent(self, event):
        super().showEvent(event)
        self._show_own()
        self.check_connection()

    def check_connection(self):
        """Check the CPA database in the background (a slow name lookup must not block the tab)."""
        if getattr(self, "_check_task", None) is not None:
            return
        self.cpa_status.setText(self.tr("Baza CPA: preverjam…"))
        self._check_task = QgsTask.fromFunction("AGIS: povezava CPA", lambda task: cpa_available(refresh=True),
                                                on_finished=self._checked)
        QgsApplication.taskManager().addTask(self._check_task)

    def _checked(self, exception, result=None):
        self._check_task = None
        try:
            self.update_status(refresh=False)
        except RuntimeError:            # tab already deleted
            pass

    def _changed(self):
        if self._on_changed:
            self._on_changed()

    # ---------------------------------------------------------------- catalogue

    def _official_toggled(self, on):
        QgsSettings().setValue(KEY_OFFICIAL, on)
        self._changed()

    # ---------------------------------------------------------------- own layer

    def _show_own(self):
        name = parcele.own_settings()[0]
        source, _provider = parcele.own_source()
        layer = parcele.open_own_layer()
        if name and layer is not None:
            self.own_name.setText(self.tr("Shranjen sloj: <b>{}</b>").format(name))
        elif name:
            self.own_name.setText(self.tr("Shranjen sloj: <b>{}</b> – <span style='color:#c62828'>"
                                          "vira ni mogoče odpreti</span>").format(name))
        else:
            self.own_name.setText(self.tr("Lasten sloj ni nastavljen."))
        self.own_name.setToolTip(source)
        self.own_clear.setEnabled(bool(name))
        _, ko_f, parc_f, _ = parcele.own_settings()
        for combo, field in ((self.ko_field, ko_f), (self.parc_field, parc_f)):
            combo.blockSignals(True)
            combo.setLayer(layer)
            combo.setField(field if layer is not None else "")
            combo.blockSignals(False)

    def _own_layer_picked(self, layer):
        if layer is None:
            return
        self.own_error.hide()
        try:
            parcele.save_own_layer(layer)
        except ValueError as e:
            self.own_error.setText(str(e))
            self.own_error.show()
        self.own_layer.blockSignals(True)
        self.own_layer.setLayer(None)
        self.own_layer.blockSignals(False)
        self._show_own()

    def _fields_changed(self, *_):
        if self.ko_field.layer() is not None:
            parcele.save_own_fields(self.ko_field.currentField(), self.parc_field.currentField())

    def _clear_own(self):
        parcele.clear_own_layer()
        self.own_error.hide()
        self._show_own()

    # ------------------------------------------------------------------- web

    def _url_changed(self, key):
        edit = self.url_edits[key]
        config.set_user(key, edit.text())
        edit.setText(config.get(key))
        edit.setCursorPosition(0)
        if key == "gurs_wfs_url":
            parcele.wfs_reachable(refresh=True)

    def _url_reset(self, key):
        self.url_edits[key].setText(config.default(key))
        self._url_changed(key)

    # ------------------------------------------------------------- connections

    def update_status(self, refresh=True):
        reachable = cpa_available(refresh=refresh)
        self.cpa_status.setText(self.tr("Baza CPA: ") + (self.tr("dosegljiva") if reachable
                                                          else self.tr("ni dosegljiva")))
        overrides = config.overrides()
        lines = "<br>".join(f"{k} = {'***' if 'password' in k else v}" for k, v in overrides.items())
        self.dev_info.setText(f"<b>{self.tr('Razvojni način')}</b><br>{lines}" if overrides else "")
        self.dev_info.setVisible(bool(overrides))
        self.reset_btn.setVisible(bool(overrides))
        self.reset_btn.setEnabled(True)

    def _reset_dev(self):
        QgsSettings().remove(config.DEV_GROUP)
        cpa_available(refresh=True)
        self.update_status(refresh=False)
        self._changed()
