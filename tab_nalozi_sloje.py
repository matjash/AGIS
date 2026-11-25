"""'Naloži sloje' tab: one merged list of the CPA, official and own layer catalogues."""
from qgis.PyQt.QtCore import QEvent, QMimeData, QObject, QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QBrush, QColor, QDrag, QFont, QIcon, QPainter, QPixmap
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QMessageBox, QProgressBar,
    QSizePolicy, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)
from qgis.core import Qgis, QgsApplication, QgsSettings, QgsTask

from .catalogue import Catalogues, CatalogueError, download_official, export_catalogue, new_entry
from .catalogue_dialogs import DetailsDialog, EntryDialog, ExportDialog, LoginDialog
from .externals import cpa_available, log, pn_path
from . import reachability
from .qlr_tools import QlrError, check_qlr, describe, drop_position, export_nodes, load_qlr, tree_position, without_cpa_login
from .tab_nastavitve import official_catalogue_enabled

COLORS = {"cpa": "#2e7d32", "uradni": "#1565c0", "moji": "#ef6c00"}
TITLES = {"cpa": "Katalog CPA", "uradni": "Katalog AGIS", "moji": "Moji viri"}
ORDER = {"uradni": 0, "cpa": 1, "moji": 2}         # AGIS catalogue always on top
AGIS_ICON = "agis_small.png"                       # three dots: the AGIS catalogue
ROLE = Qt.ItemDataRole.UserRole
DRAG_MIME = "application/x-agis-catalogue"
KEY_HIDDEN_FOR_ME = "agis/skriti_viri"          # ids of entries this user has hidden for themselves
KEY_CATALOGUES_OFF = "agis/izklopljeni_katalogi"  # catalogue buttons switched off at the bottom
EDIT_RED = "#c62828"


def catalogues_off():
    return set(QgsSettings().value(KEY_CATALOGUES_OFF, [], type=list) or [])


def set_catalogue_off(key, off):
    keys = catalogues_off()
    (keys.add if off else keys.discard)(key)
    QgsSettings().setValue(KEY_CATALOGUES_OFF, sorted(keys))


def hidden_for_me():
    return set(QgsSettings().value(KEY_HIDDEN_FOR_ME, [], type=list) or [])


def set_hidden_for_me(entry_id, hidden):
    ids = hidden_for_me()
    (ids.add if hidden else ids.discard)(entry_id)
    QgsSettings().setValue(KEY_HIDDEN_FOR_ME, sorted(ids))


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


def stop_icon():
    """Red stop sign (icons/stop.png); Qt greys it out while the button is disabled."""
    return QIcon(str(pn_path("icons") / "stop.png"))


class ReachabilityTask(QgsTask):
    """Checks entries a few at a time and reports each one as soon as it is done."""

    entry_checked = pyqtSignal(str, object)

    def __init__(self, entries, workers=4):
        super().__init__("AGIS: dosegljivost virov", QgsTask.Flag.CanCancel)
        self.entries = entries
        self.workers = workers

    def run(self):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        done = 0
        pool = ThreadPoolExecutor(max_workers=self.workers)
        try:
            futures = {pool.submit(reachability.check_entry, e): e["id"] for e in self.entries}
            for future in as_completed(futures):
                if self.isCanceled():
                    return False
                try:
                    result = future.result()
                except Exception as ex:              # never stop the others
                    log(f"Preverjanje vira: {ex}", Qgis.MessageLevel.Info)
                    continue
                self.entry_checked.emit(futures[future], result)
                done += 1
                self.setProgress(done / len(self.entries) * 100)
            return True
        finally:
            pool.shutdown(wait=False, cancel_futures=True)


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
        self.edit_mode = False          # ✎ Urejanje: editing actions shown (never in the quick window)
        self._queue, self._total, self._done, self._loading = [], 0, 0, False
        self._target = None             # [group, index] where the next layer goes
        self.dragged = []
        self._by_id = {}                # every entry of the catalogues, by id (backup sources)
        self._reach = {}                # entry id -> (unreachable layers, number of layers)
        self._check_task = None
        self._download_task = None
        self._icons = {k: dot_icon(c) for k, c in COLORS.items()}
        self._icons["uradni"] = QIcon(str(pn_path("icons") / AGIS_ICON))

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(self.tr("Išči vire..."))
        self.search.textChanged.connect(self.filter_table)
        top.addWidget(self.search)

        def tool_button(icon, tip, slot=None, text=None):
            b = QToolButton()
            if icon:
                b.setIcon(QgsApplication.getThemeIcon(icon))
            if text:
                b.setText(text)
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.setIconSize(QSize(18, 18))
            b.setFixedSize(QSize(28, 28))
            if slot:
                b.clicked.connect(slot)
            top.addWidget(b)
            return b

        self.refresh_btn = tool_button("/mActionRefresh.svg",
                                       self.tr("Osveži kataloge ter ponovno preveri povezavo in dosegljivost virov"),
                                       self.refresh_all)
        self.cancel_btn = tool_button(None, self.tr("Ustavi nalaganje"), self.cancel_loading)
        self.cancel_btn.setIcon(stop_icon())
        self.cancel_btn.setEnabled(False)
        self.add_btn = tool_button("/symbologyAdd.svg",
                                   self.tr("Dodaj vir: izbrane sloje ali skupino iz panela Sloji shrani v katalog"),
                                   self.add_selected)
        self.edit_btn = tool_button("/mActionToggleEditing.svg", self.tr("Urejanje katalogov"))
        self.edit_btn.setCheckable(True)
        self.edit_btn.toggled.connect(self.set_edit_mode)
        self.more_btn = tool_button(None, self.tr("Več možnosti"), text="⋯")
        self.more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_btn.setStyleSheet("QToolButton::menu-indicator { image: none; }")
        more = QMenu(self.more_btn)
        self.hidden_action = more.addAction(self.tr("Pokaži skrite vire"))
        self.hidden_action.setCheckable(True)
        self.hidden_action.toggled.connect(self._toggle_hidden)
        self.export_action = more.addAction(self.tr("Izvozi katalog…"))
        self.export_action.triggered.connect(self.export_dialog)
        self.logout_action = more.addAction(self.tr("Odjava iz kataloga CPA"))
        self.logout_action.triggered.connect(self.logout_cpa)
        more.aboutToShow.connect(self._update_more_menu)
        self.more_btn.setMenu(more)
        layout.addLayout(top)
        self.add_btn.hide()                 # only in edit mode
        if compact:
            self.edit_btn.hide()
            self.more_btn.hide()

        # thin red line across the whole width while editing
        self.edit_line = QFrame()
        self.edit_line.setFixedHeight(2)
        self.edit_line.setStyleSheet(f"background-color: {EDIT_RED}; border: none;")
        self.edit_line.hide()
        layout.addWidget(self.edit_line)

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

        # one toggle button per catalogue: shows / hides all its rows
        chips = QHBoxLayout()
        chips.setSpacing(4)
        self.chips = {}
        for key in sorted(ORDER, key=ORDER.get):
            b = QToolButton()
            b.setCheckable(True)
            b.setChecked(key not in catalogues_off())
            b.setIcon(self._icons[key])
            b.setIconSize(QSize(11, 11))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setStyleSheet(
                "QToolButton { border: 1px solid #ccc; border-radius: 3px; padding: 1px 6px; color: #999; background: #f4f4f4; }"
                "QToolButton:checked { border: 1px solid #999; color: palette(text); background: palette(base); }"
                "QToolButton:disabled { color: #bbb; border-style: dashed; }")
            b.toggled.connect(lambda on, key=key: self._toggle_catalogue(key, on))
            chips.addWidget(b)
            self.chips[key] = b
        chips.addStretch()
        layout.addLayout(chips)

        self.status = QLabel()          # messages while checking / loading
        self.status.setStyleSheet("color: #666;")
        self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status.hide()
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
        if recheck:
            reachability.clear_cache()
            self._reach = {}
        include_hidden = True if self.show_hidden else {k for k in ORDER if self.editable(k)}
        listed = self.catalogues.entries(official_catalogue_enabled(), include_hidden=include_hidden)
        self._by_id = {e["id"]: e for e in listed}
        # an entry chosen as another listed entry's backup is not shown on its own (one level)
        used_as_backup = {e.get("nadomestni_id") for e in listed
                          if e.get("nadomestni_id") and e.get("nadomestni_id") != e["id"]}
        mine = hidden_for_me()
        for e in listed:
            e["skrit_zame"] = e["id"] in mine
        entries = [e for e in listed
                   if self.show_hidden or (e["id"] not in used_as_backup and not e["skrit_zame"])]

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
                "SKRIT (za vse)" if not e["omogocen"] else "",
                "SKRIT (samo zame)" if e.get("skrit_zame") else "",
                "",
                e.get("opis") or "",
            ]))
            for item in (icon_item, name, desc):
                item.setToolTip(tip)
                if not e["omogocen"] or e.get("skrit_zame"):
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

        self._counts = {k: sum(1 for e in entries if e["katalog"] == k) for k in ORDER}
        self.update_chips()

        self.apply_reachability()
        self.start_reachability_check()

        if recheck and self._on_refresh:
            self._on_refresh()

    # ----------------------------------------------------------- reachability

    def start_reachability_check(self):
        """Check every listed entry and its backup in the background; each row is
        marked as soon as its own check is done (results kept until ↺)."""
        todo = [e for e in self._by_id.values() if e["id"] not in self._reach]
        if not todo:
            return
        if self._check_task is not None:
            try:
                self._check_task.cancel()
            except RuntimeError:
                pass
        # rows in list order first, so the top of the list is marked first
        order = {self.entry(r)["id"]: r for r in range(self.table.rowCount()) if self.entry(r)}
        todo.sort(key=lambda e: order.get(e["id"], 10 ** 6))
        task = ReachabilityTask(todo)
        task.entry_checked.connect(self._entry_checked)
        task.taskCompleted.connect(lambda: self._task_done(task))
        task.taskTerminated.connect(lambda: self._task_done(task))
        self._check_task = task
        QgsApplication.taskManager().addTask(task)

    def _task_done(self, task):
        if self._check_task is task:
            self._check_task = None

    def _entry_checked(self, entry_id, result):
        self._reach[entry_id] = result
        try:
            # the entry itself, and every entry that uses it as a backup
            ids = {entry_id} | {e["id"] for e in self._by_id.values() if e.get("nadomestni_id") == entry_id}
            for row in range(self.table.rowCount()):
                e = self.entry(row)
                if e and e["id"] in ids:
                    self.apply_reachability(rows=[row])
        except RuntimeError:          # widget already deleted
            pass

    def source_status(self, e):
        """(status, note) of an entry: ok / backup / partial / none, or (None, "") if not checked yet."""
        if e["id"] not in self._reach:
            return None, ""
        missing, total = self._reach[e["id"]]
        if not missing:
            return "ok", ""
        reasons = "\n".join(f"• {name or '(sloj)'}: {why}" for name, why in missing)
        backup = self._by_id.get(e.get("nadomestni_id") or "")
        if backup is not None and backup["id"] != e["id"]:
            b_missing, _ = self._reach.get(backup["id"], (None, 0))
            if b_missing == []:
                return "backup", (f"Glavni vir ni dosegljiv:\n{reasons}\n"
                                  f"Naložen bo nadomestni vir: {backup['naziv']}")
        if len(missing) < total:
            return "partial", f"Ni dosegljivo:\n{reasons}"
        extra = f"\nTudi nadomestni vir »{backup['naziv']}« ni dosegljiv." if backup is not None else ""
        return "none", f"Vir ni dosegljiv:\n{reasons}{extra}"

    def apply_reachability(self, rows=None):
        """Red ! and a note for entries with unreachable layers; grey if nothing can be loaded."""
        red = QBrush(QColor("#c62828"))
        for row in (range(self.table.rowCount()) if rows is None else rows):
            e = self.entry(row)
            if not e:
                continue
            status, note = self.source_status(e)
            icon_item, name, desc = (self.table.item(row, c) for c in range(3))
            base = icon_item.data(ROLE + 1)
            if base is None:
                base = icon_item.toolTip()
                icon_item.setData(ROLE + 1, base)
            tip = base + (f"\n\n{note}" if note else "")
            icon_item.setText("!" if status in ("backup", "partial", "none") else "")
            icon_item.setForeground(red)
            for item in (icon_item, name, desc):
                item.setToolTip(tip)
            if e["omogocen"] and status == "none":
                name.setForeground(QBrush(QColor("#9e9e9e")))
                desc.setForeground(QBrush(QColor("#9e9e9e")))

    def refresh_all(self):
        self.reload(recheck=True)
        self.start_official_download()

    # kept for the dock's ↺ wiring and older callers
    def refresh_table(self, recheck=True):
        self.reload(recheck=recheck)

    def start_official_download(self):
        if not official_catalogue_enabled() or self._download_task is not None:
            return
        self._download_task = QgsTask.fromFunction("AGIS: katalog AGIS", download_official,
                                                   on_finished=self._downloaded)
        QgsApplication.taskManager().addTask(self._download_task)

    def _downloaded(self, exception, result=None):
        self._download_task = None
        if exception is not None:
            log(f"Kataloga AGIS ni bilo mogoče prenesti (uporabljam zadnjo kopijo): {exception}", Qgis.MessageLevel.Info)
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

    def filter_table(self, text=None):
        text = (self.search.text() if text is None else text).lower()
        off = {k for k, b in self.chips.items() if not b.isChecked()}
        for row in range(self.table.rowCount()):
            e = self.entry(row)
            hay = " ".join(str(e.get(k) or "") for k in ("naziv", "opis", "izvor", "oznake")).lower()
            self.table.setRowHidden(row, text not in hay or e["katalog"] in off)

    # ------------------------------------------------------- catalogue buttons

    def update_chips(self):
        counts = getattr(self, "_counts", {})
        for key, b in self.chips.items():
            b.setVisible(key != "cpa" or cpa_available())
            enabled = key != "uradni" or official_catalogue_enabled()
            b.setEnabled(enabled)
            pencil = "✎ " if self.editable(key) else ""
            b.setText(f"{pencil}{TITLES[key]} [{counts.get(key, 0)}]")
            if not enabled:
                tip = self.tr("Izklopljen v Nastavitvah")
            elif b.isChecked():
                tip = self.tr("Klik skrije vse vire iz kataloga »{}«").format(TITLES[key])
            else:
                tip = self.tr("Klik prikaže vire iz kataloga »{}«").format(TITLES[key])
            if self.editable(key):
                tip += "\n" + self.tr("Urejanje vključeno")
            b.setToolTip(tip)

    def _toggle_catalogue(self, key, on):
        set_catalogue_off(key, not on)
        self.update_chips()
        self.filter_table()

    # ------------------------------------------------------------ edit mode

    def editable(self, key):
        """Can entries of this catalogue be changed right now (edit mode on and rights)?"""
        if not self.edit_mode:
            return False
        if key == "moji":
            return True
        return key == "cpa" and cpa_available() and self.catalogues.cpa.logged_in()

    def set_edit_mode(self, on):
        """✎ Urejanje. On the CPA network the CPA login is asked once per QGIS session;
        without it (or without rights) only Moji viri can be edited."""
        if on and cpa_available() and not self.catalogues.cpa.logged_in():
            if not self._ask_cpa_login(own_only=True):
                self.edit_btn.blockSignals(True)
                self.edit_btn.setChecked(False)
                self.edit_btn.blockSignals(False)
                return
        self.edit_mode = on
        self.edit_line.setVisible(on)
        self.add_btn.setVisible(on)
        self._update_edit_tooltip()
        self.reload(recheck=False)

    def _ask_cpa_login(self, own_only=False):
        """Login dialog; True if editing may go on (logged in, or "Samo Moji viri")."""
        cat = self.catalogues.cpa
        dlg = LoginDialog(self, own_only=own_only)
        while True:
            result = dlg.exec()
            if result == LoginDialog.OWN_ONLY:
                return True
            if not result:
                return False
            try:
                cat.login(*dlg.credentials())
                return True
            except CatalogueError as e:
                dlg.show_error(str(e) + ("\n" + self.tr("Lahko urejate samo Moji viri.") if own_only else ""))

    def _update_edit_tooltip(self):
        if not self.edit_mode:
            self.edit_btn.setToolTip(self.tr("Urejanje katalogov (vklopi)"))
            return
        parts = []
        if self.editable("cpa"):
            parts.append(self.tr("Katalog CPA (kurator: {})").format(self.catalogues.cpa.user))
        parts.append(TITLES["moji"])
        self.edit_btn.setToolTip(self.tr("Urejanje: {}").format(", ".join(parts)) + "\n" + self.tr("Klik izklopi urejanje."))

    def logout_cpa(self):
        self.catalogues.cpa.logout()
        self._update_edit_tooltip()
        self.reload(recheck=False)

    def _update_more_menu(self):
        self.logout_action.setVisible(self.catalogues.cpa.logged_in())

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
        """Load one entry. Its sources are checked first (in the background, if that has not
        happened yet), and unreachable layers are left out before QGIS opens anything:
        QGIS opens web layers on the main thread, so a dead service would freeze QGIS."""
        if not self._loading:
            return
        needed = [e["id"]] + ([e["nadomestni_id"]] if e.get("nadomestni_id") in self._by_id else [])
        unchecked = [self._by_id.get(i, e) for i in needed if i not in self._reach]
        if unchecked:
            self.show_status(self.tr("Preverjam »{}« …").format(e["naziv"]))
            task = QgsTask.fromFunction(f"AGIS: preverjanje {e['naziv']}",
                                        lambda _t, items=unchecked: {x["id"]: reachability.check_entry(x) for x in items},
                                        on_finished=lambda exc, res=None, e=e: self._checked_then_load(e, exc, res))
            self._pending_check = task
            QgsApplication.taskManager().addTask(task)
            return
        try:
            group, index = self._target
            status, _note = self.source_status(e)
            entry, label = e, e["naziv"]
            if status == "backup":
                entry = self._by_id[e["nadomestni_id"]]
                self._message(f"»{label}«: glavni vir ni dosegljiv, naložen nadomestni vir »{entry['naziv']}«.",
                              Qgis.MessageLevel.Info)
            missing, total = self._reach.get(entry["id"], ([], 0))
            # Layers whose server does not answer at all would freeze QGIS until a timeout:
            # those are left out. Every other broken layer is loaded and shown as unavailable,
            # so the group stays complete and the source can be fixed or comes back later.
            left_out = [name for name, why in missing if reachability.blocks_qgis(why)]
            broken = [name for name, why in missing if not reachability.blocks_qgis(why)]
            if total and len(left_out) == total:
                self._message(f"»{label}«: strežnik se ne odziva, vir ni naložen.", Qgis.MessageLevel.Warning)
            else:
                qlr = reachability.without_layers(entry["qlr"], left_out) if left_out else entry["qlr"]
                self._target[1] = index + load_qlr(qlr, group=group, index=index)
                notes = []
                if broken:
                    notes.append(f"naloženi, a nedosegljivi: {', '.join(broken)}")
                if left_out:
                    notes.append(f"izpuščeni (strežnik se ne odziva): {', '.join(left_out)}")
                if notes:
                    self._message(f"»{label}«: " + "; ".join(notes), Qgis.MessageLevel.Warning)
        except Exception as ex:
            log(f"{e['naziv']}: {ex}", Qgis.MessageLevel.Critical)
            self._message(f"»{e['naziv']}« ni bilo mogoče naložiti: {ex}", Qgis.MessageLevel.Warning)
        self._done += 1
        self.progress.setValue(int(self._done / self._total * 100))
        self._next()

    def _checked_then_load(self, e, exception, result):
        self._pending_check = None
        if exception is None and result:
            self._reach.update(result)
            try:
                self.apply_reachability()
            except RuntimeError:
                return
        if not self._loading:
            return
        if exception is not None:                      # check failed: mark as checked, load as is
            self._reach.setdefault(e["id"], ([], 0))
        self._load_one(e)

    def _finish(self):
        self._stop()
        self.progress.setValue(100)
        QTimer.singleShot(500, lambda: self.progress.setValue(0))

    def cancel_loading(self):
        """Stop after the layer that is being opened right now."""
        self._queue = []
        if getattr(self, "_pending_check", None) is not None:
            try:
                self._pending_check.cancel()
            except RuntimeError:
                pass
            self._pending_check = None
        self._message(self.tr("Nalaganje ustavljeno."), Qgis.MessageLevel.Info)
        self._stop()
        self.progress.setValue(0)

    def _stop(self):
        self._loading = False
        self.show_status("")
        self.cancel_btn.setEnabled(False)
        canvas = self.iface.mapCanvas()
        canvas.freeze(False)
        canvas.refresh()

    def show_status(self, text):
        self.status.setText(text)
        self.status.setVisible(bool(text))

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
        if self.editable("cpa"):
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

    def hide_for_me(self, e, hidden):
        """Hide/show an entry of any catalogue, only on this computer (QGIS settings)."""
        set_hidden_for_me(e["id"], hidden)
        self.reload(recheck=False)

    def backup_choices(self, e):
        """[(label, id)] of the entries that can be the backup of e (any catalogue, not e itself)."""
        out = [(self.tr("(brez nadomestnega vira)"), None)]
        for other in sorted(self._by_id.values(), key=lambda x: (ORDER[x["katalog"]], (x["naziv"] or "").lower())):
            if other["id"] != e["id"]:
                out.append((f"{other['naziv']} ({TITLES[other['katalog']]})", other["id"]))
        return out

    def choose_backup(self, e):
        from qgis.PyQt.QtWidgets import QInputDialog
        choices = self.backup_choices(e)
        labels = [c[0] for c in choices]
        current = next((i for i, c in enumerate(choices) if c[1] == e.get("nadomestni_id")), 0)
        label, ok = QInputDialog.getItem(
            self, self.tr("Nadomestni vir"),
            self.tr("Ko »{}« ni dosegljiv, naloži:").format(e["naziv"]), labels, current, False)
        if ok:
            self.set_backup(e, dict(choices)[label])

    def set_backup(self, e, backup_id):
        return self._run(e, "update", nadomestni_id=backup_id)

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

    def show_details(self, e):
        backup = self._by_id.get(e.get("nadomestni_id") or "")
        _status, note = self.source_status(e)
        DetailsDialog(e, TITLES[e["katalog"]], reachability.layers_of(without_cpa_login(e["qlr"])),
                      backup_name=f"{backup['naziv']} ({TITLES[backup['katalog']]})" if backup else None,
                      note=note, parent=self).exec()

    def delete_entry(self, e):
        users = [x["naziv"] for x in self._by_id.values() if x.get("nadomestni_id") == e["id"] and x["id"] != e["id"]]
        text = self.tr("Izbrišem vir »{}« iz kataloga {}?").format(e["naziv"], TITLES[e["katalog"]])
        if users:
            text += "\n\n" + self.tr("Vir je nadomestni za: {}. Ta vnos bo ostal brez nadomestnega.").format(", ".join(users))
        return self._run(e, "delete", confirm=text)

    def copy_to_own(self, e):
        values = {k: e.get(k) for k in ("naziv", "opis", "izvor", "vidnost", "kategorija", "oznake", "vrstni_red")}
        return self.add_entry("moji", values, without_cpa_login(e["qlr"]))

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
        """Actions for the clicked source. Changing a catalogue needs ✎ Urejanje
        (and for the CPA catalogue a login with write rights)."""
        row = self.table.rowAt(pos.y())
        e = self.entry(row) if row >= 0 else None
        if not e:
            return
        menu = QMenu(self)
        menu.addAction(self.tr("Naloži")).triggered.connect(lambda: self.load(self.selected_entries() or [e]))
        menu.addAction(self.tr("Podrobnosti…")).triggered.connect(lambda: self.show_details(e))
        if not self.compact:
            editable = self.editable(e["katalog"])
            menu.addSeparator()
            if not (editable and e["katalog"] == "moji"):
                if e.get("skrit_zame"):
                    menu.addAction(self.tr("Prikaži (samo zame)")).triggered.connect(lambda: self.hide_for_me(e, False))
                else:
                    menu.addAction(self.tr("Skrij (samo zame)")).triggered.connect(lambda: self.hide_for_me(e, True))
            if e["katalog"] != "moji":
                menu.addAction(self.tr("Kopiraj v Moji viri")).triggered.connect(lambda: self.copy_to_own(e))
            if editable:
                menu.addSeparator()
                menu.addAction(self.tr("Uredi podatke…")).triggered.connect(lambda: self.edit_entry(e))
                menu.addAction(self.tr("Zamenjaj z izbranim")).triggered.connect(lambda: self.replace_entry(e))
                menu.addAction(self.tr("Nadomestni vir…")).triggered.connect(lambda: self.choose_backup(e))
                undo = menu.addAction(self.tr("Razveljavi zadnjo zamenjavo"))
                undo.setEnabled(bool(e.get("ima_prejsnji")))
                undo.triggered.connect(lambda: self._run(e, "undo"))
                own = e["katalog"] == "moji"
                if e["omogocen"]:
                    menu.addAction(self.tr("Skrij") if own else self.tr("Skrij za vse")
                                   ).triggered.connect(lambda: self._run(e, "set_enabled", False))
                else:
                    menu.addAction(self.tr("Prikaži") if own else self.tr("Prikaži za vse")
                                   ).triggered.connect(lambda: self._run(e, "set_enabled", True))
                delete = menu.addAction(self.tr("Izbriši…"))
                delete.triggered.connect(lambda: self.delete_entry(e))
                if not own and not self.catalogues.cpa.can_delete:
                    delete.setEnabled(False)
                    delete.setToolTip(self.tr("Ta prijava nima pravice brisati – vir lahko skrijete za vse."))
                    menu.setToolTipsVisible(True)
        menu.exec(self.table.viewport().mapToGlobal(pos))
