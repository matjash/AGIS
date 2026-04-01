import xml.etree.ElementTree as ET
import json
import psycopg2
import os

# CONFIGURE THESE
XML_PATH = r"c:\Users\matjaz\Downloads\RNO(1)\RNO.xml"
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'dbname': 'your_db',
    'user': 'your_user',
    'password': 'your_password'
}
TABLE_NAME = 'imported_xml'

# Parse XML
tree = ET.parse(XML_PATH)
root = tree.getroot()

# Find top-level tag name and children
def get_row_data(elem):
    row = {}
    children = list(elem)
    # Add attributes as columns
    for k, v in elem.attrib.items():
        row[k] = v
    # Add text if present and not just whitespace
    if elem.text and elem.text.strip():
        row['text'] = elem.text.strip()
    # If children, store as JSON
    if children:
        row['children'] = json.dumps([
            ET.tostring(child, encoding='unicode') for child in children
        ])
    return row

rows = [get_row_data(child) for child in root]

# Collect all possible columns
all_keys = set()
for row in rows:
    all_keys.update(row.keys())

# Prepare table
columns = list(all_keys)
col_defs = ', '.join([
    f'"{col}" TEXT' if col != 'children' else 'children JSON' for col in columns
])

# Connect to PostgreSQL
conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

# Create table
cur.execute(f'DROP TABLE IF EXISTS {TABLE_NAME}')
cur.execute(f'CREATE TABLE {TABLE_NAME} ({col_defs})')

# Insert rows
for row in rows:
    vals = [row.get(col) for col in columns]
    placeholders = ', '.join(['%s'] * len(columns))
    cur.execute(
        f'INSERT INTO {TABLE_NAME} ({", ".join(columns)}) VALUES ({placeholders})',
        vals
    )

conn.commit()
cur.close()
conn.close()

print(f"Imported {len(rows)} rows into {TABLE_NAME}.")
