# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ArheoloskiGis
                                 A QGIS plugin
 This plugin loads useful layers
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2020-05-19
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
                       QgsLayerTreeLayer,
                       QgsDataSourceUri,
                       QgsCredentials,
                       QgsApplication,
                       QgsAuthMethodConfig,
                       Qgis,
                       QgsVectorLayerJoinInfo,
                       QgsEditorWidgetSetup,
                       QgsAuthManager
                       )
from qgis.gui import QgsAuthConfigSelect
import tempfile
import shutil
import psycopg2
import re

# Initialize Qt resources from file resources.py
from ..resources import *
# Import the code for the dialog
from .agis_work_loader_dialog import ArheoloskiGisWorkLoaderDialog
import os.path
from pathlib import Path
from ..externals import (path,
                        data_access,
                        access,
                        postgis_connect,
                        parameters,
                        get_work_layers
                        )
import tempfile
import shutil

class ArheoloskiGisWorkLoader:
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

        self.dlg = ArheoloskiGisWorkLoaderDialog()

        self.dlg.buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.dlg.close)
        self.dlg.buttonBox.button(QDialogButtonBox.Ok).clicked.connect(self.load_work_layers)
        self.dlg.buttonBox.button(QDialogButtonBox.Ok).clicked.connect(self.dlg.close)

        self.dlg.remove_layers.clicked.connect(self.remove_layers)
    
        logo_path = path('icons')/"CPA_logo_small.png"
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
        table = get_work_layers(self)

        w_layers = [r[1] for r in table.getFeatures()]         
        groups = [self.tr('Delovni sloji')]
        for w in  w_layers:
            for a in QgsProject.instance().mapLayersByName(w):
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
    


    def load_work_layers(self):

        def check_conn(host, port, database, user, password):
            try:
                conn = psycopg2.connect(host=host,port=port, database=database, user=user, password=password, connect_timeout=1)
                conn.close()
                #self.iface.messageBar().pushMessage(self.tr('Povezava uspešna'))
                return True
            except:
                #self.iface.messageBar().pushMessage(self.tr('Povezava neuspešna, napačen uporabnik ali geslo!'))
                return False


        host = parameters(self)[0]
        database =  parameters(self)[1]
        port =  parameters(self)[4]
        table = get_work_layers(self)
        uri = QgsDataSourceUri()
        root = QgsProject.instance().layerTreeRoot()

        self.host = parameters(self)[0]
        self.database =  parameters(self)[1]
        self.port =  parameters(self)[4]


        #Input authentication
        authcfg = self.dlg.mAuthConfigSelect.configId()
        auth_mgr = QgsApplication.authManager()
        auth_cfg = QgsAuthMethodConfig()
        auth_mgr.loadAuthenticationConfig(authcfg, auth_cfg, True)
        auth = auth_cfg.configMap()

        # Input Username, password
        user = self.dlg.user_input.text()
        password = self.dlg.pass_input.text()
        def auth_text(user, password):   
            authMgr = QgsApplication.authManager()    
            cfg = QgsAuthMethodConfig()
            cfg.setName(user)
            cfg.setMethod('Basic')
            cfg.setConfig('username', user)
            cfg.setConfig('password', password) 
            authMgr.storeAuthenticationConfig(cfg)
            return(cfg) 

        aut_meth = 0 

        if user:
            check_conn(host, port, database, user, password)
            authentication = auth_text(user, password)  
            aut_meth = 1

        elif auth_mgr:
            try:
                check_conn(host, port, database, auth["username"], auth["password"])
                authentication = auth_cfg
            except:
                pass
        else:
            self.iface.messageBar().pushMessage(self.tr("Napačen uporabnik ali geslo."), self.tr("Potrdi za javni dostop."), level=Qgis.Critical)
            text = self.tr('Uporabljam javni dostop:')
            uri.setConnection(host, port, database, None, None)
            (success, user, passwd) = QgsCredentials.instance().get(text, parameters(self)[3],  parameters(self)[2])  
            if success:
                if check_conn(host, port, database, user, passwd):
                    user = user
                    password = passwd  
                else:
                    check_conn(host, port, database, user, passwd) 
                    self.iface.messageBar().pushMessage(self.tr('Povezava neuspešna, napačen uporabnik ali geslo!'))

        #List of groups and layers
        w_layers = [r[1] for r in table.getFeatures()]         
        groups = [self.tr('Delovni sloji')]



        def load_wl(shema, table, geom, sql, fid):   
            if geom == '':
                geom = None
            uri.setConnection(self.host, self.port, self.database, "", "", QgsDataSourceUri.SslDisable,"")
            uri.setAuthConfigId(authentication.id())
            uri.setDataSource(shema, table, geom, sql, fid)
            layer=QgsVectorLayer (uri .uri(False), table, "postgres")
            return layer
      



        #Attribute form config for layer ZLS Int
        def field_to_value_relation(layer):
            fields = layer.fields()
            pattern = re.compile(r'Vrsta')
            fields_vrsta = [field for field in fields if pattern.match(field.name())]
            if len(fields_vrsta) > 0:
                config = {'AllowMulti': False,
                        'AllowNull': False,
                        'FilterExpression': 'Sloj = current_value(\'Sloj\') and  \"Opombe\" =\'kategorije\'',
                        'Key': 'Vrsta',
                        'Layer': layer.id(),
                        'NofColumns': 1,
                        'OrderByValue': False,
                        'UseCompleter': False,
                        'Value': 'Vrsta'}
                for field in fields_vrsta:
                    field_idx = fields.indexOf(field.name())
                    if field_idx >= 0:
                        try:             
                            widget_setup = QgsEditorWidgetSetup('ValueRelation',config)
                            layer.setEditorWidgetSetup(field_idx, widget_setup) 
                        except:
                            pass
                    else:
                        return False
            else:
                return False
            return True

        #Join fields function
        def field_join(t_layer, s_layer, t_field, s_field):
            joinObject = QgsVectorLayerJoinInfo()
            joinObject.setJoinFieldName(s_field)
            joinObject.setTargetFieldName(t_field)
            joinObject.setJoinLayerId(s_layer.id())
            joinObject.setUsingMemoryCache(True)
            joinObject.setJoinLayer(s_layer)
            t_layer.addJoin(joinObject)


        #Populate list of accessible layers
        layers_list = []
        for f in table.getFeatures():
            if f[3] != 'admin':
                print(f[2])
                try:
                    layer = load_wl(f[2], f[1], f[4], "", f[5])
                    if layer.isValid():
                        layers_list.append(layer)  
                except:
                    continue

        if not root.findGroup(self.tr('Delovni sloji')) and len(layers_list) != 0:
            w_group = root.addGroup(self.tr('Delovni sloji'))
        else:
            w_group = root.findGroup(self.tr('Delovni sloji'))

        # load layers
        for current, layer in enumerate(layers_list):
            QgsProject.instance().addMapLayer(layer, False)   
            w_group.insertChildNode(current, QgsLayerTreeLayer(layer))
            myLayerNode = root.findLayer(layer.id())
            myLayerNode.setExpanded(False)
            if layer.name() == 'ZLS Interpretacija_delovno':
                field_to_value_relation(layer)
        
        if aut_meth == 1:
            authMgr = QgsApplication.authManager()
            authMgr.removeAuthenticationConfig(authentication.id())  
