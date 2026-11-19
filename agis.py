# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ArheoloskiGis - A QGIS plugin
        begin                : 2020-02-22
        copyright            : (C) 2020 by Matjaž Mori, ZVKDS CPA
        email                : matjaz.mori@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QDialog, QDockWidget, QLabel, QTabWidget, QVBoxLayout, QWidget
from qgis.core import QgsSettings

from . import config
from .externals import cpa_available, pn_path
from .tab_nalozi_sloje import TabNaloziSloje
from .tab_nastavitve import TabNastavitve
from .tab_o_vticniku import TabOVticniku
from .tab_parcele import TabParcele
from .tab_raziskave import TabEarheologija, TabEvrd


def tr(message):
    return QCoreApplication.translate("ArheoloskiGis", message)


class ArheoloskiGis:
    """QGIS plugin entry point."""

    def __init__(self, iface):
        self.iface = iface
        self.toolbar = None
        self.dock = None
        self.actions = []
        self.work_action = None
        self.quick = None
        self.menu = tr("AGIS")

    # ------------------------------------------------------------------ GUI

    def initGui(self):
        self.toolbar = self.iface.addToolBar("AGIS")
        self.toolbar.setObjectName("AGIS")

        self._add_action("icon_load.png", tr("AGIS"), self.show_dock, in_menu=True)
        self._add_action("agis_small.png", tr("AGIS – naloži sloje"), self.show_quick)
        self.update_work_action()   # only shown if the CPA database is reachable

        self.show_dock()

    def _add_action(self, icon, text, callback, in_menu=False):
        action = QAction(QIcon(str(pn_path("icons") / icon)), text, self.iface.mainWindow())
        action.triggered.connect(callback)
        self.toolbar.addAction(action)
        if in_menu:
            self.iface.addPluginToWebMenu(self.menu, action)
        self.actions.append((action, in_menu))
        return action

    def update_work_action(self):
        """Show "Naloži delovne sloje" only while the CPA database is reachable."""
        reachable = cpa_available()
        if reachable and self.work_action is None:
            self.work_action = self._add_action("icon_work_loader.png", tr("Naloži delovne sloje"), self.work_loader)
        if self.work_action is not None:
            self.work_action.setVisible(reachable)

    def unload(self):
        for action, in_menu in self.actions:
            if in_menu:
                self.iface.removePluginWebMenu(self.menu, action)
            if self.toolbar:
                self.toolbar.removeAction(action)
        self.actions = []
        self.work_action = None
        if self.toolbar:
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None
        if self.quick:
            self.quick.close()
            self.quick.deleteLater()
            self.quick = None
        if self.dock:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None

    def show_dock(self):
        if self.dock is None:
            self.dock = AgisDockWidget(self.iface, on_refresh=self.update_work_action,
                                       parent=self.iface.mainWindow())
            self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.show()
        self.dock.raise_()

    # -------------------------------------------------------------- actions

    def show_quick(self):
        """Small window with only the layer list (search, load, drag into the Layers panel)."""
        if self.quick is None:
            self.quick = QuickLoadWindow(self.iface, self.iface.mainWindow())
        self.quick.list.reload(recheck=False)
        self.quick.show()
        self.quick.raise_()
        self.quick.activateWindow()
        self.quick.list.search.setFocus()

    def work_loader(self):
        from .agis_work_loader.agis_work_loader import ArheoloskiGisWorkLoader  # only when used
        ArheoloskiGisWorkLoader(self.iface).run()


class AgisDockWidget(QDockWidget):

    def __init__(self, iface, on_refresh=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("AGIS")
        self.setObjectName("AgisDock")

        main = QWidget()
        layout = QVBoxLayout(main)
        layout.setContentsMargins(0, 0, 0, 0)

        # DEV marker - only shown in test mode (dev overrides active)
        self.dev_label = QLabel()
        self.dev_label.setStyleSheet("background: #ff9800; color: white; padding: 1px 6px; border-radius: 3px;")
        layout.addWidget(self.dev_label, 0, Qt.AlignmentFlag.AlignLeft)

        self.tabs = QTabWidget()
        self.nalozi = TabNaloziSloje(iface, on_refresh=self._refreshed)
        self.tabs.addTab(self.nalozi, tr("Naloži sloje"))
        self.tabs.addTab(TabParcele(iface), tr("Parcele"))
        self.tabs.addTab(TabEarheologija(iface), tr("eArheologija"))
        self.tabs.addTab(TabEvrd(iface), tr("eVRD"))
        self.settings = TabNastavitve(on_changed=self._settings_changed)
        self.tabs.addTab(self.settings, tr("Nastavitve"))
        self.tabs.addTab(TabOVticniku(iface), tr("Pomoč"))
        layout.addWidget(self.tabs)

        self.setWidget(main)
        self._on_refresh = on_refresh
        self.update_dev_label()

    def _refreshed(self):
        self.update_dev_label()
        if self._on_refresh:
            self._on_refresh()

    def update_dev_label(self):
        text = config.dev_label()
        self.dev_label.setText(text)
        self.dev_label.setToolTip("\n".join(f"{k} = {v}" for k, v in config.overrides().items()
                                            if "password" not in k))
        self.dev_label.setVisible(bool(text))

    def _settings_changed(self):
        """Catalogue switch or dev reset in the Nastavitve tab."""
        self.nalozi.refresh_all()      # reloads the catalogues and calls _refreshed


class QuickLoadWindow(QDialog):
    """'AGIS – naloži sloje' from the toolbar: the catalogue list without editing tools."""

    KEY_GEOMETRY = "agis/quick_window_geometry"

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("AGIS – naloži sloje"))
        self.setWindowFlag(Qt.WindowType.Tool, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.list = TabNaloziSloje(iface, compact=True)
        layout.addWidget(self.list)
        geometry = QgsSettings().value(self.KEY_GEOMETRY)
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(380, 520)

    def done(self, result):
        QgsSettings().setValue(self.KEY_GEOMETRY, self.saveGeometry())
        super().done(result)

    def closeEvent(self, event):
        QgsSettings().setValue(self.KEY_GEOMETRY, self.saveGeometry())
        super().closeEvent(event)
