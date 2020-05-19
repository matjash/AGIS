import os
from pathlib import Path
from qgis.core import (QgsProject,
                       QgsRasterLayer,
                       QgsVectorLayer,
                       QgsLayerDefinition,
                       QgsDataSourceUri
                       )
import psycopg2
import base64

u = base64.b64decode('Y3Bh')

def path(item):
    path = {}
    plugin_dir = os.path.dirname(__file__)

    path['plugin'] = Path(plugin_dir)
    path['qlrs'] = path['plugin']/"qlrs"
    path['icons'] = path['plugin']/"icons"
    path['dependencies'] = path['plugin']/"dependencies"


    path = path[item]
    return path

# Checks if connected to CPA, ZVKDS network
def access(self):
    self.host = "majadb"
    self.database = "CPA_Analiza"
    self.user = u.decode('utf')
    self.password = u.decode('utf')
    self.port = "5432"
    try:
        conn = psycopg2.connect(host=self.host,port=self.port, database=self.database, user=self.user, password=self.password, connect_timeout=1 )
        conn.close()
        return True
    except:
        return False
        
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
    vlayer=QgsVectorLayer (uri .uri(False), tablename, "postgres")
    return vlayer
