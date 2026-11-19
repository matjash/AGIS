"""eArheologija and eVRD tabs: searchable tables, data from the CPA copy or geohub."""
import html
import webbrowser

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLineEdit, QMenu,
    QPushButton, QTabWidget, QTableWidget, QTableWidgetItem, QTextBrowser, QToolButton, QVBoxLayout, QWidget,
)
from qgis.core import (
    Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsGeometry, QgsProject, QgsTask,
)

from . import evidence
from .externals import log
from .tab_parcele import short, status_label

CRS = QgsCoordinateReferenceSystem("EPSG:3794")
ROLE = Qt.ItemDataRole.UserRole
MAX_COLUMN_WIDTH = 220
HIDDEN_DETAILS = {"OBJECTID", "SHAPE", "SHAPE_AREA", "SHAPE_LENGTH", "SHAPE.AREA", "SHAPE.LEN",
                  "SE_ANNO_CAD_DATA", "GLOBALID"}


def text(value):
    return "" if value is None else str(value)


class SizedTable(QTableWidget):
    """Table whose columns follow a layout: a fixed width in pixels (int) or a share
    of the remaining width (float), recalculated when the table is resized."""

    def __init__(self, columns, layout=None):
        super().__init__(0, columns)
        self.column_layout = layout or {}

    def apply_layout(self):
        if not self.column_layout:
            return
        fixed = {c: w for c, w in self.column_layout.items() if isinstance(w, int)}
        shares = {c: w for c, w in self.column_layout.items() if isinstance(w, float)}
        rest = max(0, self.viewport().width() - sum(fixed.values()))
        for c, w in fixed.items():
            self.setColumnWidth(c, w)
        for c, share in shares.items():
            self.setColumnWidth(c, int(rest * share))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.apply_layout()


class DataTab(QWidget):
    """One searchable table over rows from evidence.fetch()."""

    def __init__(self, iface, columns, search_fields, predicate=None, reports=False, title_fields=(),
                 details_label="Več informacij", column_layout=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.columns = columns                  # [(FIELD, header)]
        self.search_fields = search_fields      # [(FIELD, label)]
        self.predicate = predicate              # row -> bool, which rows belong to this table
        self.reports = reports
        self.title_fields = title_fields
        self.details_label = details_label
        self.data = None
        self.rows = []
        self.active_fields = {f for f, _ in search_fields}
        self._extent_ids = None                 # None = no extent filter
        self._geoms = {}
        self._tasks = set()

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.field_button = QToolButton()
        self.field_button.setText(self.tr("Polja"))
        self.field_button.setToolTip(self.tr("Po katerih poljih se išče"))
        self.field_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        fields_menu = QMenu(self.field_button)
        for f, label in search_fields:
            act = fields_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(True)
            act.toggled.connect(lambda on, f=f: self._toggle_field(f, on))
        self.field_button.setMenu(fields_menu)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(self.tr("Vnesite iskalni niz..."))
        self.search_bar.setClearButtonEnabled(True)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self.apply_filter)
        self.search_bar.textChanged.connect(lambda _t: self._search_timer.start())

        self.extent_button = QPushButton(self.tr("Le v obsegu karte"))
        self.extent_button.setCheckable(True)
        self.extent_button.toggled.connect(self._extent_toggled)
        self._extent_timer = QTimer(self)
        self._extent_timer.setSingleShot(True)
        self._extent_timer.setInterval(600)
        self._extent_timer.timeout.connect(self._query_extent)

        for w in (self.field_button, self.search_bar, self.extent_button):
            top.addWidget(w)
        layout.addLayout(top)

        self.status = status_label()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)

        self.table = SizedTable(len(columns), self._column_layout(column_layout))
        self.table.setHorizontalHeaderLabels([h for _, h in columns])
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        if self.table.column_layout:
            self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        vh = self.table.verticalHeader()
        vh.setVisible(False)
        vh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        vh.setDefaultSectionSize(self.fontMetrics().lineSpacing() * 2 + 8)     # two lines of text
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.cellDoubleClicked.connect(lambda row, _c: self.zoom_to(self._rec(row)))
        layout.addWidget(self.table)

    def _column_layout(self, spec):
        """spec: {column: "sample text" (fixed, fits the sample) or share (float)} -> pixels/shares."""
        if not spec:
            return {}
        out = {}
        for col, value in spec.items():
            if isinstance(value, str):
                out[col] = self.fontMetrics().horizontalAdvance(value) + 16
            else:
                out[col] = float(value)
        return out

    # ------------------------------------------------------------------ data

    def set_message(self, message):
        self.status.setText(message)

    def set_data(self, data):
        self.data = data
        self._geoms = {}
        self.rows = [r for r in data.rows if self.predicate is None or self.predicate(r)]
        t = self.table
        t.setSortingEnabled(False)
        t.clearContents()
        t.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            for col, (field, _h) in enumerate(self.columns):
                value = text(r.get(field))
                item = QTableWidgetItem(value)
                item.setData(ROLE, i)
                if len(value) > 25:
                    item.setToolTip(value)
                t.setItem(i, col, item)
        t.setSortingEnabled(True)
        if t.column_layout:
            t.apply_layout()
        else:
            t.resizeColumnsToContents()
            for col in range(len(self.columns) - 1):
                if t.columnWidth(col) > MAX_COLUMN_WIDTH:
                    t.setColumnWidth(col, MAX_COLUMN_WIDTH)
        if self.extent_button.isChecked():
            self._query_extent()
        self.apply_filter()

    def _rec(self, row):
        item = self.table.item(row, 0)
        return self.rows[item.data(ROLE)] if item is not None else None

    # ---------------------------------------------------------------- filter

    def _toggle_field(self, field, on):
        (self.active_fields.add if on else self.active_fields.discard)(field)
        self.apply_filter()

    def apply_filter(self, *_):
        if self.data is None:
            return
        needle = self.search_bar.text().strip().lower()
        fields = self.active_fields or {f for f, _ in self.search_fields}
        ids = self._extent_ids
        shown = 0
        for row in range(self.table.rowCount()):
            r = self._rec(row)
            hit = not needle or any(needle in text(r.get(f)).lower() for f in fields)
            if hit and ids is not None:
                hit = r.get(evidence.ID_FIELD) in ids
            self.table.setRowHidden(row, not hit)
            shown += hit
        self.status.setText(self.tr("Prikazanih: {} od {} · vir: {}").format(shown, len(self.rows), self.data.label))

    def _extent_toggled(self, on):
        canvas = self.iface.mapCanvas()
        if on:
            canvas.extentsChanged.connect(self._extent_timer.start)
            self._query_extent()
        else:
            try:
                canvas.extentsChanged.disconnect(self._extent_timer.start)
            except (TypeError, RuntimeError):
                pass
            self._extent_ids = None
            self.apply_filter()

    def _query_extent(self):
        if self.data is None or not self.extent_button.isChecked():
            return
        canvas = self.iface.mapCanvas()
        xf = QgsCoordinateTransform(canvas.mapSettings().destinationCrs(), CRS, QgsProject.instance())
        rect = xf.transformBoundingBox(canvas.extent())
        self.status.setText(self.tr("Iščem v obsegu karte…"))
        self._run("AGIS: obseg karte", evidence.ids_in_rect, self.data, rect, done=self._extent_result)

    def _extent_result(self, ids):
        self._extent_ids = ids or set()
        self.apply_filter()

    # ---------------------------------------------------------------- tasks

    def _run(self, description, fn, *args, done=None):
        def finished(exception, result=None):
            self._tasks.discard(task)
            if exception is not None:
                log(f"{description}: {exception}", Qgis.MessageLevel.Warning)
                self.status.setText(self.tr("Napaka: {}").format(short(exception)))
                return
            if done:
                done(result)

        task = QgsTask.fromFunction(description, fn, *args, on_finished=finished)
        self._tasks.add(task)
        QgsApplication.taskManager().addTask(task)
        return task

    # --------------------------------------------------------------- geometry

    def zoom_to(self, rec):
        if not rec:
            return
        rid = rec.get(evidence.ID_FIELD)
        if rid in self._geoms:
            self._zoom(self._geoms[rid])
            return
        self._run("AGIS: geometrija", evidence.geometries, self.data, [rid],
                  done=lambda geoms, rid=rid: self._got_geometry(rid, geoms))

    def _got_geometry(self, rid, geoms):
        geom = (geoms or {}).get(rid)
        if geom is None or geom.isEmpty():
            self.status.setText(self.tr("Zapis nima geometrije."))
            return
        self._geoms[rid] = geom
        self._zoom(geom)

    def _zoom(self, geom):
        canvas = self.iface.mapCanvas()
        xf = QgsCoordinateTransform(CRS, canvas.mapSettings().destinationCrs(), QgsProject.instance())
        box = xf.transformBoundingBox(geom.boundingBox())
        box.scale(1.3)
        canvas.setExtent(box)
        canvas.refresh()
        canvas.flashGeometries([QgsGeometry(geom)], CRS)

    # ------------------------------------------------------------------ menu

    def report_urls(self, rec):
        """[(label, url)] of the reports of a record (completed research only)."""
        if not self.reports or not rec:
            return []
        out = []
        for n in (1, 2):
            url = text(rec.get(f"URL_POROCILO{n}")).strip()
            if url:
                out.append((self.tr("Odpri poročilo {}").format(n), url))
        return out

    def show_context_menu(self, pos):
        rec = self._rec(self.table.rowAt(pos.y()))
        if not rec:
            return
        menu = QMenu(self.table)
        menu.addAction(self.tr(self.details_label)).triggered.connect(lambda: self.show_details(rec))
        menu.addAction(self.tr("Pokaži geometrijo")).triggered.connect(lambda: self.zoom_to(rec))
        reports = self.report_urls(rec)
        if reports:
            menu.addSeparator()
            for label, url in reports:
                menu.addAction(label).triggered.connect(lambda _c=False, u=url: webbrowser.open(u))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def details_html(self, rec):
        rows = []
        for key, value in rec.items():
            if key in HIDDEN_DETAILS or value in (None, ""):
                continue
            v = html.escape(text(value))
            if v.startswith(("http://", "https://")):
                v = f'<a href="{v}">{v}</a>'
            rows.append(f'<tr><td style="color:#555; padding-right:8px; white-space:nowrap;" valign="top">'
                        f'{html.escape(key)}</td><td>{v}</td></tr>')
        return f"<table cellspacing='2'>{''.join(rows)}</table>"

    def show_details(self, rec):
        title = next((text(rec.get(f)) for f in self.title_fields if rec.get(f)), self.tr(self.details_label))
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(520, 480)
        layout = QVBoxLayout(dlg)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(self.details_html(rec))         # QTextBrowser wraps long text to the window width
        layout.addWidget(browser)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        dlg.exec()


class EvidenceTab(QWidget):
    """Loads one dataset when first shown and gives it to its tables."""

    def __init__(self, iface, source, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.source = source
        self.tables = []
        self.data = None
        self._task = None
        self._loaded = False

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.reload()

    def reload(self):
        for t in self.tables:
            t.set_message(self.tr("Nalaganje…"))
        self._task = QgsTask.fromFunction(f"AGIS: {self.source.name}", evidence.fetch, self.source,
                                          on_finished=self._on_loaded)
        QgsApplication.taskManager().addTask(self._task)

    def _on_loaded(self, exception, data=None):
        self._task = None
        if exception is not None:
            log(f"{self.source.name}: {exception}", Qgis.MessageLevel.Warning)
            for t in self.tables:
                t.set_message(self.tr("Podatkov ni mogoče naložiti: ") + short(exception))
            self._loaded = False          # try again next time the tab is shown
            return
        self.data = data
        for t in self.tables:
            t.set_data(data)


def completed(row):
    return text(row.get("STATUS_SK")) == "zaključena"


class TabEarheologija(EvidenceTab):
    COLUMNS = [("KODA_RAZ", "Koda"), ("RAZ_POST", "Raziskovalni postopek"), ("IZVAJALEC", "Izvajalec")]
    SEARCH = [("KODA_RAZ", "Koda"), ("EID", "EID"), ("RAZ_POST", "Raziskovalni postopek"),
              ("IZVAJALEC", "Izvajalec"), ("PARCELE", "Parcele")]
    # Koda fits a code like 76-2344; the rest is shared 70 / 30
    LAYOUT = {0: "00-00000", 1: 0.7, 2: 0.3}

    def __init__(self, iface, parent=None):
        super().__init__(iface, evidence.RESEARCH, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget()
        self.done = DataTab(iface, self.COLUMNS, self.SEARCH, completed, reports=True, title_fields=("KODA_RAZ",),
                            column_layout=self.LAYOUT)
        self.ongoing = DataTab(iface, self.COLUMNS, self.SEARCH, lambda r: not completed(r),
                               title_fields=("KODA_RAZ",), column_layout=self.LAYOUT)
        tabs.addTab(self.done, self.tr("Zaključene raziskave"))
        tabs.addTab(self.ongoing, self.tr("Raziskave v teku"))
        layout.addWidget(tabs)
        self.tables = [self.done, self.ongoing]


class TabEvrd(EvidenceTab):
    COLUMNS = [("EID", "EID"), ("IME", "Ime"), ("REZIM", "Režim"), ("TIP", "Tip")]
    SEARCH = [("EID", "EID"), ("IME", "Ime"), ("REZIM", "Režim"), ("PODREZIM", "Podrežim"), ("TIP", "Tip"),
              ("NASELJE", "Naselje"), ("OBCINA", "Občina")]

    def __init__(self, iface, parent=None):
        super().__init__(iface, evidence.EVRD, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table_tab = DataTab(iface, self.COLUMNS, self.SEARCH, title_fields=("IME", "EID"),
                                 details_label="Podrobnosti")
        layout.addWidget(self.table_tab)
        self.tables = [self.table_tab]
