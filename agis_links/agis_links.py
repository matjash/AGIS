# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ArheoloskiGis
                                 A QGIS plugin
 This plugin loads useful layers
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2020-02-22
        git sha              : $Format:%H$
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
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
from qgis.utils import iface

# Initialize Qt resources from file resources.py
from ..resources import *
# Import the code for the dialog
from .agis_links_dialog import ArheoloskiGisLinksDialog
import os.path
from pathlib import Path
import webbrowser
from ..externals import path


class ArheoloskiGisLinks:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'ArheoloskiGis_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.dlg = ArheoloskiGisLinksDialog()
        logo_path = path('icons')/"loader_logo_small"
        self.dlg.label_1.setPixmap(QPixmap(str(logo_path)))
        self.dlg.pushButton.clicked.connect(self.dlg.close)

        self.dlg.mapire.clicked.connect(self.arcanum)
        self.dlg.e_vode.clicked.connect(self.evode)
        self.dlg.gis_portal.clicked.connect(self.gis_portal)

        # Declare instance attributes
        self.actions = []


    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('ArheoloskiGis', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this='aaa',
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        self.first_start = True
        icon_path = ':/plugins/agis/icons/icon_arcanum_loader'
        self.add_action(
            icon_path,
            text=self.tr(u'Arcanum'),
            callback=self.run,
            parent=self.iface.mainWindow())
        
       # will be set False in run()
        



    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&AGIS'),
                action)
            self.iface.removeToolBarIcon(action)


    def run(self):
        """Run method that performs all the real work"""
        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        self.dlg.exec_()

    def arcanum(self):
        #Get bounding box and transform to WGS84 pseudo
        crsSrc = iface.mapCanvas().mapSettings().destinationCrs().authid()
        crsSrc = QgsCoordinateReferenceSystem(crsSrc)
        crsDest = QgsCoordinateReferenceSystem("EPSG:3857")
        transform = QgsCoordinateTransform(crsSrc, crsDest, QgsProject.instance())
        bbox = iface.mapCanvas().extent()
        e = transform.transformBoundingBox(bbox)
        xmin = e.xMinimum()
        ymin = e.yMinimum()
        xmax = e.xMaximum()
        ymax = e.yMaximum()
 
 
        part_one = 'https://mapire.eu/en/map/cadastral/?bbox='
        sep = '%2C'
        part_three = '&map-list=1&layers=here-aerial%2C3%2C4'
        link = '%s%s%s%s%s%s%s%s%s' %(part_one, xmin, sep, ymin, sep, xmax, sep, ymax,part_three) 
        webbrowser.open(link)
        pass

    def evode(self):
        webbrowser.open('http://gis.arso.gov.si/evode/profile.aspx?id=atlas_voda_Lidar@Arso')
        pass

    def gis_portal(self):
        webbrowser.open('https://gisportal.gov.si/portal/home/')
        pass