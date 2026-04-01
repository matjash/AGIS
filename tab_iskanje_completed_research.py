import requests
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QPushButton, 
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, 
    QMessageBox, QMenu, QLabel
)
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.core import QgsGeometry, QgsPointXY
from qgis.gui import QgsRubberBand
from qgis.PyQt.QtGui import QColor
import json


class CompletedResearchTab(QWidget):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.search_fields = ["KODA_RAZ", "EID", "IZVAJALEC", "RAZ_POST"]
        self.active_fields = list(self.search_fields)
        self.data = []
        self.filtered_data = []
        self.setup_ui()
        self.load_data()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
   
        # Top layout: field button + search bar + extent button
        top_layout = QHBoxLayout()
        
        self.field_button = QPushButton("Izberi iskalna polja")
        top_layout.addWidget(self.field_button)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Vnesite iskalni niz...")
        top_layout.addWidget(self.search_bar)
        
        self.extent_button = QPushButton("Filtriraj po obsegu")
        top_layout.addWidget(self.extent_button)
        
        layout.addLayout(top_layout)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["KODA_RAZ", "EID", "IZVAJALEC", "Poročilo", "RAZ_POST"])
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.table)
        
        # Signals
        self.search_bar.textChanged.connect(self.on_search)
        self.extent_button.clicked.connect(self.filter_extent)
        self.table.cellDoubleClicked.connect(self.zoom_to_feature)
        self.table.cellClicked.connect(self.open_pdf)
        self.field_button.clicked.connect(self.select_fields)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
    
    def load_data(self):
        try:
            self.data = self.fetch_data()
            self.filtered_data = self.data
            self.populate_table(self.data)
        except Exception as e:
            QMessageBox.critical(self, "Napaka", f"Napaka pri nalaganju podatkov: {str(e)}")
    
    def fetch_data(self):
        url = "https://geohub.gov.si/ags/rest/services/MK/MK_ARHEO/FeatureServer/3692/query"
        params = {
            "where": "STATUS_SK='zaključena'",  # Filter for completed research
            "outFields": "*",
            "f": "json",
            "outSR": 3794
        }
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        js = resp.json()
        rows = []
        
        for feature in js.get("features", []):
            attrs = feature.get("attributes", {})
            geom_json = feature.get("geometry")
            geom = QgsGeometry()
            
            if geom_json:
                if "x" in geom_json and "y" in geom_json:
                    geom = QgsGeometry.fromPointXY(QgsPointXY(geom_json["x"], geom_json["y"]))
                elif "rings" in geom_json:
                    rings = [[QgsPointXY(pt[0], pt[1]) for pt in ring] for ring in geom_json["rings"]]
                    geom = QgsGeometry.fromPolygonXY(rings)
                elif "paths" in geom_json:
                    paths = [[QgsPointXY(pt[0], pt[1]) for pt in path] for path in geom_json["paths"]]
                    if len(paths) == 1:
                        geom = QgsGeometry.fromPolylineXY(paths[0])
                    else:
                        geom = QgsGeometry.fromMultiPolylineXY(paths)
                            
                # Determine porocilo link
                p2 = attrs.get("URL_POROCILO2")
                p1 = attrs.get("URL_POROCILO1")

                if p2:
                    porocilo_url = p2
                elif p1:
                    porocilo_url = p1
                else:
                    porocilo_url = ""

                report_num = ""
                if porocilo_url:
                    try:
                        # Extract digits before /download
                        report_num = porocilo_url.rstrip("/").split("/")[-2]
                    except:
                        report_num = ""

                        

            rows.append({
                "KODA_RAZ": str(attrs.get("KODA_RAZ", "") or ""),
                "EID": str(attrs.get("EID", "") or ""),
                "IZVAJALEC": str(attrs.get("IZVAJALEC", "") or ""),
                "RAZ_POST": str(attrs.get("RAZ_POST", "") or ""),
                "POROCILO_URL": porocilo_url,
                "POROCILO_ID": report_num,
                "geom": geom,
                "raw": feature
            })

        
        return rows
    
    def populate_table(self, rows):
        self.filtered_data = rows
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        
        for r in rows:
            row_idx = self.table.rowCount()
            self.table.insertRow(row_idx)
            self.table.setItem(row_idx, 0, QTableWidgetItem(r["KODA_RAZ"]))
            self.table.setItem(row_idx, 1, QTableWidgetItem(r["EID"]))
            self.table.setItem(row_idx, 2, QTableWidgetItem(r["IZVAJALEC"]))
            if r["POROCILO_URL"]:
                item = QTableWidgetItem(r["POROCILO_ID"])
                item.setForeground(QColor(0, 0, 255))  # blue like hyperlink
                item.setData(Qt.ItemDataRole.UserRole, r["POROCILO_URL"])
            else:
                item = QTableWidgetItem("")

            self.table.setItem(row_idx, 3, item)
            self.table.setItem(row_idx, 4, QTableWidgetItem(r["RAZ_POST"]))
        
        self.table.setSortingEnabled(True)
    
    def on_search(self, text):
        txt = text.lower()
        filtered = [
            r for r in self.data
            if any(txt in str(r.get(f, "")).lower() for f in self.active_fields)
        ]
        self.populate_table(filtered)
    
    def filter_extent(self):
        canvas = self.iface.mapCanvas()
        extent = canvas.extent()
        extent_geom = QgsGeometry.fromRect(extent)
        
        filtered = []
        for r in self.data:
            if r["geom"] and not r["geom"].isEmpty():
                if r["geom"].intersects(extent_geom):
                    filtered.append(r)
        
        if not filtered:
            QMessageBox.information(
                self,
                "Brez rezultatov",
                "Nobena značilnost se ne nahaja v trenutnem obsegu karte."
            )
        
        self.populate_table(filtered)
    
    def show_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        
        menu = QMenu(self.table)
        more_info_action = menu.addAction("Več informacij")
        flash_geom_action = menu.addAction("Pokaži geometrijo")
        
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        
        if action == more_info_action:
            self.show_more_info(row)
        elif action == flash_geom_action:
            self.flash_geometry(row)
    
    def show_more_info(self, row):
        if row >= len(self.filtered_data):
            return
        
        rec = self.filtered_data[row]
        
        dlg = QDialog(self)
        dlg.setWindowTitle("Več informacij o značilnosti")
        dlg.resize(500, 400)
        layout = QVBoxLayout(dlg)
        
        info_table = QTableWidget()
        info_table.setColumnCount(2)
        info_table.setHorizontalHeaderLabels(["Atribut", "Vrednost"])
        
        attrs = rec["raw"].get("attributes", {})
        info_table.setRowCount(len(attrs))
        
        for i, (key, value) in enumerate(sorted(attrs.items())):
            info_table.setItem(i, 0, QTableWidgetItem(str(key)))
            info_table.setItem(i, 1, QTableWidgetItem(str(value)))
        
        info_table.resizeColumnsToContents()
        layout.addWidget(info_table)
        
        close_btn = QPushButton("Zapri")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)
        
        dlg.exec()
    
    def flash_geometry(self, row):
        if row >= len(self.filtered_data):
            return
        
        rec = self.filtered_data[row]
        geom = rec["geom"]
        
        if not geom or geom.isEmpty():
            QMessageBox.warning(self, "Brez geometrije", "Ta značilnost nima geometrije za prikaz.")
            return
        
        canvas = self.iface.mapCanvas()
        rubber = QgsRubberBand(canvas, geom.type())
        rubber.setToGeometry(geom, None)
        rubber.setColor(QColor(255, 0, 0, 100))
        rubber.setWidth(3)
        
        QTimer.singleShot(2000, lambda: rubber.reset(geom.type()))
    
    def zoom_to_feature(self, row, col):

        
        rec = self.filtered_data[row]
        geom = rec["geom"]
        
        if geom and not geom.isEmpty():
            canvas = self.iface.mapCanvas()
            canvas.setExtent(geom.boundingBox())
            canvas.refresh()
            self.flash_geometry(row)
    

    def open_pdf(self, row, col):
        # Column 3 = PDF click
        if col == 3:
            url = self.table.item(row, 3).data(Qt.ItemDataRole.UserRole)
            if url:
                import webbrowser
                webbrowser.open(url)
            return

    
    def select_fields(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Izberi iskalna polja")
        layout = QFormLayout(dlg)
        checkboxes = []
        
        for f in self.search_fields:
            cb = QCheckBox(f)
            cb.setChecked(f in self.active_fields)
            layout.addRow(cb)
            checkboxes.append(cb)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addRow(buttons)
        
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        
        if dlg.exec():
            self.active_fields = [cb.text() for cb in checkboxes if cb.isChecked()]
            if not self.active_fields:
                self.active_fields = list(self.search_fields)