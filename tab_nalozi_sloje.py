from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QToolButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMenu,
    QAction, QAbstractItemView, QProgressBar, QLabel
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

class SortableIconItem(QTableWidgetItem):
    def __init__(self, sort_key):
        super().__init__()
        self._sort_key = sort_key

    def __lt__(self, other):
        if isinstance(other, SortableIconItem):
            return self._sort_key < other._sort_key
        return super().__lt__(other)
    
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


        self._status_bar = QLabel()
        self._status_bar.setFixedHeight(4)
        self._status_bar.setStyleSheet("background: #eee;")  # grey = unknown
        main_layout.addWidget(self._status_bar)



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

        # Preload icons
        self._icons = {
            k: QIcon(str(pn_path("icons") / v))
            for k, v in self.ICON_BY_TYPE.items()
        }
        self._icon_default = QIcon(str(pn_path("icons") / "layer.png"))

        self.load_resources()
        self.table.cellDoubleClicked.connect(self.handle_double_click)

        self._update_status_bar()


        # STATE
        self._layer_queue = []
        self._loading_active = False
        self._total_layers = 0
        self._loaded_count = 0
        self._canvas = None






    # -----------------------------------------------------------------------


    def _update_status_bar(self):
        if access(self):
            self._status_bar.setStyleSheet("background: #4caf50;")  # green = connected
            self._status_bar.setToolTip(self.tr("Povezan z bazo CPA"))
        else:
            self._status_bar.setStyleSheet("background: #eee;")  # grey = not connected
            self._status_bar.setToolTip(self.tr("Ni povezave z bazo CPA"))

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
                    "qml": f["qml"],
                    "qlr_xml": f["qlr_xml"], 
                    "order": f["order"]
                } for f in table.getFeatures()]

        conn = sqlite3.connect(self.resources_db)
        c = conn.cursor()
        c.execute("""
            SELECT name, source_type, uri, url, description, authority, qml, qlr_xml, "order"
            FROM layer_sources
            WHERE enabled=1
            ORDER BY "order" ASC
        """)
        rows = c.fetchall()
        conn.close()

        resources = []
        for name, source_type, uri, url, description, authority, qml, qlr_xml, order in rows:
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
                "qml": qml or "",
                "qlr_xml": qlr_xml or "",
                "order": order
            })
        return resources

    # -----------------------------------------------------------------------


    def load_resources(self):
        self.resources = self.get_resources_from_db()
        self._populate_table()



    def _populate_table(self):
        t = self.table
        t.setUpdatesEnabled(False)
        t.setSortingEnabled(False)
        t.clearContents()
        t.setRowCount(len(self.resources))

        for row, res in enumerate(self.resources):
            icon_item = SortableIconItem(res.get("order", row))
            icon_item.setIcon(self._icons.get(res["type"], self._icon_default))
            icon_item.setFlags(Qt.ItemFlag.ItemIsEnabled)

                
            tooltip = (
                f"Name: {res['naziv']}\n"
                f"URI: {res['uri']}\n"
                f"Description: {res['opis']}\n"
                f"Authority: {res.get('authority', 'N/A')}"
            )  # keep it short

            name_item = QTableWidgetItem(res["naziv"])
            name_item.setData(Qt.ItemDataRole.UserRole, res)
            name_item.setToolTip(tooltip)

            desc_item = QTableWidgetItem(res["opis"])
            desc_item.setToolTip(tooltip)
            
            t.setItem(row, 0, icon_item)
            t.setItem(row, 1, name_item)
            t.setItem(row, 2, desc_item)

        t.setUpdatesEnabled(True)
        t.setSortingEnabled(True)
        t.sortItems(t.horizontalHeader().sortIndicatorSection(),
                t.horizontalHeader().sortIndicatorOrder())



    def refresh_table(self):
        self.table.horizontalHeader().setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        self.load_resources()
        self._update_status_bar()



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





    def _load_qlr_from_string(self, qlr_xml, name):
        doc = QDomDocument()
        ok, err, line, col = doc.setContent(qlr_xml)
        if not ok:
            log(f"QLR XML parse error at line {line}: {err}", Qgis.Critical)
            return

        QgsLayerDefinition.loadLayerDefinition(
            doc,
            QgsProject.instance(),
            QgsProject.instance().layerTreeRoot(),
            QgsReadWriteContext()
        )




    def _load_single_layer(self, res):
        name = res["naziv"]
        uri = res.get("uri") or res.get("url")
        t = res.get("type")
        provider = res.get("type", "ogr")
        style_path = res.get("qml")
        qlr_xml = res.get("qlr_xml")

        try:
            if t in ("qlr", "definition"):
                if qlr_xml:
                    self._load_qlr_from_string(qlr_xml, name)
                    log(f"QLR load from db: {name}", Qgis.Info)
                else:
                    self.iface.mapCanvas().setMapTool(None)
                    QgsLayerDefinition.loadLayerDefinition(
                        uri,
                        QgsProject.instance(),
                        QgsProject.instance().layerTreeRoot()
                    )
                    log(f"QLR load from file: {name}", Qgis.Info)
          
                    
            elif t == "wms":
                layer = QgsRasterLayer(uri, name, "wms")

                if not layer or layer.dataProvider() is None:
                    log(f"Invalid WMTS/WMS provider: {name}", Qgis.Critical)
                    return

                if not layer.isValid():
                    log(f"Invalid raster layer: {name}", Qgis.Critical)
                    return

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


    def show_context_menu(self, pos):
        menu = QMenu(self)
        action = QAction("Naloži izbrane sloje", self)
        action.triggered.connect(self.load_selected_layers)
        menu.addAction(action)
        menu.exec(self.table.viewport().mapToGlobal(pos))