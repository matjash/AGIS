"""Parcel search: CPA copy of the cadastre -> GURS WFS -> user's own layer.

No user interface here, so everything can be tested on its own. Network and
CPA calls may run in a QgsTask; the user's own layer is always read on the
main thread (it belongs to the project).
"""
import csv
import re
import time
from datetime import datetime

from qgis.core import (
    Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsExpression, QgsFeature, QgsFeatureRequest,
    QgsFields, QgsGeometry, QgsJsonUtils, QgsLayerMetadata, QgsMemoryProviderUtils, QgsProject,
    QgsProviderConnectionException, QgsSettings, QgsWkbTypes,
)

from . import config
from .externals import (cpa_available, cpa_comment_date, cpa_connection, format_date, http_get, log, pg_literal,
                        pg_ident, pn_path, profile_path, sql_value)

CRS = QgsCoordinateReferenceSystem("EPSG:3794")
WFS_PARCELS = "SI.GURS.KN:OSNOVNI_PARCELE"
WFS_KO = "SI.GURS.KN:KATASTRSKE_OBCINE"
WFS_MAX = 20000
KO_MAX_AGE_DAYS = 30
WFS_CHECK_SECONDS = 300

KEY_LAYER, KEY_KO_FIELD, KEY_PARC_FIELD, KEY_FIRST = (
    "agis/parcele/layer", "agis/parcele/ko_field", "agis/parcele/parcela_field", "agis/parcele/own_first")
KEY_SOURCE, KEY_PROVIDER = "agis/parcele/source", "agis/parcele/provider"

# Field names of the K.O. id and the parcel number in each remote source
WFS_KO_FIELD, WFS_PARCEL_FIELD = "KO_ID", "ST_PARCELE"


class Result:
    def __init__(self, features, fields, crs, source, date=None, authoritative=False,
                 ko_field=None, parcel_field=None):
        self.features = features
        self.ko_field = ko_field          # field names, for the text list of parcels
        self.parcel_field = parcel_field
        self.fields = fields
        self.crs = crs
        self.source = source              # text for the status line, e.g. "GURS WFS"
        self.date = date                  # copy date (datetime.date) or None
        self.authoritative = authoritative

    @property
    def label(self):
        return f"{self.source} ({format_date(self.date)})" if self.date else self.source


class NoSource(Exception):
    pass


# ---------------------------------------------------------------------------
# K.O. list
# ---------------------------------------------------------------------------
def ko_path():
    p = profile_path("ko.csv")
    return p if p.exists() else pn_path("plugin") / "ko.csv"


def load_ko():
    """{ko_id (int): name}"""
    with open(ko_path(), encoding="utf-8") as f:
        return {int(r["KO_ID"]): r["NAZIV"] for r in csv.DictReader(f) if r.get("KO_ID")}


def ko_needs_refresh():
    p = profile_path("ko.csv")
    return not p.exists() or (time.time() - p.stat().st_mtime) > KO_MAX_AGE_DAYS * 86400


def refresh_ko(task=None):
    """Download the K.O. list from GURS into the profile (background task)."""
    js = _wfs_json(WFS_KO, propertyName="KO_ID,NAZIV")
    rows = sorted({(int(f["properties"]["KO_ID"]), f["properties"]["NAZIV"]) for f in js.get("features", [])})
    if len(rows) < 2000:                  # Slovenia has ~2700 K.O.; anything less is a broken answer
        raise IOError(f"Seznam K.O. z GURS ni popoln ({len(rows)}).")
    target = profile_path("ko.csv")
    tmp = target.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["KO_ID", "NAZIV"])
        w.writerows(rows)
    tmp.replace(target)
    return len(rows)


def resolve_ko(text, ko):
    """K.O. id from '1722', '1722 - NAME' or 'NAME'. Returns (id, None) or (None, [matching ids])."""
    text = (text or "").strip()
    m = re.match(r"^(\d+)", text)
    if m:
        ko_id = int(m.group(1))
        return (ko_id, None) if ko_id in ko else (None, [])
    matches = [k for k, name in ko.items() if name.lower() == text.lower()]
    if len(matches) == 1:
        return matches[0], None
    if not matches and text:
        matches = [k for k, name in ko.items() if name.lower().startswith(text.lower())]
    return None, sorted(matches)


def ko_label(ko_id, ko):
    return f"{ko_id} - {ko.get(ko_id, '?')}"


def normalize_parcel(text):
    return re.sub(r"\s+", "", text or "")


def valid_parcel(text):
    """Parcel numbers are like 123, 123/4 (also 123/4a in some old K.O.)."""
    return bool(re.fullmatch(r"\d+[a-zA-Z]?(/\d+[a-zA-Z]?)?", text or ""))


def parcel_sort_key(p):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", str(p))]


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
def _wfs_json(type_name, **params):
    base = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": type_name,
            "outputFormat": "application/json"}
    base.update(params)
    text = http_get(config.get("gurs_wfs_url"), base, timeout_ms=20000).decode("utf-8")
    import json
    try:
        return json.loads(text)
    except ValueError:
        raise IOError(f"GURS WFS ni vrnil JSON: {text[:200]}")


def _wfs_features(type_name, **params):
    import json
    js = _wfs_json(type_name, srsName="EPSG:3794", count=WFS_MAX, **params)
    text = json.dumps(js)
    fields = QgsJsonUtils.stringToFields(text)
    feats = QgsJsonUtils.stringToFeatureList(text, fields)
    return feats, fields


_wfs_state = {"ok": None, "when": 0}


def wfs_reachable(refresh=False):
    """Quick check, remembered for a few minutes."""
    if refresh or _wfs_state["ok"] is None or time.time() - _wfs_state["when"] > WFS_CHECK_SECONDS:
        try:
            _wfs_json(WFS_PARCELS, count=1, propertyName="KO_ID")
            _wfs_state["ok"] = True
        except IOError as e:
            log(f"GURS WFS ni dosegljiv: {e}", Qgis.MessageLevel.Info)
            _wfs_state["ok"] = False
        _wfs_state["when"] = time.time()
    return _wfs_state["ok"]


# --- CPA copy of the cadastre: plain SQL (no QGIS layer, so the view's key
# column and SRID do not matter; geometry always comes back in EPSG:3794) ----
_cadastre_info = {}


def cadastre_info():
    """Columns, geometry SRID and K.O. column type of the CPA cadastre (remembered)."""
    schema, table = config.get("cpa_cadastre_schema"), config.get("cpa_cadastre_table")
    key = (config.get("cpa_host"), config.get("cpa_port"), config.get("cpa_database"), schema, table)
    if key not in _cadastre_info:
        conn = cpa_connection()
        t, g = pg_ident(schema, table), config.get("cpa_cadastre_geom")
        rows = conn.executeSql(
            "SELECT a.attname, format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
            f"WHERE a.attrelid = {pg_literal(t)}::regclass AND a.attnum > 0 AND NOT a.attisdropped")
        types = {sql_value(n): sql_value(ty) for n, ty in rows}
        if g not in types:
            raise IOError(f"Kopija KN v bazi CPA nima stolpca {g}.")
        srid_rows = conn.executeSql(f"SELECT ST_SRID({pg_ident(g)}) FROM {t} WHERE {pg_ident(g)} IS NOT NULL LIMIT 1")
        srid = int(sql_value(srid_rows[0][0]) or 0) if srid_rows else 0
        ko_type = types.get(config.get("cpa_cadastre_ko"), "")
        _cadastre_info[key] = {
            "table": t, "geom": g, "srid": srid,
            "ko_numeric": ko_type.split("(")[0] in ("integer", "smallint", "bigint", "numeric"),
        }
    return _cadastre_info[key]


def _ko_condition(info, ko_id):
    col = pg_ident(config.get("cpa_cadastre_ko"))
    n = int(ko_id)
    if info["ko_numeric"]:
        return f"{col} = {n}"
    variants = sorted({str(n)} | {str(n).zfill(w) for w in range(2, 7)})
    return f"{col}::text IN ({', '.join(pg_literal(v) for v in variants)})"


def _geom_3794(info):
    g = pg_ident(info["geom"])
    return f"ST_SetSRID({g}, 3794)" if info["srid"] == 0 else f"ST_Transform({g}, 3794)"


def _in_table_srid(info, wkt):
    """SQL for a EPSG:3794 WKT geometry in the table's SRID (so the spatial index is used)."""
    src = f"ST_GeomFromText({pg_literal(wkt)}, 3794)"
    if info["srid"] == 0:
        return f"ST_SetSRID({src}, 0)"
    return src if info["srid"] == 3794 else f"ST_Transform({src}, {info['srid']})"


def _cpa_query(where):
    """Features of the CPA cadastre matching ``where``, as a Result (EPSG:3794)."""
    import json
    info = cadastre_info()
    g = pg_ident(info["geom"])
    sql = (f"SELECT json_build_object('type', 'Feature', "
           f"'properties', to_jsonb(t) - {pg_literal(info['geom'])}, "
           f"'geometry', ST_AsGeoJSON({_geom_3794(info)})::json)::text "
           f"FROM {info['table']} t WHERE {g} IS NOT NULL AND {where}")
    rows = cpa_connection().executeSql(sql)
    feats_json = [json.loads(sql_value(r[0])) for r in rows]
    text = json.dumps({"type": "FeatureCollection", "features": feats_json})
    fields = QgsJsonUtils.stringToFields(text)
    feats = QgsJsonUtils.stringToFeatureList(text, fields) if feats_json else []
    return Result(feats, fields, CRS, "lokalna kopija KN", cpa_copy_date(), False,
                  config.get("cpa_cadastre_ko"), config.get("cpa_cadastre_parcela"))


def cpa_copy_date():
    """Copy date of the CPA cadastre, from the view's comment ('Datum zadnje posodobitve: YYYY-MM-DD')."""
    return cpa_comment_date(config.get("cpa_cadastre_schema"), config.get("cpa_cadastre_table"))


def _layer_result(layer, request, source, date=None, ko_field=None, parcel_field=None):
    feats = list(layer.getFeatures(request))
    return Result(feats, layer.fields(), layer.crs(), source, date, False, ko_field, parcel_field)


def _equality(layer, field, value, number=False):
    """Expression "field" = value, with the value typed like the field (number or text).
    number=True: a text field may hold the number with leading zeros ("0505" = 505)."""
    idx = layer.fields().indexOf(field)
    if idx < 0:
        raise ValueError(f"Sloj »{layer.name()}« nima polja »{field}«.")
    if layer.fields().at(idx).isNumeric():
        try:
            value = int(value)
        except ValueError:
            return "FALSE"
        return QgsExpression.createFieldEqualityExpression(field, value)
    if number:
        try:
            n = int(value)
        except ValueError:
            return "FALSE"
        variants = sorted({str(n)} | {str(n).zfill(w) for w in range(2, 7)})
        return f"{QgsExpression.quotedColumnRef(field)} IN ({', '.join(QgsExpression.quotedString(v) for v in variants)})"
    return QgsExpression.createFieldEqualityExpression(field, str(value))


# --- find one parcel ------------------------------------------------------
def find_cpa(ko_id, parcela):
    try:
        info = cadastre_info()
        parc = pg_ident(config.get("cpa_cadastre_parcela"))
        return _cpa_query(f"{_ko_condition(info, ko_id)} AND {parc}::text = {pg_literal(str(parcela))}")
    except QgsProviderConnectionException as e:
        raise IOError(f"Kopija KN v bazi CPA ni dosegljiva: {e}")


def find_wfs(ko_id, parcela):
    parcela = parcela.replace("'", "''")
    feats, fields = _wfs_features(WFS_PARCELS, CQL_FILTER=f"KO_ID={int(ko_id)} AND ST_PARCELE='{parcela}'")
    return Result(feats, fields, CRS, "GURS WFS", None, True, WFS_KO_FIELD, WFS_PARCEL_FIELD)


def find_layer(layer, ko_field, parcel_field, ko_id, parcela):
    expr = f"{_equality(layer, ko_field, ko_id, number=True)} AND {_equality(layer, parcel_field, parcela)}"
    return _layer_result(layer, QgsFeatureRequest(QgsExpression(expr)), layer.name(), None, ko_field, parcel_field)


def find_remote(task, ko_id, parcela, skip_cpa=False):
    """CPA copy, then GURS WFS (for a QgsTask). Returns Result or None if neither answered."""
    last = None
    if not skip_cpa and cpa_available():
        try:
            last = find_cpa(ko_id, parcela)
            if last.features:
                return last
        except IOError as e:
            log(str(e), Qgis.MessageLevel.Warning)
    if wfs_reachable():
        return find_wfs(ko_id, parcela)
    return last


# --- parcels under a geometry ---------------------------------------------
def _area_filter(request, geom):
    request.setFilterRect(geom.boundingBox())
    return request


def _intersecting(feats, geom):
    engine = QgsGeometry.createGeometryEngine(geom.constGet())
    engine.prepareGeometry()
    return [f for f in feats if f.hasGeometry() and engine.intersects(f.geometry().constGet())]


def intersect_cpa(geom):
    try:
        info = cadastre_info()
        area = _in_table_srid(info, geom.asWkt())
        g = pg_ident(info["geom"])
        return _cpa_query(f"{g} && {area} AND ST_Intersects({g}, {area})")
    except QgsProviderConnectionException as e:
        raise IOError(f"Kopija KN v bazi CPA ni dosegljiva: {e}")


def intersect_wfs(geom):
    b = geom.boundingBox()
    feats, fields = _wfs_features(WFS_PARCELS, bbox=f"{b.xMinimum()},{b.yMinimum()},{b.xMaximum()},{b.yMaximum()},EPSG:3794")
    if len(feats) >= WFS_MAX:
        raise IOError(f"Območje je preveliko (več kot {WFS_MAX} parcel).")
    return Result(_intersecting(feats, geom), fields, CRS, "GURS WFS", None, True, WFS_KO_FIELD, WFS_PARCEL_FIELD)


def intersect_layer(layer, geom, ko_field=None, parcel_field=None):
    xf = QgsCoordinateTransform(CRS, layer.crs(), QgsProject.instance())
    g = QgsGeometry(geom)
    g.transform(xf)
    r = _layer_result(layer, _area_filter(QgsFeatureRequest(), g), layer.name(), None, ko_field, parcel_field)
    r.features = _intersecting(r.features, g)
    return r


def intersect_remote(task, geom, skip_cpa=False):
    if not skip_cpa and cpa_available():
        try:
            return intersect_cpa(geom)
        except IOError as e:
            log(str(e), Qgis.MessageLevel.Warning)
    if wfs_reachable():
        return intersect_wfs(geom)
    return None


def area_geometry(layer, selected_only=False, buffer_m=0.0):
    """Union of the layer's (selected) features in EPSG:3794, optionally buffered
    (a negative buffer shrinks the area)."""
    feats = layer.selectedFeatures() if selected_only else list(layer.getFeatures())
    geoms = [QgsGeometry(f.geometry()) for f in feats if f.hasGeometry()]
    if not geoms:
        raise ValueError("Sloj nima (izbranih) objektov.")
    xf = QgsCoordinateTransform(layer.crs(), CRS, QgsProject.instance())
    for g in geoms:
        g.transform(xf)
    geom = QgsGeometry.unaryUnion(geoms)
    if buffer_m:
        geom = geom.buffer(buffer_m, 8)
        if geom.isNull() or geom.isEmpty() or geom.area() <= 0:
            raise ValueError(f"Z odmikom {buffer_m:g} m od območja ne ostane nič.")
    return geom


# --- parcel numbers for suggestions ----------------------------------------
def parcel_numbers_remote(task, ko_id):
    if cpa_available():
        try:
            info = cadastre_info()
            col = pg_ident(config.get("cpa_cadastre_parcela"))
            rows = cpa_connection().executeSql(
                f"SELECT DISTINCT {col}::text FROM {info['table']} WHERE {_ko_condition(info, ko_id)}")
            numbers = sorted({str(sql_value(r[0])) for r in rows if sql_value(r[0])}, key=parcel_sort_key)
            if numbers:
                return numbers
        except (QgsProviderConnectionException, IOError) as e:
            log(f"Seznam parcel iz baze CPA ni dosegljiv: {e}", Qgis.MessageLevel.Info)
    if wfs_reachable():
        js = _wfs_json(WFS_PARCELS, propertyName="ST_PARCELE", CQL_FILTER=f"KO_ID={int(ko_id)}", count=WFS_MAX)
        return sorted({f["properties"]["ST_PARCELE"] for f in js.get("features", [])}, key=parcel_sort_key)
    return []


def parcel_numbers_layer(layer, ko_field, parcel_field, ko_id):
    req = QgsFeatureRequest(QgsExpression(_equality(layer, ko_field, ko_id, number=True)))
    flags = getattr(Qgis, "FeatureRequestFlag", None)
    req.setFlags(flags.NoGeometry if flags else QgsFeatureRequest.NoGeometry)
    req.setSubsetOfAttributes([parcel_field], layer.fields())
    return sorted({str(f[parcel_field]) for f in layer.getFeatures(req)}, key=parcel_sort_key)


# ---------------------------------------------------------------------------
# Own layer settings
# ---------------------------------------------------------------------------
def own_settings():
    """(name, ko_field, parcel_field, own_first) of the user's own parcel layer."""
    s = QgsSettings()
    return (s.value(KEY_LAYER, ""), s.value(KEY_KO_FIELD, ""), s.value(KEY_PARC_FIELD, ""),
            s.value(KEY_FIRST, False, type=bool))


def own_source():
    """(source, provider) of the own layer, or ("", "")."""
    s = QgsSettings()
    return s.value(KEY_SOURCE, ""), s.value(KEY_PROVIDER, "")


def can_be_own_layer(layer):
    """None if the layer can be remembered, else the reason (text)."""
    if layer is None:
        return "Ni sloja."
    if layer.providerType() in ("memory", "virtual"):
        return "Začasnega sloja ni mogoče shraniti – shranite ga v datoteko ali bazo."
    if not layer.source():
        return "Sloj nima vira."
    return None


def save_own_layer(layer, ko_field="", parcel_field=""):
    """Remember the layer by its source, so it works in any project."""
    reason = can_be_own_layer(layer)
    if reason:
        raise ValueError(reason)
    s = QgsSettings()
    s.setValue(KEY_LAYER, layer.name())
    s.setValue(KEY_SOURCE, layer.source())
    s.setValue(KEY_PROVIDER, layer.providerType())
    s.setValue(KEY_KO_FIELD, ko_field or guess_field(layer.fields(), "ko"))
    s.setValue(KEY_PARC_FIELD, parcel_field or guess_field(layer.fields(), "parcela"))
    _own_cache.clear()


def save_own_fields(ko_field, parcel_field):
    s = QgsSettings()
    s.setValue(KEY_KO_FIELD, ko_field or "")
    s.setValue(KEY_PARC_FIELD, parcel_field or "")


def clear_own_layer():
    s = QgsSettings()
    for k in (KEY_LAYER, KEY_SOURCE, KEY_PROVIDER, KEY_KO_FIELD, KEY_PARC_FIELD):
        s.remove(k)
    _own_cache.clear()


_own_cache = {}


def open_own_layer():
    """The own layer, opened from its saved source (not added to the project), or None."""
    from qgis.core import QgsVectorLayer
    name, _, _, _ = own_settings()
    source, provider = own_source()
    if not source:
        # settings from before 2.0: only the layer name - use it if it is in this project
        layers = QgsProject.instance().mapLayersByName(name) if name else []
        return layers[0] if layers else None
    key = (source, provider)
    layer = _own_cache.get(key)
    if layer is None or not layer.isValid():
        layer = QgsVectorLayer(source, name or "lasten sloj parcel", provider or "ogr")
        if not layer.isValid():
            log(f"Lastnega sloja parcel ni mogoče odpreti: {name}", Qgis.MessageLevel.Warning)
            return None
        _own_cache.clear()
        _own_cache[key] = layer
    return layer


def own_layer():
    """(layer, ko_field, parcel_field) if the own layer is set and can be opened, else None."""
    name, ko_field, parcel_field, _ = own_settings()
    if not (ko_field and parcel_field):
        return None
    layer = open_own_layer()
    if layer is not None and layer.fields().indexOf(ko_field) >= 0 and layer.fields().indexOf(parcel_field) >= 0:
        return layer, ko_field, parcel_field
    return None


def guess_field(fields, kind):
    patterns = {"ko": r"^(sifko|ko_?id|ko|sif_?ko|ko_?sifra|sifra_?ko)$",
                "parcela": r"^(parcela|st_?parcele|parc_?st|stparc|parcelna_?st|st_?parc)$"}[kind]
    for f in fields:
        if re.match(patterns, f.name(), re.I):
            return f.name()
    return ""


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def parcel_pairs(result):
    """{(ko_id, parcel number)} from a result (K.O. id as int where possible)."""
    if not (result.ko_field and result.parcel_field):
        raise ValueError("Vir nima podatka o K.O. in številki parcele.")
    pairs = set()
    for f in result.features:
        ko_value, parcel = f[result.ko_field], f[result.parcel_field]
        if parcel is None or str(parcel) in ("", "NULL"):
            continue
        try:
            ko_value = int(str(ko_value).strip())
        except ValueError:
            ko_value = str(ko_value).strip()
        pairs.add((ko_value, str(parcel).strip()))
    return pairs


def parcel_list_text(pairs, ko):
    """Parcels as text, one line per K.O.:
    123/1, 123/2, 125 in 130/4, vse k. o. TRNOVSKO PREDMESTJE (1722);
    7, k. o. VIČ (1723)"""
    by_ko = {}
    for ko_id, parcel in pairs:
        by_ko.setdefault(ko_id, set()).add(parcel)
    lines = []
    for ko_id in sorted(by_ko, key=lambda k: (0, k, "") if isinstance(k, int) else (1, 0, str(k))):
        parcels = sorted(by_ko[ko_id], key=parcel_sort_key)
        numbers = parcels[0] if len(parcels) == 1 else ", ".join(parcels[:-1]) + " in " + parcels[-1]
        name = (ko.get(ko_id) or "?").upper()
        lines.append(f"{numbers}, {'vse k. o.' if len(parcels) > 1 else 'k. o.'} {name} ({ko_id})")
    return ";\n".join(lines)


def to_memory_layer(result, name):
    """Copy the result into a temporary layer with source and date in its metadata."""
    geoms = [f.geometry() for f in result.features if f.hasGeometry()]
    default = getattr(Qgis, "WkbType", QgsWkbTypes).MultiPolygon
    wkb = QgsWkbTypes.multiType(geoms[0].wkbType()) if geoms else default
    fields = result.fields if result.fields is not None else QgsFields()
    layer = QgsMemoryProviderUtils.createMemoryLayer(name, fields, wkb, result.crs)
    feats = []
    for f in result.features:
        g = QgsGeometry(f.geometry())
        g.convertToMultiType()
        nf = QgsFeature(fields)
        nf.setAttributes(f.attributes()[:fields.count()])
        nf.setGeometry(g)
        feats.append(nf)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    md = QgsLayerMetadata()
    md.setTitle(name)
    md.setAbstract(f"Pridobljeno {datetime.now():%d. %m. %Y %H:%M}, vir: {result.label}.")
    layer.setMetadata(md)
    return layer


def zoom_and_flash(canvas, result):
    geoms = [f.geometry() for f in result.features if f.hasGeometry()]
    if not geoms:
        return
    xf = QgsCoordinateTransform(result.crs, canvas.mapSettings().destinationCrs(), QgsProject.instance())
    box = xf.transformBoundingBox(QgsGeometry.unaryUnion(geoms).boundingBox())
    box.scale(1.5)
    canvas.setExtent(box)
    canvas.refresh()
    canvas.flashGeometries(geoms, result.crs)
