import os
from pathlib import Path
from qgis.core import (
                       QgsVectorLayer,
                       QgsDataSourceUri
                       )
import base64
import socket
def pn_path(item):
    path = {}
    plugin_dir = os.path.dirname(__file__)

    path['plugin'] = Path(plugin_dir)
    path['qlrs'] = path['plugin']/"qlrs"
    path['qml'] = path['plugin']/"qml"
    path['icons'] = path['plugin']/"icons"
    path['dependencies'] = path['plugin']/"dependencies"

    path = path[item]
    return path

#to be changed with secure method later
_cached_params = None

def parameters(self):
    global _cached_params
    if _cached_params is None:
        in_params = ['bWFqYWRi','Q1BBX0FuYWxpemE=','Y3Bh','Y3Bh','NTQzMg==']
        _cached_params = [base64.b64decode(p).decode('utf-8') for p in in_params]
    return _cached_params

def access(self, timeout=0.1):
    params = parameters(self)  # now a single cached call
    self.host = params[0]
    self.port = params[4]
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
    params = parameters(self) 
    uri = QgsDataSourceUri()
    uri.setConnection( params[0], params[4], params[1], params[2], params[3])  
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
    
def load_cpa_sources_list(self):
    table = postgis_connect(self, "cpa", "agis_layer_sources", None, "id")
    return table