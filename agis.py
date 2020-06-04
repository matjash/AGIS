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
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.core import QgsProcessingAlgorithm, QgsApplication
import os.path
from pathlib import Path


# Initialize Qt resources from file resources.py
from .resources import *

from .externals import path, access

#import processing provider
#from .processing_provider.provider import Provider

# Import the code for the dialog
from .agis_loader.agis_load import ArheoloskiGisLoad
from .agis_links.agis_links import ArheoloskiGisLinks
from .about.agis_about import ArheoloskiGisAbout
from .agis_work_loader.agis_work_loader import ArheoloskiGisWorkLoader
#from .agis_search import ArheoloskiGisSearch

class ArheoloskiGis:
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

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr('AGIS')

        #self.provider = Provider()

		#Create custom menu
        self.AGIS_Menu = QMenu(self.menu)

		#Create sub menus
        #self.Sub_Menu = QMenu("Pre-Processor")
        #self.AGIS_Menu.addMenu(self.Sub_Menu)

        #Add tools to menus, actions..
        self.load_icon = str(path('icons')/'icon_load.png')
        self.Load_agis = QAction(QIcon(self.load_icon),self.tr("Naloži sloje"), self.iface.mainWindow())
        self.AGIS_Menu.addAction(self.Load_agis)
        self.Load_agis.triggered.connect(self.Loadagis)

        self.links_icon = str(path('icons')/'icon_links.png')
        self.Links_agis = QAction(QIcon(self.links_icon),self.tr("Uporabne povezave"), self.iface.mainWindow())
        self.AGIS_Menu.addAction(self.Links_agis)
        self.Links_agis.triggered.connect(self.link)

        if access(self):
            self.work_loader_icon = str(path('icons')/'icon_work_loader.png')
            self.Work_loader = QAction(QIcon(self.work_loader_icon),self.tr("Naloži delovne sloje"), self.iface.mainWindow())
            self.AGIS_Menu.addAction(self.Work_loader)
            self.Work_loader.triggered.connect(self.work_loader)


        self.about_icon = str(path('icons')/'agis_logo.png')
        self.About_agis = QAction(QIcon(self.about_icon),self.tr('O vtičniku'), self.iface.mainWindow())
        self.AGIS_Menu.addAction(self.About_agis)
        self.About_agis.triggered.connect(self.about)

        self.iface.mainWindow().menuBar().insertMenu(self.iface.firstRightStandardMenu().menuAction(), self.AGIS_Menu)




        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

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
        """
        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)
        """
        self.actions.append(action)
        return action


    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        #QgsApplication.processingRegistry().addProvider(self.provider)


        # will be set False in run()
        self.first_start = True

        self.add_action(
            self.load_icon,
            text=self.tr('Naloži sloje'),
            callback=self.Loadagis,
            parent=self.iface.mainWindow())


        if access(self):
            self.add_action(
                self.work_loader_icon,
                text=self.tr('Naloži delovne sloje'),
                callback=self.work_loader,
                parent=self.iface.mainWindow())


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
  
        #QgsApplication.processingRegistry().removeProvider(self.provider)
        
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr('AGIS'),
                action)
            self.iface.removeToolBarIcon(action)
            self.iface.removePluginMenu(
                self.tr('Naloži sloje'),
                action)
            self.iface.removePluginMenu(
                self.tr('O vtičniku'),
                action)
            if access(self):
                self.iface.removePluginMenu(
                self.tr('Naloži delovne sloje'),
                action)


    def run(self):
        """Run method that performs all the real work"""
        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start == True:
            self.first_start = False


    def link(self):
        ld = ArheoloskiGisLinks(self.iface)
        ld.run()

    def Loadagis(self):
        ld = ArheoloskiGisLoad(self.iface)
        ld.run()

    def about(self):
        ld = ArheoloskiGisAbout(self.iface)
        ld.run()
    
    def work_loader(self):
        ld = ArheoloskiGisWorkLoader(self.iface)
        ld.run()

