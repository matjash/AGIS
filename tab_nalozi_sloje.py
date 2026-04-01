from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QToolButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMenu,
    QAction, QAbstractItemView, QProgressBar
)
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtXml import QDomDocument
from qgis.core import (
    QgsVectorLayer,
    QgsRasterLayer,
    QgsProject,
    QgsLayerDefinition,
    Qgis,
    QgsMessageLog,
    QgsReadWriteContext
)

import sqlite3
import os
from .externals import pn_path, access, load_cpa_sources_list

LOG_TAG = "TabNaloziSloje"


def log(msg, level=Qgis.Info):
    QgsMessageLog.logMessage(msg, LOG_TAG, level)


class TabNaloziSloje(QWidget):

    ICON_BY_TYPE = {
        "layer": "layer.png",
        "group": "group.png",
        "definition": "sourcetype_qlr.png",
        "qlr": "sourcetype_qlr.png",
        "service": "server.png",
        "wms": "sourcetype_wms.png",
        "wfs": "sourcetype_wfs.png",
        "arcgisfeatureserver": "sourcetype_arcgis.png",
        "arcgismapserver": "sourcetype_arcgis.png",
        "default": "default.png"
    }

    def __init__(self, iface=None, parent=None):
        super().__init__(parent)

        self.resources_db = pn_path('plugin') / "sources.db"
        self.iface = iface
        self.resources = []

        main_layout = QVBoxLayout(self)

        # SEARCH
        top_layout = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(self.tr("Išči vire..."))
        self.search.textChanged.connect(self.filter_table)

        self.settings_btn = QToolButton()
        self.settings_btn.setIcon(QIcon(str(pn_path("icons") / "refresh.png")))
        self.settings_btn.clicked.connect(self.refresh_table)


        self.cancel_btn = QToolButton()
        self.cancel_btn.setText("✕")
        self.cancel_btn.clicked.connect(self.cancel_loading)
        self.cancel_btn.setEnabled(False)


        top_layout.addWidget(self.search)
        top_layout.addWidget(self.settings_btn)
        top_layout.addWidget(self.cancel_btn)
        main_layout.addLayout(top_layout)

 
        self.progress = QProgressBar()
        self.progress.setFixedHeight(4)  # thin
        self.progress.setMaximumHeight(3)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)


        # style (thin + green)
        self.progress.setStyleSheet("""
        QProgressBar {
            border: none;
            background: #eee;
        }
        QProgressBar::chunk {
            background-color: #4caf50;
        }
        """)

        main_layout.addWidget(self.progress)


        # TABLE
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["", "Naziv", "Opis"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        main_layout.addWidget(self.table)

        self.load_resources()
        self.table.cellDoubleClicked.connect(self.handle_double_click)

        # STATE
        self._layer_queue = []
        self._loading_active = False
        self._total_layers = 0
        self._loaded_count = 0
        self._canvas = None

    # -----------------------------------------------------------------------

    def get_resources_from_db(self):
        if access(self):
            table = load_cpa_sources_list(self)
            if table and table.isValid():
                return [{
                    "type": f["source_type"],
                    "naziv": f["name"],
                    "opis": f["description"] or "",
                    "uri": f["uri"],
                    "url": f["url"],
                    "authority": f["authority"],
                    "qml": f["qml"]
                } for f in table.getFeatures()]

        conn = sqlite3.connect(self.resources_db)
        c = conn.cursor()
        c.execute("""
            SELECT name, source_type, uri, url, description, authority, qml
            FROM layer_sources
            WHERE enabled=1
            ORDER BY "order", id
        """)
        rows = c.fetchall()
        conn.close()

        resources = []
        for name, source_type, uri, url, description, authority, qml in rows:
            if uri:
                uri = uri.replace("{qlrs}", str(pn_path("qlrs")))
            if qml:
                qml = qml.replace("{qml}", str(pn_path("qml")))
            resources.append({
                "type": source_type,
                "naziv": name,
                "opis": description or "",
                "uri": uri,
                "url": url,
                "authority": authority or "",
                "qml": qml or ""
            })
        return resources

    # -----------------------------------------------------------------------

    def load_resources(self):
        self.resources = self.get_resources_from_db()
        self.table.setRowCount(len(self.resources))

        for row, res in enumerate(self.resources):
            icon = QTableWidgetItem()
            icon.setIcon(QIcon(str(pn_path("icons") / self.ICON_BY_TYPE.get(res["type"], "layer.png"))))
            self.table.setItem(row, 0, icon)

            tooltip = (
                f"Name: {res['naziv']}\n"
                f"Type: {res['type']}\n"
                f"URI: {res['uri']}\n"
                f"Description: {res['opis']}\n"
                f"Authority: {res.get('authority', 'N/A')}"
            )

            
            name_item = QTableWidgetItem(res["naziv"])
            name_item.setData(Qt.ItemDataRole.UserRole, res)
            name_item.setToolTip(tooltip)
            opis_item = QTableWidgetItem(res["opis"])
            opis_item.setToolTip(tooltip)

            self.table.setItem(row, 1, name_item)
            self.table.setItem(row, 2, opis_item)

    # -----------------------------------------------------------------------

    def filter_table(self, text):
        text = text.lower()
        for row, res in enumerate(self.resources):
            self.table.setRowHidden(row, not (
                text in res["naziv"].lower() or text in res["opis"].lower()
            ))

    # -----------------------------------------------------------------------

    def _res_from_visual_row(self, row):
        return self.table.item(row, 1).data(Qt.ItemDataRole.UserRole)

    def handle_double_click(self, row, col):
        res = self._res_from_visual_row(row)
        if res:
            self.load_layers_queue([res])

    def load_selected_layers(self):
        rows = self.table.selectionModel().selectedRows()
        resources = [self._res_from_visual_row(r.row()) for r in rows]
        self.load_layers_queue(resources)

    # -----------------------------------------------------------------------
    # QUEUE LOADING
    # -----------------------------------------------------------------------

    def load_layers_queue(self, resources):
        self.progress.setValue(10)
        if not resources or self._loading_active:
            return

        self._layer_queue = list(resources)
        self._total_layers = len(resources)
        self._loaded_count = 0
        self._loading_active = True

        self.cancel_btn.setEnabled(True)

        
        from qgis.utils import iface
        self._canvas = iface.mapCanvas()
        self._canvas.freeze(True)

        self._load_next_layer()

    def _load_next_layer(self):
        if not self._loading_active:
            return

        if not self._layer_queue:
            self._finish_loading()
            return

        res = self._layer_queue.pop(0)
        QTimer.singleShot(50, lambda r=res: self._load_single_layer(r))



    def _load_single_layer(self, res):
        name = res["naziv"]
        uri = res.get("uri") or res.get("url")
        t = res.get("type")
        provider = res.get("type", "ogr")
        style_path = res.get("qml")
       

        try:
            if t in ("qlr", "definition"):
                QgsLayerDefinition.loadLayerDefinition(uri, QgsProject.instance(), QgsProject.instance().layerTreeRoot())

            elif t == "wms":
                layer = QgsRasterLayer(uri, name, "wms")
                if layer.isValid():
                    QgsProject.instance().addMapLayer(layer)

            else:
                layer = QgsVectorLayer(uri, name, provider)
                if layer.isValid():
                    if style_path:
                        log(f"Path: {style_path}", Qgis.Warning)
                        ok = layer.loadNamedStyle(style_path)

                        if ok:
                            layer.triggerRepaint()
                        else:
                            log(f"Failed to load QML: {style_path}", Qgis.Warning)

          
                if layer.isValid():
                    QgsProject.instance().addMapLayer(layer)

        except Exception as e:
            log(f"Error: {e}", Qgis.Critical)

     
        self._loaded_count += 1

        progress = int((self._loaded_count / self._total_layers) * 100)
        self.progress.setValue(progress)


        self._load_next_layer()

    def _finish_loading(self):
        
        self._loading_active = False
        self.cancel_btn.setEnabled(False)


        if self._canvas:
            self._canvas.freeze(False)
            self._canvas.refresh()
        self.progress.setValue(100)
        QTimer.singleShot(500, lambda: self.progress.setValue(0))

    def cancel_loading(self):
        self._layer_queue = []
        self._loading_active = False
        self.cancel_btn.setEnabled(False)

        if self._canvas:
            self._canvas.freeze(False)
            self._canvas.refresh()
        self.progress.setValue(0)
    # -----------------------------------------------------------------------

    def refresh_table(self):
        self.load_resources()

    def show_context_menu(self, pos):
        menu = QMenu(self)
        action = QAction("Naloži izbrane sloje", self)
        action.triggered.connect(self.load_selected_layers)
        menu.addAction(action)
        menu.exec(self.table.viewport().mapToGlobal(pos))