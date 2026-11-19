"""Shared helpers: plugin paths, CPA database access, web requests."""
import json
import socket
from pathlib import Path
from urllib.parse import urlencode

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsBlockingNetworkRequest,
    QgsDataSourceUri,
    QgsGeometry,
    QgsMessageLog,
    QgsPointXY,
    QgsVectorLayer,
)

from . import config

PLUGIN_DIR = Path(__file__).resolve().parent
LOG_TAG = "AGIS"


def log(msg, level=Qgis.MessageLevel.Info):
    QgsMessageLog.logMessage(str(msg), LOG_TAG, level)


def pn_path(item):
    """Path to the plugin folder ('plugin') or one of its subfolders ('icons', 'catalogue', ...)."""
    return PLUGIN_DIR if item == "plugin" else PLUGIN_DIR / item


def profile_path(name=""):
    """Folder for AGIS data in the user's QGIS profile (survives plugin updates)."""
    folder = Path(QgsApplication.qgisSettingsDirPath()) / "agis"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name if name else folder


def enum(owner, scope, name):
    """Enum member that works with both scoped (Qt6/QGIS 4) and flat (Qt5) bindings."""
    return getattr(getattr(owner, scope, owner), name)


# ---------------------------------------------------------------------------
# CPA database
# ---------------------------------------------------------------------------
_cpa_state = None


def cpa_available(refresh=False, timeout=0.3):
    """True if the CPA database answers. Checked once and remembered; refresh=True checks again."""
    global _cpa_state
    if _cpa_state is None or refresh:
        try:
            with socket.create_connection((config.get("cpa_host"), int(config.get("cpa_port"))), timeout=timeout):
                _cpa_state = True
        except (OSError, ValueError):
            _cpa_state = False
    return _cpa_state


def cpa_uri(schema, table, geom=None, key="id", sql="", authcfg=None):
    """QgsDataSourceUri for a CPA table, with the shared cpa account or an auth config."""
    uri = QgsDataSourceUri()
    host, port, db = config.get("cpa_host"), config.get("cpa_port"), config.get("cpa_database")
    if authcfg:
        uri.setConnection(host, port, db, "", "")
        uri.setAuthConfigId(authcfg)
    else:
        uri.setConnection(host, port, db, config.get("cpa_user"), config.get("cpa_password"))
    uri.setDataSource(schema, table, geom, sql, key)
    return uri


def cpa_layer(schema, table, geom=None, key="id", sql="", name=None, authcfg=None):
    """Postgres layer from the CPA database (not added to the project)."""
    uri = cpa_uri(schema, table, geom, key, sql, authcfg)
    return QgsVectorLayer(uri.uri(False), name or table, "postgres")


def get_work_layers(*_ignored):
    return cpa_layer(config.get("cpa_work_schema"), config.get("cpa_work_table"), None, "id")


# --- SQL on the CPA database (no psycopg2: QGIS's own connection API) -------
def cpa_connection(user=None, password=None):
    """QGIS database connection to CPA; the shared cpa account unless a login is given.
    Raises QgsProviderConnectionException (message without the password)."""
    from qgis.core import QgsProviderConnectionException, QgsProviderRegistry
    uri = QgsDataSourceUri()
    uri.setConnection(config.get("cpa_host"), config.get("cpa_port"), config.get("cpa_database"),
                      user if user is not None else config.get("cpa_user"),
                      password if password is not None else config.get("cpa_password"))
    md = QgsProviderRegistry.instance().providerMetadata("postgres")
    try:
        conn = md.createConnection(uri.uri(False), {})
        conn.executeSql("SELECT 1")
        return conn
    except QgsProviderConnectionException as e:
        raise QgsProviderConnectionException(hide_passwords(str(e)))


_comment_dates = {}


def cpa_comment_date(schema, table):
    """Copy date from a CPA table/view comment ("Datum zadnje posodobitve: YYYY-MM-DD"), or None.
    Remembered per host and table."""
    import re
    from datetime import datetime
    from qgis.core import QgsProviderConnectionException
    key = (config.get("cpa_host"), schema, table)
    if key not in _comment_dates:
        date = None
        try:
            rows = cpa_connection().executeSql(
                f"SELECT obj_description({pg_literal(pg_ident(schema, table))}::regclass, 'pg_class')")
            comment = sql_value(rows[0][0]) if rows else None
            m = re.search(r"Datum zadnje posodobitve:\s*(\d{4}-\d{2}-\d{2})", comment or "")
            if m:
                date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except (QgsProviderConnectionException, ValueError) as e:
            log(f"Datum kopije {schema}.{table} ni znan: {e}", Qgis.MessageLevel.Info)
        _comment_dates[key] = date
    return _comment_dates[key]


def format_date(date):
    return f"{date.day}. {date.month}. {date.year}" if date else ""


def hide_passwords(text):
    import re
    return re.sub(r"(password=)('[^']*'|\S+)", r"\1***", str(text))


def sql_value(value):
    """Python value from executeSql (NULL QVariant -> None, QDateTime -> ISO text)."""
    from qgis.PyQt.QtCore import QDateTime, QVariant
    if isinstance(value, QVariant):
        return None if value.isNull() else value.value()
    if isinstance(value, QDateTime):
        return value.toString("yyyy-MM-dd HH:mm:ss")
    return value


def pg_ident(*parts):
    return ".".join('"' + str(p).replace('"', '""') + '"' for p in parts)


def pg_literal(value):
    """Safe SQL literal (dollar-quoted text, so any QLR content is fine)."""
    import secrets
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    while True:
        tag = "$agis" + secrets.token_hex(4) + "$"
        if tag not in text:
            return tag + text + tag


# ---------------------------------------------------------------------------
# Web requests - through QGIS network settings (proxy, certificates),
# with a timeout; safe to call from a background QgsTask.
# ---------------------------------------------------------------------------
def http_get(url, params=None, timeout_ms=20000):
    full = url + ("?" + urlencode(params) if params else "")
    request = QNetworkRequest(QUrl(full))
    if hasattr(request, "setTransferTimeout"):
        request.setTransferTimeout(timeout_ms)
    blocking = QgsBlockingNetworkRequest()
    err = blocking.get(request, True)
    if err != enum(QgsBlockingNetworkRequest, "ErrorCode", "NoError"):
        raise IOError(blocking.errorMessage() or f"Napaka pri dostopu do {url}")
    return bytes(blocking.reply().content())


def fetch_json(url, params=None, timeout_ms=20000):
    text = http_get(url, params, timeout_ms).decode("utf-8")
    try:
        return json.loads(text)
    except ValueError:
        raise IOError(f"Strežnik ni vrnil JSON: {text[:200]}")


def arcgis_query_all(layer_url, params, page_size=1000):
    """ArcGIS REST /query, following pagination (exceededTransferLimit)."""
    features, offset = [], 0
    while True:
        page = dict(params, f="json", resultOffset=offset, resultRecordCount=page_size)
        js = fetch_json(layer_url.rstrip("/") + "/query", page)
        if "error" in js:
            raise IOError(js["error"].get("message", "ArcGIS napaka"))
        batch = js.get("features", [])
        features.extend(batch)
        if not batch or not js.get("exceededTransferLimit"):
            return features
        offset += len(batch)


def arcgis_geometry(g):
    """ArcGIS JSON geometry -> QgsGeometry (empty geometry if missing/unknown)."""
    if not g:
        return QgsGeometry()
    if "x" in g and "y" in g:
        return QgsGeometry.fromPointXY(QgsPointXY(g["x"], g["y"]))
    if "rings" in g:
        return QgsGeometry.fromPolygonXY([[QgsPointXY(p[0], p[1]) for p in r] for r in g["rings"]])
    if "paths" in g:
        paths = [[QgsPointXY(p[0], p[1]) for p in path] for path in g["paths"]]
        return QgsGeometry.fromPolylineXY(paths[0]) if len(paths) == 1 else QgsGeometry.fromMultiPolylineXY(paths)
    return QgsGeometry()
