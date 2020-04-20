import os
from pathlib import Path
from qgis.core import (QgsProject,
                       QgsRasterLayer,
                       QgsVectorLayer,
                       QgsLayerDefinition,
                       QgsDataSourceUri
                       )
import psycopg2


def path(item):
    path = {}
    plugin_dir = os.path.dirname(__file__)

    path['plugin'] = Path(plugin_dir)
    path['qlrs'] = path['plugin']/"qlrs"
    path['icons'] = path['plugin']/"icons"
    path['dependencies'] = path['plugin']/"dependencies"


    path = path[item]
    return path

# Checks duplicates and returnes value error (not used yet)
"""
def checkDuplicates(features, name, feedback):
    list = []
    for feature in features:
        list.append(feature[name])
    duplicates = 0
    for element in list:
        if list.count(element) > 1:
            feedback.pushInfo(self.tr("%s %s se pojavi: %s - krat!" % (name, element, list.count(element))))
            duplicates = duplicates + 1
        else:
            pass
    if duplicates == 0:
        feedback.pushInfo("Ni podvojenih %s" % name)
    else:
        raise ValueError

def value_error(id, value, feedback):
    feedback.reportError("Pri %s manjaka vrednost  %s!" % (id, value),False)
    raise ValueError
"""

# Checks if connected to CPA, ZVKDS network
def access(self):
    self.host = "majadb"
    self.database = "CPA_Analiza"
    self.user = "cpa"
    self.password = "cpa"
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
