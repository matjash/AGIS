"""Data for the eArheologija and eVRD tabs: the CPA copy first, geohub otherwise.

The table is filled from attributes only (fast, also for the ~32 000 eVRD
records). Geometry is fetched when it is needed: one record for "Pokaži
geometrijo", only ids for "Le v obsegu karte". No user interface here.
Attribute names are upper case, whatever the case in the source.
"""
import json

from qgis.core import Qgis, QgsGeometry, QgsProviderConnectionException

from . import config
from .externals import (arcgis_geometry, arcgis_query_all, cpa_available, cpa_comment_date, cpa_connection,
                        fetch_json, format_date, log, pg_ident, pg_literal, sql_value)

ID_FIELD = "OBJECTID"


class Source:
    """One dataset: a CPA table/view (config keys) and a geohub layer (config key)."""

    def __init__(self, name, cpa_schema_key, cpa_table_key, url_key):
        self.name = name
        self.cpa_schema_key, self.cpa_table_key, self.url_key = cpa_schema_key, cpa_table_key, url_key

    @property
    def cpa_table(self):
        return config.get(self.cpa_schema_key), config.get(self.cpa_table_key)

    @property
    def url(self):
        return config.get(self.url_key)


RESEARCH = Source("eArheologija", "cpa_research_schema", "cpa_research_table", "geohub_research_url")
EVRD = Source("eVRD", "cpa_evrd_schema", "cpa_evrd_table", "geohub_evrd_url")


class Data:
    """Rows (dicts of upper-case attributes) and where they came from."""

    def __init__(self, source, rows, origin, label, columns=None):
        self.source = source
        self.rows = rows
        self.origin = origin          # "cpa" or "geohub"
        self.label = label            # for the status line
        self.columns = columns or {}  # CPA: {UPPER: real column name, "#geom": geometry column}


# ---------------------------------------------------------------------------
# CPA copy
# ---------------------------------------------------------------------------
def cpa_columns(schema, table):
    """{UPPER NAME: real name} of a CPA table/view, plus "#geom" for its geometry column."""
    rows = cpa_connection().executeSql(
        "SELECT a.attname, t.typname FROM pg_attribute a JOIN pg_type t ON t.oid = a.atttypid "
        f"WHERE a.attrelid = {pg_literal(pg_ident(schema, table))}::regclass AND a.attnum > 0 "
        "AND NOT a.attisdropped ORDER BY a.attnum")
    columns = {}
    for name, type_name in rows:
        name, type_name = sql_value(name), sql_value(type_name)
        if type_name == "geometry" and "#geom" not in columns:
            columns["#geom"] = name
        else:
            columns[name.upper()] = name
    return columns


def _fetch_cpa(source):
    schema, table = source.cpa_table
    columns = cpa_columns(schema, table)
    geom = columns.get("#geom")
    record = "to_jsonb(t)" + (f" - {pg_literal(geom)}" if geom else "")
    rows = cpa_connection().executeSql(f"SELECT ({record})::text FROM {pg_ident(schema, table)} t")
    data = []
    for (text,) in rows:
        attrs = json.loads(sql_value(text) or "{}")
        data.append({k.upper(): v for k, v in attrs.items()})
    date = cpa_comment_date(schema, table)
    label = "baza CPA" + (f", kopija {format_date(date)}" if date else "")
    return Data(source, data, "cpa", label, columns)


# ---------------------------------------------------------------------------
# geohub
# ---------------------------------------------------------------------------
def _fetch_geohub(source):
    feats = arcgis_query_all(source.url, {"where": "1=1", "outFields": "*", "returnGeometry": "false"},
                             page_size=2000)
    rows = [{k.upper(): v for k, v in f.get("attributes", {}).items()} for f in feats]
    return Data(source, rows, "geohub", "geohub")


def fetch(task, source):
    """CPA copy if the database answers and has the table, else geohub (for a QgsTask)."""
    if cpa_available():
        try:
            return _fetch_cpa(source)
        except (QgsProviderConnectionException, ValueError) as e:
            log(f"{source.name}: kopija v bazi CPA ni dosegljiva, uporabljam geohub ({e})", Qgis.MessageLevel.Info)
    return _fetch_geohub(source)


def _id_column(data):
    column = data.columns.get(ID_FIELD)
    if not column:
        raise IOError(f"Kopija {data.source.name} v bazi CPA nima stolpca {ID_FIELD}.")
    return column


def geometries(task, data, ids):
    """{id: QgsGeometry in EPSG:3794} for the given record ids."""
    ids = [int(i) for i in ids if i is not None]
    if not ids:
        return {}
    if data.origin == "cpa":
        schema, table = data.source.cpa_table
        geom, key = data.columns.get("#geom"), _id_column(data)
        if not geom:
            return {}
        rows = cpa_connection().executeSql(
            f"SELECT {pg_ident(key)}, ST_AsText(ST_Transform({pg_ident(geom)}, 3794)) "
            f"FROM {pg_ident(schema, table)} WHERE {pg_ident(key)} IN ({', '.join(map(str, ids))})")
        return {int(sql_value(i)): QgsGeometry.fromWkt(sql_value(w) or "") for i, w in rows}
    feats = arcgis_query_all(data.source.url, {"objectIds": ",".join(map(str, ids)), "outFields": ID_FIELD,
                                               "returnGeometry": "true", "outSR": 3794})
    return {int(f["attributes"][ID_FIELD]): arcgis_geometry(f.get("geometry")) for f in feats}


def ids_in_rect(task, data, rect):
    """Set of record ids whose geometry intersects ``rect`` (QgsRectangle in EPSG:3794)."""
    box = (rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum())
    if data.origin == "cpa":
        schema, table = data.source.cpa_table
        geom, key = data.columns.get("#geom"), _id_column(data)
        if not geom:
            return set()
        g, t = pg_ident(geom), pg_ident(schema, table)
        srid = f"(SELECT ST_SRID({g}) FROM {t} WHERE {g} IS NOT NULL LIMIT 1)"
        env = f"ST_Transform(ST_MakeEnvelope({', '.join(repr(float(v)) for v in box)}, 3794), {srid})"
        rows = cpa_connection().executeSql(
            f"SELECT {pg_ident(key)} FROM {pg_ident(schema, table)} WHERE ST_Intersects({pg_ident(geom)}, {env})")
        return {int(sql_value(r[0])) for r in rows}
    js = fetch_json(data.source.url.rstrip("/") + "/query", {
        "where": "1=1", "geometry": ",".join(map(str, box)), "geometryType": "esriGeometryEnvelope",
        "inSR": 3794, "spatialRel": "esriSpatialRelIntersects", "returnIdsOnly": "true", "f": "json"})
    if "error" in js:
        raise IOError(js["error"].get("message", "ArcGIS napaka"))
    return set(js.get("objectIds") or [])
