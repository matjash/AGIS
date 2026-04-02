from qgis.core import (
    QgsProject,
    QgsLayerDefinition
)
from qgis.PyQt.QtXml import QDomDocument
from qgis.utils import iface

import sqlite3

DB_PATH = r"C:\Users\matjaz\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\agis\sources.db"
TABLE = "layer_sources"   # adjust if needed
COLUMN = "qlr_xml"


def get_selected_group():
    view = iface.layerTreeView()
    selected = view.selectedNodes()
    
    for node in selected:
        if node.nodeType() == node.NodeGroup:
            return node
    return None


def ensure_column_exists(conn, table, column):
    cur = conn.cursor()
    
    cur.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cur.fetchall()]
    
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
        conn.commit()


from qgis.core import QgsReadWriteContext
from qgis.PyQt.QtXml import QDomDocument

def group_to_qlr_xml(group):
    doc = QDomDocument("qlr")
    context = QgsReadWriteContext()

    QgsLayerDefinition.exportLayerDefinition(
        doc,
        [group],
        context
    )

    return doc.toString()

def save_qlr_to_db(qlr_xml, name):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    ensure_column_exists(conn, TABLE, COLUMN)

    # simple example: update by name
    cur.execute(f"""
        UPDATE {TABLE}
        SET {COLUMN} = ?
        WHERE name = ?
    """, (qlr_xml, name))

    conn.commit()
    conn.close()


# ---------------- RUN ----------------

group = get_selected_group()

if not group:
    print("No group selected")
else:
    qlr_xml = group_to_qlr_xml(group)
    save_qlr_to_db(qlr_xml, group.name())
    print(f"Saved QLR for group: {group.name()}")