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
from qgis.PyQt.QtWidgets import (QAction,
                                QMenu,
                                QDialogButtonBox,
                                QCheckBox)
from qgis.core import (QgsProject,
                       QgsRasterLayer,
                       QgsVectorLayer,
                       QgsLayerDefinition,
                       QgsCoordinateReferenceSystem,
                       QgsLayerTreeLayer

                       )
import tempfile
import shutil


# Initialize Qt resources from file resources.py
from ..resources import *
# Import the code for the dialog
from .agis_search_dialog import ArheoloskiGisSearchDialog
import os.path
from pathlib import Path
from ..externals import (path,
                        access,
                        data_access,
                        postgis_connect
                        )
import tempfile
import shutil

class ArheoloskiGisSearch:
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

        self.dlg = ArheoloskiGisSearchDialog()


        def my_function(self, txt):
            search_in =  txt
            query = "SELECT myfield1, myfield2 FROM my_table WHERE '%s' LIKE '%' || search_field || '%';" % (search_in)
            # access your db and run the query 
            # run the query with while query.next(

        self.dlg.textedit.textChanged.connect(self.my_function)

        completer = QCompleter ()
        self.dlg.mylineedit.setCompleter(completer)
        model = QStringListModel()
        completer.setModel(model)
        model.setStringList(["completion", "data", "goes", "here"])
        # model.setStringList(my_lst)

        #https://gis.stackexchange.com/questions/246339/drop-down-list-qgis-plugin-based-on-keyword-search


        self.dlg.buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.dlg.close)
        self.dlg.buttonBox.button(QDialogButtonBox.Ok).clicked.connect(self.load_layers)
        self.dlg.buttonBox.button(QDialogButtonBox.Ok).clicked.connect(self.dlg.close)
        self.dlg.remove_layers.clicked.connect(self.remove_layers)


        logo_path = path('icons')/"loader_logo_small"
        self.dlg.label_2.setPixmap(QPixmap(str(logo_path)))
        # Declare instance attributes
        self.actions = []
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

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/agis/icons/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'AGIS'),
            callback=self.run,
            parent=self.iface.mainWindow())
        # will be set False in run()

        self.first_start = True

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&AGIS'),
                action)
            self.iface.removeToolBarIcon(action)


    def run(self):
        """Run method that performs all the real work"""
        if self.first_start == True:
            self.first_start = False
        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result:
            # Do something useful here - delete the line containing pass and
            # substitute with your code.
            pass





    def remove_layers(self):
        root = QgsProject.instance().layerTreeRoot()
        #Clean layers (On update use:  names = [layer.name() for layer in QgsProject.instance().mapLayers().values()] ; print (names)  ) 
        layers = ['Električno omrežje', 'Geologic age by colour, includes Fennoscandian Precambrian subdivisions', 'Kanalizacijsko omrežje', 'Lithology (Representative)', 'Telekomunikacijsko omrežje ', 'Toplotno omrežje', 'Vodovodno omrežje', 'AO_topo75_1880', 'AO_topo75_1914', 'Claustra Alpium Iuliarum', 'DOF050', 'DPK1000', 'DPK250', 'DPK500', 'DTK50_1950_1967', 'DTK50', 'DTK5', 'Državna meja Republike Slovenije', 'Evidenca arheoloških raziskav', 'Franciscejski kataster', 'Katalog najdišč', 'Katastrske občine', 'Naselja', 'Načrti najdišč', 'Načrti najdišč_poligoni', 'Občine', 'ZKP parcele', 'ZKN parcele', 'RKD', 'SMAP', 'ZLS SVF', 'ZLS interpretacija', 'eVRD']
        groups = ['Arheologija', 'Dediščina', 'Prostorske enote', 'Historične podlage', 'Podlage' ]
       
        for layer in layers:
            for a in QgsProject.instance().mapLayersByName(layer):
                try:
                    QgsProject.instance().removeMapLayer(a.id())
                except:
                    continue
        for group in groups:       
            for s in [child for child in root.children()]:
                if s.name() == group:
                    try:
                     root.removeChildNode(s)
                    except:
                        continue
  
   
    def load_layers(self):
        root = QgsProject.instance().layerTreeRoot()
        crs = QgsCoordinateReferenceSystem("EPSG:3794")

        if access(self):
            self.iface.messageBar().pushMessage(self.tr("Povezava s podatkovno bazo CPA uspešna.."))
        else:
            self.iface.messageBar().pushMessage(self.tr("Nalagam brez CPA slojev.."))

        #To prevent folder locking of Plugin directory
        try:
            tmp = tempfile.mkdtemp()
            src = path('qlrs')
            shutil.rmtree(tmp)
            shutil.copytree(str(src), tmp)
            styles_path = Path(tmp)
        except:
            self.iface.messageBar().pushMessage(self.tr('Berem qlr iz mape vtičnika...'))



        #Load Arheologija layes group

        if access(self):
            if not root.findGroup(self.tr("Arheologija")):
                arheo_group = root.addGroup(self.tr("Arheologija"))
            else:
                arheo_group = root.findGroup(self.tr("Arheologija"))
            
            vlayer = postgis_connect(self, "public", "Katalog najdišč", "geom", "kid")
            QgsProject.instance().addMapLayer(vlayer, False)  
            arheo_group.insertChildNode(0, QgsLayerTreeLayer(vlayer))

            vlayer = postgis_connect(self, "public", "Evidenca arheoloških raziskav", "geom", "id")
            QgsProject.instance().addMapLayer(vlayer, False)   
            arheo_group.insertChildNode(1, QgsLayerTreeLayer(vlayer)) 

            arch_layers = ['Claustra Alpium Iuliarum', 'Načrti najdišč', 'Načrti najdišč_poligoni']
            for layer in arch_layers:
                vlayer = postgis_connect(self, "public", layer, "geom", "id")
                QgsProject.instance().addMapLayer(vlayer, False)   
                arheo_group.insertChildNode(2, QgsLayerTreeLayer(vlayer)) 
            
            arch_layers = ['SMAP', 'ZLS interpretacija']
            for layer in arch_layers:
                vlayer = postgis_connect(self, "public", layer, "geom", "gid")
                QgsProject.instance().addMapLayer(vlayer, False) 
                arheo_group.insertChildNode(7, QgsLayerTreeLayer(vlayer))  

        else:
                pass


        #Load Dediščina layes group
        if self.dlg.dediscina.isChecked():
            if not root.findGroup(self.tr("Dediščina")):
                dedi_group = root.addGroup(self.tr("Dediščina"))
            else:
                dedi_group = root.findGroup(self.tr("Dediščina"))

            evrd = styles_path/'eVRD.qlr'
            QgsLayerDefinition().loadLayerDefinition(str(evrd), QgsProject.instance(), dedi_group)

            rkd = styles_path/'RKD.qlr'
            QgsLayerDefinition().loadLayerDefinition(str(rkd), QgsProject.instance(), dedi_group)

        #Load Prostorske enote layes group
        if self.dlg.prostorske_enote.isChecked():
            self.iface.messageBar().pushMessage(self.tr("Nalagam Prostoske enote..."))
            if not root.findGroup(self.tr("Prostorske enote")):
                prostorske_group = root.addGroup(self.tr("Prostorske enote"))
            else:
                prostorske_group = root.findGroup(self.tr("Prostorske enote"))

            prostorske = styles_path/'Prostorske enote.qlr'
            QgsLayerDefinition().loadLayerDefinition(str(prostorske), QgsProject.instance(), prostorske_group)

            if access(self):
                vlayer = postgis_connect(self, "public", "ZKN parcele", "geom", "fid")
                QgsProject.instance().addMapLayer(vlayer, False) 
                prostorske_group.insertChildNode(6, QgsLayerTreeLayer(vlayer))   

            zkgji = styles_path/'zkgji.qlr'
            QgsLayerDefinition().loadLayerDefinition(str(zkgji), QgsProject.instance(), prostorske_group)
                      
        else:
            self.iface.messageBar().pushMessage(self.tr("Ne nalagam Prostorskih enot!"), duration=2)       

        #Load Historične podlage layes group
        if self.dlg.historicnepodlage.isChecked():
            self.iface.messageBar().pushMessage(self.tr("Nalagam Historične podlage..."))
            if not root.findGroup(self.tr("Historične podlage")):
                hist_group = root.addGroup(self.tr("Historične podlage"))
            else:
                hist_group = root.findGroup(self.tr("Historične podlage"))

            histo = styles_path/'Historicne podlage.qlr'
            QgsLayerDefinition().loadLayerDefinition(str(histo), QgsProject.instance(), hist_group)
            hist_group.setExpanded(False)
        else:
            self.iface.messageBar().pushMessage(self.tr("Ne nalagam Historičnih podlag!"), duration=2)  

        #Load podlage layes group
        if self.dlg.c_podlage.isChecked():
            self.iface.messageBar().pushMessage(self.tr("Nalagam podlage.."))
            if not root.findGroup(self.tr("Podlage")):
                podlage_group = root.addGroup(self.tr("Podlage"))
            else:
                podlage_group = root.findGroup(self.tr("Podlage"))

            geology = styles_path/'Geološka karta.qlr'
            QgsLayerDefinition().loadLayerDefinition(str(geology), QgsProject.instance(), podlage_group)

            if data_access(self):
                podlage_zls = styles_path/'ZLS 1.qlr'
                QgsLayerDefinition().loadLayerDefinition(str(podlage_zls), QgsProject.instance(), podlage_group)
            else:
                pass

            podlage_gurs = styles_path/'Podlage.qlr'
            QgsLayerDefinition().loadLayerDefinition(str(podlage_gurs), QgsProject.instance(), podlage_group)

        else:
            self.iface.messageBar().pushMessage(self.tr("Ne nalagam podlag!"), duration=2)


        QgsProject.instance().setCrs(crs)
        self.iface.messageBar().pushMessage(self.tr("Nastavljam Državni kordinatni sistem D96/TM.."), duration=5)  

        

        if access(self):
            #Set which layers should not be expanded
            not_expanded = ['SMAP', 'ZLS interpretacija','Claustra Alpium Iuliarum', 'Načrti najdišč', 'Načrti najdišč_poligoni', 'Evidenca arheoloških raziskav', 'Katalog najdišč']
            for layer in not_expanded:
                if len(QgsProject.instance().mapLayersByName(layer)) != 0:
                    layer = QgsProject.instance().mapLayersByName(layer)[0]
                    myLayerNode = root.findLayer(layer.id())
                    myLayerNode.setExpanded(False)

            #toggle visibility
            layers =['Claustra Alpium Iuliarum', 'Načrti najdišč', 'Načrti najdišč_poligoni', 'Evidenca arheoloških raziskav','SMAP', 'ZLS interpretacija', 'ZKN parcele']
            for layer in layers:
                if len(QgsProject.instance().mapLayersByName(layer)) != 0:
                    layer = QgsProject.instance().mapLayersByName(layer)[0]
                    root.findLayer(layer.id()).setItemVisibilityChecked(0)

        #toggle visibility
        layers =['RKD']
        for layer in layers:
            if len(QgsProject.instance().mapLayersByName(layer)) != 0:
                layer = QgsProject.instance().mapLayersByName(layer)[0]
                root.findLayer(layer.id()).setItemVisibilityChecked(0)            
