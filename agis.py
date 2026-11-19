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
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QDockWidget, QFrame, QHBoxLayout, QLabel, QStyle, QTabWidget, QToolButton, QVBoxLayout,
    QWidget,
)
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
        self.work = None
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
        if self.work is not None:
            self.work.close()
            self.work = None
        self._remove_temporary_logins()
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

    @staticmethod
    def _remove_temporary_logins():
        """Temporary logins of work layers live only while QGIS runs."""
        from .agis_work_loader.agis_work_loader import remove_temporary_logins
        try:
            remove_temporary_logins()
        except Exception as e:          # never block loading/unloading the plugin
            from .externals import log
            log(f"Začasnih prijav ni bilo mogoče odstraniti: {e}")

    def work_loader(self):
        from .agis_work_loader.agis_work_loader import ArheoloskiGisWorkLoader  # only when used
        if self.work is None:
            self.work = ArheoloskiGisWorkLoader(self.iface)
        self.work.run()


CPA_GREEN = "#2e7d32"


class DockTitleBar(QWidget):
    """Title bar of the AGIS panel: logo, name, float and close buttons, and a thin
    green line along the whole width while the CPA database is reachable.
    Unhandled mouse events go to the dock, so dragging and double-click still work."""

    def __init__(self, dock):
        super().__init__(dock)
        self.dock = dock
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        row = QHBoxLayout()
        row.setContentsMargins(4, 2, 2, 2)
        row.setSpacing(4)
        logo = QLabel()
        h = max(14, self.fontMetrics().height())
        logo.setPixmap(QPixmap(str(pn_path("icons") / "agis_small.png")).scaled(
            h, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        row.addWidget(logo)
        title = QLabel("AGIS")
        title.setStyleSheet("font-weight: bold;")
        row.addWidget(title)
        row.addStretch()
        for pixmap, tip, slot in (
                (QStyle.StandardPixmap.SP_TitleBarNormalButton, tr("Odklopi / priklopi panel"),
                 lambda: dock.setFloating(not dock.isFloating())),
                (QStyle.StandardPixmap.SP_TitleBarCloseButton, tr("Zapri"), dock.close)):
            b = QToolButton()
            b.setAutoRaise(True)
            b.setIcon(self.style().standardIcon(pixmap))
            b.setToolTip(tip)
            b.setFixedSize(h + 4, h + 4)
            b.clicked.connect(slot)
            row.addWidget(b)
        outer.addLayout(row)
        self.cpa_line = QFrame()
        self.cpa_line.setFixedHeight(2)
        self.cpa_line.setStyleSheet(f"background: {CPA_GREEN}; border: none;")
        self.cpa_line.setToolTip(tr("Povezano z bazo CPA"))
        outer.addWidget(self.cpa_line)


class AgisDockWidget(QDockWidget):

    def __init__(self, iface, on_refresh=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("AGIS")
        self.setObjectName("AgisDock")
        self.title_bar = DockTitleBar(self)
        self.setTitleBarWidget(self.title_bar)

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
        self.settings = TabNastavitve(on_changed=self._settings_changed, on_status=self.update_cpa_line)
        self.tabs.addTab(self.settings, tr("Nastavitve"))
        self.tabs.addTab(TabOVticniku(iface), tr("Pomoč"))
        layout.addWidget(self.tabs)

        self.setWidget(main)
        self._on_refresh = on_refresh
        self.update_dev_label()
        self.update_cpa_line()

    def update_cpa_line(self):
        """Green line under the title while the CPA database is reachable (last known state)."""
        self.title_bar.cpa_line.setVisible(cpa_available())

    def _refreshed(self):
        self.update_dev_label()
        self.update_cpa_line()
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
