import os
from pathlib import Path
from qgis.core import (
                       QgsVectorLayer,
                       QgsDataSourceUri
                       )
import base64
import socket
def path(item):
    path = {}
    plugin_dir = os.path.dirname(__file__)

    path['plugin'] = Path(plugin_dir)
    path['qlrs'] = path['plugin']/"qlrs"
    path['icons'] = path['plugin']/"icons"
    path['dependencies'] = path['plugin']/"dependencies"

    path = path[item]
    return path

#to be changed with secure method later
def parameters(self):
    in_params = ['bWFqYWRi','Q1BBX0FuYWxpemE=','Y3Bh','Y3Bh','NTQzMg==']
    params = []
    for par in in_params:
        par = base64.b64decode(par).decode('utf')
        params.append(par) 
    return params

# Checks if connected to CPA, ZVKDS network
def access(self, timeout=1):
    self.host = parameters(self)[0]
    self.port =  parameters(self)[4]
    try:
        with socket.create_connection((self.host, int(self.port)), timeout=timeout):
            return True
    except:
        return False

# Check if data path is accessible
def data_access(self):
    data_path = Path('V:/01 CPA - PODATKOVNE ZBIRKE/03 GIS CPA')
    if data_path.exists():
        return True
    else:
        return False

# Get layer from CPA, ZVKDS database
def postgis_connect(self, shema, tablename, geometry, id):
    uri = QgsDataSourceUri()
    uri.setConnection(self.host, self.port, self.database, self.user, self.user)  
    uri.setDataSource(shema, tablename, geometry)
    uri.setKeyColumn(id)
    vlayer=QgsVectorLayer (uri.uri(False), tablename, "postgres")
    return vlayer

def get_work_layers(self):
    if access(self):
        uri = QgsDataSourceUri()
        uri.setConnection(self.host, self.port, self.database, self.user, self.user)  
        uri.setDataSource("Delovno", "Delovni sloji", None, "", "id")
        table = QgsVectorLayer(uri.uri(), self.tr("Delovni sloji"), "postgres")
        if not table.isValid():
            self.iface.messageBar().pushMessage(self.tr('Težave z dostopom.'))
        return table