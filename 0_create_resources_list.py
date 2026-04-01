import sqlite3
from pathlib import Path

db_path = Path(r"C:\Users\matjaz\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\agis\sources.db")
db_path.parent.mkdir(parents=True, exist_ok=True)

# connect (will create file if missing)
conn = sqlite3.connect(db_path)
c = conn.cursor()

# create table
c.execute("""
CREATE TABLE IF NOT EXISTS layer_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    uri TEXT NOT NULL,
    url TEXT,
    description TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    "order" INTEGER DEFAULT 0
)
""")

# Updated sample WMS row to remove 'provider'
c.execute("""
INSERT INTO layer_sources
(name, source_type, uri, url, layer_name, description, group_name, enabled)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", (
    "DOF050",
    "wms",
    "contextualWMSLegend=0&crs=EPSG:3794&dpiMode=7&featureCount=10&format=image/png&layers=SI.GURS.ZPDZ:DOF050&styles&tilePixelRatio=0&url=https://ipi.eprostor.gov.si/wms-si-gurs-dts/wms",
    "https://ipi.eprostor.gov.si/wms-si-gurs-dts/wms",
    "SI.GURS.ZPDZ:DOF050",
    "Digital orthophoto 50 cm",
    None,
    1
))

# Updated sample QLR row to remove 'provider'
c.execute("""
INSERT INTO layer_sources
(name, source_type, uri, url, layer_name, description, group_name, enabled)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", (
    "RNPD",
    "qlr",
    "{qlrs}/RNPD.qlr",
    None,
    None,
    "RNPD predefined layer group",
    None,
    1
))

# Updated ArcGIS Feature Server row to remove 'provider'
c.execute("""
INSERT INTO layer_sources
(name, source_type, uri, url, layer_name, description, group_name, enabled)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", (
    "RABA",
    "arcgisfeatureserver",
    "crs='EPSG:3794' url='https://geohub.gov.si/ags/rest/services/TEMELJNE_VSEBINE/GH_MKGP_GERK_RABA/MapServer/1551'",
    "https://geohub.gov.si/ags/rest/services/TEMELJNE_VSEBINE/GH_MKGP_GERK_RABA/MapServer/1551",
    None,
    "Raba kmetijskih zemljišč (MKGP)",
    None,
    1
))

# Updated group row to remove 'provider'
c.execute("""
INSERT INTO layer_sources
(name, source_type, uri, url, layer_name, description, group_name, enabled)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", (
    "Arheologija – osnovni sloji",
    "group",
    None,
    None,
    None,
    "Standardni delovni paket",
    None,
    1
))

conn.commit()
conn.close()

print(f"SQLite layer source DB created: {db_path}")