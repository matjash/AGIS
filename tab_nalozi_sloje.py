"""'Naloži sloje' tab: one merged list of the CPA, official and own layer catalogues."""
from qgis.PyQt.QtCore import QEvent, QMimeData, QObject, Qt, QTimer
from qgis.PyQt.QtGui import QBrush, QColor, QDrag, QFont, QIcon, QPainter, QPixmap
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QMessageBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)
from qgis.core import Qgis, QgsApplication, QgsTask

from .catalogue import Catalogues, CatalogueError, download_official, export_catalogue, new_entry
from .catalogue_dialogs import EntryDialog, ExportDialog, LoginDialog
from .externals import cpa_available, log, pn_path
from .qlr_tools import QlrError, check_qlr, describe, drop_position, export_nodes, load_qlr, tree_position
from .tab_nastavitve import official_catalogue_enabled

COLORS = {"cpa": "#2e7d32", "uradni": "#1565c0", "moji": "#ef6c00"}
TITLES = {"cpa": "Katalog CPA", "uradni": "Katalog AGIS", "moji": "Moji viri"}
ORDER = {"uradni": 0, "cpa": 1, "moji": 2}         # AGIS catalogue always on top
AGIS_ICON = "agis_small.png"                       # three dots: the AGIS catalogue
ROLE = Qt.ItemDataRole.UserRole
DRAG_MIME = "application/x-agis-catalogue"


def dot_icon(color):
    pix = QPixmap(14, 14)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, 10, 10)
    p.end()
    return QIcon(pix)


class SortItem(QTableWidgetItem):
    def __init__(self, key):
        super().__init__()
        self.key = key

    def __lt__(self, other):
        return self.key < other.key if isinstance(other, SortItem) else super().__lt__(other)


class CatalogueTable(QTableWidget):
    """Catalogue list; rows can be dragged into the QGIS Layers panel."""

    def __init__(self, tab):
        super().__init__(0, 3)
        self.tab = tab
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def startDrag(self, actions):
        entries = self.tab.selected_entries()
        if not entries:
            return
        self.tab.dragged = entries
        mime = QMimeData()
        mime.setData(DRAG_MIME, b"1")
        mime.setText("\n".join(e["naziv"] or "" for e in entries))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)
        self.tab.dragged = []


class LayerTreeDrop(QObject):
    """Event filter on the Layers panel: accepts catalogue rows and loads them where dropped."""

    def __init__(self, tab, view):
        super().__init__(tab)
        self.tab = tab
        self.view = view

    def eventFilter(self, obj, event):
        t = event.type()
        if t in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop):
            mime = event.mimeData()
            if mime is None or not mime.hasFormat(DRAG_MIME) or not self.tab.dragged:
                return False
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            if t == QEvent.Type.Drop:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                entries = list(self.tab.dragged)
                position = drop_position(self.view, pos)
                QTimer.singleShot(0, lambda: self.tab.load(entries, position))
            return True
        return False


class TabNaloziSloje(QWidget):

    def __init__(self, iface=None, on_refresh=None, compact=False, parent=None):
        """compact=True: only search and load (the quick window from the toolbar)."""
        super().__init__(parent)
        self.iface = iface
        self.compact = compact
        self._on_refresh = on_refresh
        self.catalogues = Catalogues()
        self.show_hidden = False
        self._queue, self._total, self._done, self._loading = [], 0, 0, False
        self._target = None             # [group, index] where the next layer goes
        self.dragged = []
        self._download_task = None
        self._icons = {k: dot_icon(c) for k, c in COLORS.items()}
        self._icons["uradni"] = QIcon(str(pn_path("icons") / AGIS_ICON))

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(self.tr("Išči vire..."))
        self.search.textChanged.connect(self.filter_table)
        top.addWidget(self.search)

        self.add_btn = QToolButton()
        self.add_btn.setText("+")
        self.add_btn.setToolTip(self.tr("Dodaj izbrane sloje/skupine iz panela Sloji v katalog"))
        self.add_btn.clicked.connect(self.add_selected)
        top.addWidget(self.add_btn)

        self.refresh_btn = QToolButton()
        self.refresh_btn.setIcon(QIcon(str(pn_path("icons") / "refresh.png")))
        self.refresh_btn.setToolTip(self.tr("Osveži kataloge in ponovno preveri povezavo z bazo CPA"))
        self.refresh_btn.clicked.connect(self.refresh_all)
        top.addWidget(self.refresh_btn)

        self.cancel_btn = QToolButton()
        self.cancel_btn.setText("✕")
        self.cancel_btn.setToolTip(self.tr("Prekini nalaganje"))
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_loading)
        top.addWidget(self.cancel_btn)

        self.more_btn = QToolButton()
        self.more_btn.setText("⋯")
        self.more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more = QMenu(self.more_btn)
        self.hidden_action = more.addAction(self.tr("Pokaži skrite vire"))
        self.hidden_action.setCheckable(True)
        self.hidden_action.toggled.connect(self._toggle_hidden)
        more.addAction(self.tr("Izvozi kot katalog…")).triggered.connect(self.export_dialog)
        self.more_btn.setMenu(more)
        top.addWidget(self.more_btn)
        layout.addLayout(top)
        if compact:
            self.add_btn.hide()
            self.more_btn.hide()

        self.progress = QProgressBar()
        self.progress.setFixedHeight(3)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("QProgressBar {border: none; background: #eee;}"
                                    "QProgressBar::chunk {background-color: #4caf50;}")
        layout.addWidget(self.progress)

        self.table = CatalogueTable(self)
        self.table.setHorizontalHeaderLabels(["", self.tr("Naziv"), self.tr("Opis")])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.cellDoubleClicked.connect(lambda row, _c: self.load([self.entry(row)]))
        layout.addWidget(self.table)

        self.status = QLabel()
        self.status.setStyleSheet("color: #666;")
        layout.addWidget(self.status)

        self.reload(recheck=False)
        if not compact:
            self.start_official_download()

        # Drag and drop into the Layers panel
        self._drop_filter = None
        view = self.iface.layerTreeView() if self.iface is not None else None
        if view is not None and hasattr(view, "viewport"):
            try:
                self._drop_filter = LayerTreeDrop(self, view)
                view.viewport().installEventFilter(self._drop_filter)
                view.viewport().setAcceptDrops(True)
            except TypeError:           # test doubles
                self._drop_filter = None

    # ------------------------------------------------------------------ data

    def reload(self, recheck=True):
        if recheck:
            cpa_available(refresh=True)
        entries = self.catalogues.entries(official_catalogue_enabled(), include_hidden=self.show_hidden)

        t = self.table
        t.setSortingEnabled(False)
        t.clearContents()
        t.setRowCount(len(entries))
        bold = QFont()
        for row, e in enumerate(entries):
            kind, n_layers = describe(e["qlr"] or "")
            icon_item = SortItem((ORDER[e["katalog"]], e.get("vrstni_red") or 0, (e["naziv"] or "").lower()))
            icon_item.setIcon(self._icons[e["katalog"]])
            icon_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            name = QTableWidgetItem(e["naziv"] or "")
            name.setData(ROLE, e)
            desc = QTableWidgetItem(e.get("opis") or "")
            tip = "\n".join(filter(None, [
                f"{e['naziv']}",
                f"Katalog: {TITLES[e['katalog']]}",
                f"Izvor: {e['izvor']}" if e.get("izvor") else "",
                f"Oznake: {e['oznake']}" if e.get("oznake") else "",
                f"Vsebina: skupina, {n_layers} slojev" if kind == "skupina" else "",
                "SKRIT" if not e["omogocen"] else "",
                "",
                e.get("opis") or "",
            ]))
            for item in (icon_item, name, desc):
                item.setToolTip(tip)
                if not e["omogocen"]:
                    item.setForeground(QBrush(QColor("#999")))
                    f = QFont(bold)
                    f.setItalic(True)
                    item.setFont(f)
            t.setItem(row, 0, icon_item)
            t.setItem(row, 1, name)
            t.setItem(row, 2, desc)
        t.setSortingEnabled(True)
        t.sortItems(0, Qt.SortOrder.AscendingOrder)
        self.filter_table(self.search.text())

        counts = {k: sum(1 for e in entries if e["katalog"] == k) for k in ORDER}
        parts = []
        for k in ORDER:
            if k == "cpa" and not cpa_available():
                continue
            if k == "uradni" and not official_catalogue_enabled():
                parts.append(self.tr("katalog AGIS izklopljen"))
                continue
            if k == "uradni":
                mark = f'<img src="{(pn_path("icons") / AGIS_ICON).as_posix()}" width="11" height="11">'
            else:
                mark = f'<span style="color:{COLORS[k]}">●</span>'
            parts.append(f'{mark} {TITLES[k]}: {counts[k]}')
        self.status.setText(" · ".join(parts))

        if recheck and self._on_refresh:
            self._on_refresh()

    def refresh_all(self):
        self.reload(recheck=True)
        self.start_official_download()

    # kept for the dock's ↺ wiring and older callers
    def refresh_table(self, recheck=True):
        self.reload(recheck=recheck)

    def start_official_download(self):
        if not official_catalogue_enabled() or self._download_task is not None:
            return
        self._download_task = QgsTask.fromFunction("AGIS: uradni katalog", download_official,
                                                   on_finished=self._downloaded)
        QgsApplication.taskManager().addTask(self._download_task)

    def _downloaded(self, exception, result=None):
        self._download_task = None
        if exception is not None:
            log(f"Uradnega kataloga ni bilo mogoče prenesti (uporabljam zadnjo kopijo): {exception}", Qgis.MessageLevel.Info)
            return
        try:
            self.reload(recheck=False)
        except RuntimeError:          # widget already deleted
            pass

    def _toggle_hidden(self, on):
        self.show_hidden = on
        self.reload(recheck=False)

    def entry(self, row):
        item = self.table.item(row, 1)
        return item.data(ROLE) if item else None

    def selected_entries(self):
        return [self.entry(i.row()) for i in self.table.selectionModel().selectedRows()]

    def filter_table(self, text):
        text = text.lower()
        for row in range(self.table.rowCount()):
            e = self.entry(row)
            hay = " ".join(str(e.get(k) or "") for k in ("naziv", "opis", "izvor", "oznake")).lower()
            self.table.setRowHidden(row, text not in hay)

    # --------------------------------------------------------------- loading

    def load(self, entries, position=None):
        """Load entries one after another; position = (group, index) in the layer tree,
        default: above the selected layer / at the top of the selected group / at the top."""
        entries = [e for e in entries if e]
        if not entries or self._loading:
            return
        if position is None:
            try:
                position = tree_position(self.iface.layerTreeView())
            except Exception:
                position = (None, 0)
        self._target = list(position)
        self._queue = list(entries)
        self._total, self._done = len(entries), 0
        self._loading = True
        self.cancel_btn.setEnabled(True)
        self.progress.setValue(5)
        self.iface.mapCanvas().freeze(True)
        self._next()

    def _next(self):
        if not self._loading:
            return
        if not self._queue:
            self._finish()
            return
        e = self._queue.pop(0)
        QTimer.singleShot(30, lambda e=e: self._load_one(e))

    def _load_one(self, e):
        try:
            group, index = self._target
            self._target[1] = index + load_qlr(e["qlr"], group=group, index=index)
        except Exception as ex:
            log(f"{e['naziv']}: {ex}", Qgis.MessageLevel.Critical)
            self._message(f"»{e['naziv']}« ni bilo mogoče naložiti: {ex}", Qgis.MessageLevel.Warning)
        finally:
            self._done += 1
            self.progress.setValue(int(self._done / self._total * 100))
            self._next()

    def _finish(self):
        self._stop()
        self.progress.setValue(100)
        QTimer.singleShot(500, lambda: self.progress.setValue(0))

    def cancel_loading(self):
        self._queue = []
        self._stop()
        self.progress.setValue(0)

    def _stop(self):
        self._loading = False
        self.cancel_btn.setEnabled(False)
        canvas = self.iface.mapCanvas()
        canvas.freeze(False)
        canvas.refresh()

    # --------------------------------------------------------- catalogue work
    # Each action has a dialog-free core (used by the tests) and a dialog wrapper.

    def _message(self, text, level=Qgis.MessageLevel.Info):
        try:
            self.iface.messageBar().pushMessage("AGIS", text, level, 6)
        except Exception:
            log(text, level)

    def selected_layer_nodes(self):
        return list(self.iface.layerTreeView().selectedNodes(True))

    def ensure_login(self, cat):
        """Ask for the CPA login if needed. True if writing is possible."""
        if not cat.needs_login or cat.logged_in():
            return True
        dlg = LoginDialog(self)
        while dlg.exec():
            try:
                cat.login(*dlg.credentials())
                return True
            except CatalogueError as e:
                dlg.show_error(str(e))
        return False

    def prepare_qlr(self, nodes):
        """QLR for the selected nodes, checked. Returns (qlr, warnings); raises QlrError on errors."""
        clean, warnings, errors = check_qlr(export_nodes(nodes))
        if errors:
            raise QlrError("\n".join(errors))
        return clean, warnings

    def add_entry(self, target_key, values, qlr):
        cat = self.catalogues.by_key(target_key)
        entry = new_entry(qlr=qlr, **values)
        cat.add(entry)
        self.reload(recheck=False)
        return entry

    def add_selected(self):
        nodes = self.selected_layer_nodes()
        if not nodes:
            QMessageBox.information(self, "AGIS", self.tr("V panelu Sloji najprej izberite sloj ali skupino."))
            return
        try:
            qlr, warnings = self.prepare_qlr(nodes)
        except QlrError as e:
            QMessageBox.warning(self, "AGIS", self.tr("Tega ni mogoče dodati v katalog:\n\n") + str(e))
            return
        targets = [("moji", TITLES["moji"])]
        if cpa_available():
            targets.append(("cpa", TITLES["cpa"]))
        default = {"naziv": nodes[0].name() if len(nodes) == 1 else ""}
        dlg = EntryDialog(default, targets=targets, warnings=warnings, title=self.tr("Dodaj v katalog"), parent=self)
        if not dlg.exec():
            return
        cat = self.catalogues.by_key(dlg.target_key())
        if not self.ensure_login(cat):
            return
        try:
            self.add_entry(dlg.target_key(), dlg.values(), qlr)
            self._message(self.tr("Dodano v {}: {}").format(TITLES[cat.key], dlg.values()["naziv"]), Qgis.MessageLevel.Success)
        except CatalogueError as e:
            QMessageBox.warning(self, "AGIS", str(e))

    def _run(self, e, action, *args, confirm=None, **kwargs):
        """Run a write action on the entry's catalogue, with login and error handling."""
        cat = self.catalogues.by_key(e["katalog"])
        if confirm and QMessageBox.question(self, "AGIS", confirm) != QMessageBox.StandardButton.Yes:
            return False
        if not self.ensure_login(cat):
            return False
        try:
            getattr(cat, action)(e["id"], *args, **kwargs)
        except CatalogueError as ex:
            QMessageBox.warning(self, "AGIS", str(ex))
            return False
        self.reload(recheck=False)
        return True

    def edit_entry(self, e):
        dlg = EntryDialog(e, title=self.tr("Uredi podatke vira"), parent=self)
        if dlg.exec():
            self._run(e, "update", **dlg.values())

    def replace_entry(self, e):
        nodes = self.selected_layer_nodes()
        if not nodes:
            QMessageBox.information(self, "AGIS", self.tr("V panelu Sloji najprej izberite nov sloj ali skupino."))
            return
        try:
            qlr, warnings = self.prepare_qlr(nodes)
        except QlrError as ex:
            QMessageBox.warning(self, "AGIS", str(ex))
            return
        text = self.tr("Zamenjam vsebino vira »{}« z izbranimi sloji? Prejšnjo različico lahko obnovite.").format(e["naziv"])
        if warnings:
            text += "\n\n" + "\n".join("• " + w for w in warnings)
        self._run(e, "replace_qlr", qlr, confirm=text)

    def copy_to_own(self, e):
        values = {k: e.get(k) for k in ("naziv", "opis", "izvor", "vidnost", "kategorija", "oznake", "vrstni_red")}
        return self.add_entry("moji", values, e["qlr"])

    def export_dialog(self):
        entries = self.catalogues.entries(official_catalogue_enabled(), include_hidden=True)
        dlg = ExportDialog(entries, self)
        if not dlg.exec():
            return
        selected = dlg.selected()
        path = ExportDialog.ask_path(self)
        if selected and path:
            export_catalogue(selected, path)
            self._message(self.tr("Izvoženih virov: {} → {}").format(len(selected), path), Qgis.MessageLevel.Success)

    # ------------------------------------------------------------------ menu

    def show_context_menu(self, pos):
        """Actions for the clicked source (showing hidden sources and export are in the ⋯ button)."""
        row = self.table.rowAt(pos.y())
        e = self.entry(row) if row >= 0 else None
        if not e:
            return
        menu = QMenu(self)
        menu.addAction(self.tr("Naloži")).triggered.connect(lambda: self.load(self.selected_entries() or [e]))
        if not self.compact:
            cat = self.catalogues.by_key(e["katalog"])
            menu.addSeparator()
            if cat.writable:
                menu.addAction(self.tr("Uredi podatke…")).triggered.connect(lambda: self.edit_entry(e))
                menu.addAction(self.tr("Zamenjaj z izbranim")).triggered.connect(lambda: self.replace_entry(e))
                undo = menu.addAction(self.tr("Razveljavi zadnjo zamenjavo"))
                undo.setEnabled(bool(e.get("ima_prejsnji")))
                undo.triggered.connect(lambda: self._run(e, "undo"))
                if e["omogocen"]:
                    menu.addAction(self.tr("Skrij")).triggered.connect(lambda: self._run(e, "set_enabled", False))
                else:
                    menu.addAction(self.tr("Prikaži")).triggered.connect(lambda: self._run(e, "set_enabled", True))
                if e["katalog"] == "moji":
                    menu.addAction(self.tr("Izbriši")).triggered.connect(
                        lambda: self._run(e, "delete", confirm=self.tr("Izbrišem vir »{}«?").format(e["naziv"])))
            if e["katalog"] != "moji":
                menu.addAction(self.tr("Kopiraj v Moji viri")).triggered.connect(lambda: self.copy_to_own(e))
        menu.exec(self.table.viewport().mapToGlobal(pos))
