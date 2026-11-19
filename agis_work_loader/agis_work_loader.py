"""'Naloži delovne sloje': CPA work layers, loaded with the user's own login.

The list of work layers is read with the shared cpa account; each layer is
then opened with the user's login, so everyone gets exactly the layers their
database role allows. A typed username/password is stored as a temporary
QGIS login only while loading and removed again afterwards, so saved
projects never carry it.
"""
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtWidgets import QDialogButtonBox, QMessageBox
from qgis.core import (Qgis, QgsApplication, QgsAuthMethodConfig, QgsProject,
                       QgsProviderConnectionException, QgsVectorLayer)

from ..externals import cpa_connection, cpa_uri, get_work_layers, log, pn_path, sql_value
from .agis_work_loader_dialog import ArheoloskiGisWorkLoaderDialog

GROUP = "Delovni sloji"
# Columns of "Delovno"."Delovni sloji", read by position as before:
COL_TABLE, COL_SCHEMA, COL_ACCESS, COL_GEOM, COL_KEY = 1, 2, 3, 4, 5


class ArheoloskiGisWorkLoader:

    def __init__(self, iface):
        self.iface = iface
        self.dlg = ArheoloskiGisWorkLoaderDialog(iface.mainWindow())
        buttons = self.dlg.buttonBox
        buttons.button(QDialogButtonBox.StandardButton.Ok).clicked.connect(self._ok)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).clicked.connect(self.dlg.reject)
        self.dlg.remove_layers.clicked.connect(self.remove_layers)
        self.dlg.label_2.setPixmap(QPixmap(str(pn_path("icons") / "CPA_logo_small.png")))

    def run(self):
        self.dlg.exec()

    def _ok(self):
        count, message = self.load_work_layers()
        if count:
            self.dlg.accept()
            self.iface.messageBar().pushMessage("AGIS", f"Naloženih delovnih slojev: {count}", Qgis.MessageLevel.Success, 5)
        else:
            QMessageBox.warning(self.dlg, "AGIS", message)

    # ------------------------------------------------------------------ work

    def load_work_layers(self):
        """Returns (number of layers loaded, message for the user if none)."""
        user = self.dlg.user_input.text().strip()
        password = self.dlg.pass_input.text()
        mgr = QgsApplication.authManager()
        temp_id = None

        if user:
            check_user, check_password = user, password
        else:
            authcfg = self.dlg.mAuthConfigSelect.configId()
            if not authcfg:
                return 0, "Vpišite uporabniško ime in geslo ali izberite shranjeno prijavo."
            cfg = QgsAuthMethodConfig()
            mgr.loadAuthenticationConfig(authcfg, cfg, True)
            check_user, check_password = cfg.config("username"), cfg.config("password")

        if check_user:                      # quick check: clear message instead of 18 failing layers
            try:
                cpa_connection(check_user, check_password)
            except QgsProviderConnectionException as e:
                log(f"Delovni sloji: {e}", Qgis.MessageLevel.Warning)
                return 0, "Napačno uporabniško ime ali geslo."

        if user:
            cfg = QgsAuthMethodConfig()
            cfg.setName(f"AGIS začasno ({user})")
            cfg.setMethod("Basic")
            cfg.setConfig("username", user)
            cfg.setConfig("password", password)
            stored = mgr.storeAuthenticationConfig(cfg)
            if isinstance(stored, tuple):           # newer QGIS returns (ok, config)
                ok, cfg = stored[0], (stored[1] if len(stored) > 1 else cfg)
            else:
                ok = stored
            if not ok or not cfg.id():
                return 0, "Začasne prijave ni bilo mogoče shraniti (je glavno geslo QGIS odklenjeno?)."
            authcfg = temp_id = cfg.id()

        try:
            table = get_work_layers()
            if not table.isValid():
                return 0, "Seznam delovnih slojev v bazi CPA ni dosegljiv."
            layers = []
            for f in table.getFeatures():
                a = [sql_value(v) for v in f.attributes()]
                if str(a[COL_ACCESS]) == "admin":
                    continue
                uri = cpa_uri(a[COL_SCHEMA], a[COL_TABLE], a[COL_GEOM] or None, a[COL_KEY] or "", authcfg=authcfg)
                layer = QgsVectorLayer(uri.uri(False), a[COL_TABLE], "postgres")
                if layer.isValid():
                    layers.append(layer)
            if not layers:
                return 0, "S to prijavo ni dostopen noben delovni sloj."

            root = QgsProject.instance().layerTreeRoot()
            group = root.findGroup(GROUP) or root.addGroup(GROUP)
            for i, layer in enumerate(layers):
                QgsProject.instance().addMapLayer(layer, False)
                group.insertLayer(i, layer).setExpanded(False)
            return len(layers), ""
        finally:
            if temp_id:
                mgr.removeAuthenticationConfig(temp_id)

    def remove_layers(self):
        """Remove the 'Delovni sloji' group and every work layer from the project."""
        project = QgsProject.instance()
        names = set()
        table = get_work_layers()
        if table.isValid():
            names = {str(sql_value(f.attributes()[COL_TABLE])) for f in table.getFeatures()}
        group = project.layerTreeRoot().findGroup(GROUP)
        ids = {l.layerId() for l in group.findLayers()} if group else set()
        ids |= {l.id() for name in names for l in project.mapLayersByName(name)}
        project.removeMapLayers(list(ids))
        if group:
            project.layerTreeRoot().removeChildNode(group)
