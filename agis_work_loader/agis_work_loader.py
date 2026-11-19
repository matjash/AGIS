"""'Naloži delovne sloje': CPA work layers, loaded with the user's own login.

1. Login once per QGIS session (typed user/password or a saved QGIS login).
   A typed login is stored as a temporary QGIS login named "AGIS začasno (…)";
   it must stay while the layers are open (QGIS reconnects with it), so it is
   removed when AGIS is unloaded / QGIS closes.
2. A window lists the work layers of "Delovno"."Delovni sloji" (without the
   'admin' rows): search, double-click, drag into the Layers panel, Naloži vse.
   Layers the login cannot read are greyed out.
3. Styles come from the database (default style in public.layer_styles). If a
   drop-down (Value Relation) reads from another table that is not loaded, that
   table is loaded too, into the same group.
4. After login, layers of an earlier session (saved project) whose temporary
   login no longer exists are reconnected with the new login.
"""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QBrush, QColor
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu,
    QMessageBox, QPushButton, QTableWidgetItem, QVBoxLayout,
)
from qgis.PyQt.QtGui import QPixmap
from qgis.core import (Qgis, QgsApplication, QgsAuthMethodConfig, QgsDataSourceUri, QgsEditorWidgetSetup,
                       QgsProject, QgsProviderConnectionException, QgsSettings, QgsVectorLayer)

from .. import config
from ..externals import cpa_connection, cpa_uri, log, pg_ident, pg_literal, pn_path, sql_value
from ..qlr_tools import tree_position
from .agis_work_loader_dialog import ArheoloskiGisWorkLoaderDialog

GROUP = "Delovni sloji"
TEMP_LOGIN_PREFIX = "AGIS začasno ("
LIST_TABLE = ("Delovno", "Delovni sloji")
GREY = QColor("#9e9e9e")

# The ZLS interpretation's drop-down, used when its default style does not have it:
# "Vrsta" from the category table, only the types of the feature's current "Sloj".
ZLS_LAYER = "ZLS Interpretacija_delovno"
ZLS_CATEGORIES = ("ZLS", "ZLS interpretacija_kategorije", "id_kat")

_session = {"authcfg": None, "user": None}     # login of this QGIS session


# ---------------------------------------------------------------------------
# Logins
# ---------------------------------------------------------------------------
def remove_temporary_logins():
    """Remove the temporary logins created for work layers (when AGIS is unloaded)."""
    mgr = QgsApplication.authManager()
    try:
        configs = mgr.availableAuthMethodConfigs()
    except Exception:
        return
    for config_id, cfg in configs.items():
        if cfg.name().startswith(TEMP_LOGIN_PREFIX):
            mgr.removeAuthenticationConfig(config_id)
    _session.update(authcfg=None, user=None)


def store_temporary_login(user, password):
    mgr = QgsApplication.authManager()
    cfg = QgsAuthMethodConfig()
    cfg.setName(f"{TEMP_LOGIN_PREFIX}{user})")
    cfg.setMethod("Basic")
    cfg.setConfig("username", user)
    cfg.setConfig("password", password)
    stored = mgr.storeAuthenticationConfig(cfg)
    if isinstance(stored, tuple):           # newer QGIS returns (ok, config)
        ok, cfg = stored[0], (stored[1] if len(stored) > 1 else cfg)
    else:
        ok = stored
    return cfg.id() if ok and cfg.id() else None


def login(user, password, saved_authcfg):
    """Check a login exactly as the layers will connect with it.
    Returns (authcfg, None) or (None, message)."""
    mgr = QgsApplication.authManager()
    temp_id = None
    if user:
        temp_id = store_temporary_login(user, password)
        if not temp_id:
            return None, "Začasne prijave ni bilo mogoče shraniti (je glavno geslo QGIS odklenjeno?)."
        authcfg = temp_id
    elif saved_authcfg:
        authcfg = saved_authcfg
    else:
        return None, "Vpišite uporabniško ime in geslo ali izberite shranjeno prijavo."
    try:
        cpa_connection(authcfg=authcfg)
    except QgsProviderConnectionException as e:
        log(f"Delovni sloji: {e}", Qgis.MessageLevel.Warning)
        if temp_id:
            mgr.removeAuthenticationConfig(temp_id)
        return None, ("Prijava v bazo CPA ni uspela – napačno uporabniško ime ali geslo"
                      + ("" if user else " v shranjeni prijavi") + ".")
    if not user:
        cfg = QgsAuthMethodConfig()
        mgr.loadAuthenticationConfig(authcfg, cfg, True)
        user = cfg.config("username") or ""
    _session.update(authcfg=authcfg, user=user)
    return authcfg, None


# ---------------------------------------------------------------------------
# Work layer list and loading
# ---------------------------------------------------------------------------
def work_layer_rows(authcfg):
    """Rows of "Delovno"."Delovni sloji" (without 'admin'), read with the shared cpa account,
    and whether the user's login can read each (True / False / None = table missing)."""
    t = pg_ident(*LIST_TABLE)
    rows = []
    for sloj, shema, geom, key in cpa_connection().executeSql(
            f'SELECT sloj, shema, geometija, "id stolpec" FROM {t} '
            f"WHERE coalesce(pravice, '') <> 'admin' ORDER BY sloj"):
        rows.append({"naziv": sql_value(sloj), "shema": sql_value(shema), "geom": sql_value(geom) or None,
                     "key": sql_value(key) or "", "readable": None})
    if rows:
        values = ", ".join(f"({i}, {pg_literal(pg_ident(r['shema'], r['naziv']))})" for i, r in enumerate(rows))
        sql = (f"SELECT i, CASE WHEN to_regclass(n) IS NULL THEN NULL "
               f"ELSE has_table_privilege(n, 'SELECT') END FROM (VALUES {values}) AS v(i, n)")
        for i, readable in cpa_connection(authcfg=authcfg).executeSql(sql):
            rows[int(sql_value(i))]["readable"] = sql_value(readable)
    return rows


def open_work_layer(row, authcfg):
    uri = cpa_uri(row["shema"], row["naziv"], row["geom"], row["key"], authcfg=authcfg)
    return QgsVectorLayer(uri.uri(False), row["naziv"], "postgres")


def _insert(layer, group, index):
    QgsProject.instance().addMapLayer(layer, False)
    node = group.insertLayer(index, layer)
    node.setExpanded(False)
    return node


def zls_dropdown_config(categories_source):
    return {"AllowMulti": False, "AllowNull": False, "NofColumns": 1, "OrderByValue": True,
            "UseCompleter": False, "Key": "Vrsta", "Value": "Vrsta",
            "FilterExpression": "\"Sloj\" = current_value('Sloj')",
            "Layer": "", "LayerName": ZLS_CATEGORIES[1],
            "LayerSource": categories_source, "LayerProviderName": "postgres"}


def ensure_zls_dropdown(layer, authcfg):
    """If the ZLS interpretation's style has no drop-down on Vrsta, give it the agreed one."""
    if layer.name() != ZLS_LAYER:
        return
    idx = layer.fields().indexOf("Vrsta")
    if idx < 0 or layer.editorWidgetSetup(idx).type() == "ValueRelation":
        return
    schema, table, key = ZLS_CATEGORIES
    source = cpa_uri(schema, table, None, key, authcfg=authcfg).uri(False)
    layer.setEditorWidgetSetup(idx, QgsEditorWidgetSetup("ValueRelation", zls_dropdown_config(source)))


def resolve_dropdowns(layer, authcfg, group, index, rows=()):
    """Load the tables the layer's drop-downs read from, if they are not in the project yet,
    and point the drop-downs at them. Returns the number of layers added."""
    project = QgsProject.instance()
    added = 0
    for idx in range(layer.fields().count()):
        setup = layer.editorWidgetSetup(idx)
        if setup.type() != "ValueRelation":
            continue
        cfg = dict(setup.config())
        name = cfg.get("LayerName") or ""
        target = next((l for l in project.mapLayersByName(name) if l.isValid()), None) if name else None
        if target is None:
            row = next((r for r in rows if r["naziv"] == name), None)
            if row is None and cfg.get("LayerSource"):
                src = QgsDataSourceUri(cfg["LayerSource"])
                if src.table():
                    row = {"naziv": name or src.table(), "shema": src.schema() or "public", "key": src.keyColumn(),
                           "geom": src.geometryColumn() or None}
            if row is None:
                continue
            target = open_work_layer(row, authcfg)
            if not target.isValid():
                log(f"Tabele za spustni seznam »{name}« ni mogoče odpreti.", Qgis.MessageLevel.Info)
                continue
            _insert(target, group, index + added)
            added += 1
        cfg.update(Layer=target.id(), LayerName=target.name(), LayerSource=target.source(),
                   LayerProviderName=target.providerType())
        layer.setEditorWidgetSetup(idx, QgsEditorWidgetSetup("ValueRelation", cfg))
    return added


def load_rows(rows, authcfg, group, index, all_rows=()):
    """Load work layers at (group, index). Returns (loaded names, failed names)."""
    loaded, failed = [], []
    for row in rows:
        if any(l.isValid() for l in QgsProject.instance().mapLayersByName(row["naziv"])):
            continue                                   # already in the project
        layer = open_work_layer(row, authcfg)
        if not layer.isValid():
            failed.append(row["naziv"])
            continue
        _insert(layer, group, index)
        index += 1
        ensure_zls_dropdown(layer, authcfg)
        index += resolve_dropdowns(layer, authcfg, group, index, all_rows)
        loaded.append(row["naziv"])
    return loaded, failed


def reconnect_orphans(authcfg):
    """Layers from CPA whose login no longer exists (temporary login of an earlier session):
    switch them to the current login. Returns how many."""
    mgr = QgsApplication.authManager()
    existing = set(mgr.configIds())
    host, db = config.get("cpa_host"), config.get("cpa_database")
    n = 0
    for layer in QgsProject.instance().mapLayers().values():
        if layer.providerType() != "postgres":
            continue
        uri = QgsDataSourceUri(layer.source())
        if uri.host() != host or uri.database() != db or not uri.authConfigId() \
                or uri.authConfigId() in existing:
            continue
        uri.setAuthConfigId(authcfg)
        layer.setDataSource(uri.uri(False), layer.name(), "postgres")
        n += 1
    return n


def remove_work_layers(names):
    """Remove the 'Delovni sloji' group and every work layer (by name) from the project."""
    project = QgsProject.instance()
    group = project.layerTreeRoot().findGroup(GROUP)
    ids = {l.layerId() for l in group.findLayers()} if group else set()
    ids |= {l.id() for name in names for l in project.mapLayersByName(name)}
    project.removeMapLayers(list(ids))
    if group:
        project.layerTreeRoot().removeChildNode(group)


# ---------------------------------------------------------------------------
# User interface
# ---------------------------------------------------------------------------
class ArheoloskiGisWorkLoader:
    """Toolbar action: login (once per session), then the work layer window."""

    def __init__(self, iface):
        self.iface = iface
        self.window = None

    def run(self):
        if not _session["authcfg"] and not self.ask_login():
            return
        self.show_window()

    def ask_login(self):
        dlg = ArheoloskiGisWorkLoaderDialog(self.iface.mainWindow())
        dlg.label_2.setPixmap(QPixmap(str(pn_path("icons") / "CPA_logo_small.png")))
        dlg.remove_layers.hide()                      # now in the work layer window
        dlg.user_input.setText(QgsSettings().value("agis/cpa_last_user", ""))
        if dlg.user_input.text():
            dlg.pass_input.setFocus()
        ok_button = dlg.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        result = {}

        def try_login():
            user = dlg.user_input.text().strip()
            authcfg, message = login(user, dlg.pass_input.text(), dlg.mAuthConfigSelect.configId())
            if message:
                QMessageBox.warning(dlg, "AGIS", message)
                return
            if user:
                QgsSettings().setValue("agis/cpa_last_user", user)
            result["ok"] = True
            dlg.accept()

        ok_button.clicked.connect(try_login)
        dlg.buttonBox.rejected.connect(dlg.reject)
        dlg.exec()
        if result.get("ok"):
            n = reconnect_orphans(_session["authcfg"])
            if n:
                self.iface.messageBar().pushMessage(
                    "AGIS", f"Ponovno povezanih delovnih slojev iz prejšnje seje: {n}", Qgis.MessageLevel.Info, 5)
        return bool(result.get("ok"))

    def show_window(self):
        if self.window is None:
            self.window = WorkLayersWindow(self, self.iface.mainWindow())
        self.window.reload()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        self.window.search.setFocus()

    def close(self):
        if self.window is not None:
            self.window.close()
            self.window.deleteLater()
            self.window = None


class WorkLayersWindow(QDialog):
    """List of work layers: search, double-click, drag into the Layers panel, Naloži vse."""

    KEY_GEOMETRY = "agis/work_window_geometry"

    def __init__(self, loader, parent=None):
        super().__init__(parent)
        from ..tab_nalozi_sloje import CatalogueTable, LayerTreeDrop
        self.loader = loader
        self.iface = loader.iface
        self.rows = []
        self.dragged = []
        self.setWindowTitle("AGIS – delovni sloji")
        self.setWindowFlag(Qt.WindowType.Tool, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Išči delovni sloj…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.apply_filter)
        top.addWidget(self.search)
        self.user_button = QPushButton()
        self.user_button.setFlat(True)
        self.user_button.setToolTip("Prijava z drugim uporabnikom")
        self.user_button.clicked.connect(self.change_user)
        top.addWidget(self.user_button)
        layout.addLayout(top)

        self.table = CatalogueTable(self)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Sloj", "Shema"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(lambda r, _c: self.load([self.entry(r)]))
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.context_menu)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        self.all_button = QPushButton("Naloži vse")
        self.all_button.clicked.connect(self.load_all)
        remove = QPushButton("Odstrani delovne sloje")
        remove.clicked.connect(self.remove_all)
        buttons.addWidget(self.all_button)
        buttons.addStretch()
        buttons.addWidget(remove)
        layout.addLayout(buttons)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)

        self._drop_filter = None
        view = self.iface.layerTreeView() if self.iface is not None else None
        if view is not None and hasattr(view, "viewport"):
            try:
                self._drop_filter = LayerTreeDrop(self, view)
                view.viewport().installEventFilter(self._drop_filter)
                view.viewport().setAcceptDrops(True)
            except TypeError:
                self._drop_filter = None

        geometry = QgsSettings().value(self.KEY_GEOMETRY)
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(360, 460)

    # ------------------------------------------------------------- list

    def reload(self):
        self.user_button.setText(f"👤 {_session['user'] or ''}")
        try:
            self.rows = work_layer_rows(_session["authcfg"])
        except QgsProviderConnectionException as e:
            self.rows = []
            self.status.setText(f"Seznama delovnih slojev ni mogoče prebrati: {e}")
        t = self.table
        t.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            for col, text in enumerate((r["naziv"], r["shema"])):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, i)
                if r["readable"] is False:
                    item.setForeground(QBrush(GREY))
                    item.setToolTip("S to prijavo ni pravice za branje tega sloja.")
                elif r["readable"] is None:
                    item.setForeground(QBrush(GREY))
                    item.setToolTip("Tabela v bazi ne obstaja.")
                t.setItem(i, col, item)
        self.apply_filter()

    def entry(self, row):
        item = self.table.item(row, 0)
        return self.rows[item.data(Qt.ItemDataRole.UserRole)] if item is not None else None

    def selected_entries(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [e for e in (self.entry(r) for r in rows) if e]

    def apply_filter(self, *_):
        needle = self.search.text().strip().lower()
        shown = 0
        for row in range(self.table.rowCount()):
            e = self.entry(row)
            hit = not needle or needle in f"{e['naziv']} {e['shema']}".lower()
            self.table.setRowHidden(row, not hit)
            shown += hit
        readable = sum(1 for r in self.rows if r["readable"])
        if self.rows:
            self.status.setText(f"Delovnih slojev: {len(self.rows)}, berljivih: {readable}"
                                + (f", prikazanih: {shown}" if needle else ""))

    def context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        e = self.entry(row) if row >= 0 else None
        if not e:
            return
        menu = QMenu(self)
        menu.addAction("Naloži").triggered.connect(lambda: self.load(self.selected_entries() or [e]))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------- loading

    def load(self, entries, position=None):
        entries = [e for e in entries if e and e["readable"]]
        if not entries:
            self.status.setText("Izbrani sloji niso berljivi s to prijavo.")
            return
        if position is None:
            try:
                position = tree_position(self.iface.layerTreeView())
            except Exception:
                position = (None, 0)
        group, index = position
        if group is None:
            group, index = QgsProject.instance().layerTreeRoot(), 0
        self._report(*load_rows(entries, _session["authcfg"], group, index, self.rows))

    def load_all(self):
        """All readable work layers into the 'Delovni sloji' group at the top, as before."""
        root = QgsProject.instance().layerTreeRoot()
        group = root.findGroup(GROUP)
        if group is None:
            group = root.insertGroup(0, GROUP)
        readable = [r for r in self.rows if r["readable"]]
        self._report(*load_rows(readable, _session["authcfg"], group, len(group.children()), self.rows))

    def _report(self, loaded, failed):
        text = f"Naloženih: {len(loaded)}" if loaded else "Nič novega – sloji so že v projektu."
        if failed:
            text += f". Ni bilo mogoče odpreti: {', '.join(failed)}"
        self.status.setText(text)
        if loaded:
            self.iface.messageBar().pushMessage("AGIS", f"Naloženih delovnih slojev: {len(loaded)}",
                                                Qgis.MessageLevel.Success, 3)

    def remove_all(self):
        names = [r["naziv"] for r in self.rows] + [ZLS_CATEGORIES[1]]
        remove_work_layers(names)
        self.status.setText("Delovni sloji so odstranjeni iz projekta.")

    def change_user(self):
        if self.loader.ask_login():
            self.reload()

    # -------------------------------------------------------------- window

    def done(self, result):
        QgsSettings().setValue(self.KEY_GEOMETRY, self.saveGeometry())
        super().done(result)

    def closeEvent(self, event):
        QgsSettings().setValue(self.KEY_GEOMETRY, self.saveGeometry())
        super().closeEvent(event)
