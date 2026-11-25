"""Is a catalogue source reachable from this computer? (run in the background)

Each layer in a QLR is checked by its kind of source:
- file or network path (also the tiles of a VRT): does it exist?
- CPA database: the cached CPA check; another database: a short socket test
- web services: one small request per service (ArcGIS REST: service info; WMS/WMTS/WFS:
  capabilities, and whether the layer is listed); XYZ tiles and COG URLs are assumed fine
Results are cached until the next refresh (↺); a service shared by several layers is asked once."""
import os
import re
import socket
import threading
import json
import xml.etree.ElementTree as ET
from urllib.parse import parse_qsl, urlencode, unquote

from qgis.core import QgsDataSourceUri

from . import config
from .externals import cpa_available, http_get

WEB_TIMEOUT_MS = 10000
ARCGIS_PROVIDERS = {"arcgismapserver", "arcgisfeatureserver"}
OTHER_WEB = {"wcs", "vectortile", "oapif", "mbtilesvectortiles"}
_cache = {}
_locks = {}
_locks_lock = threading.Lock()


def clear_cache():
    _cache.clear()


def _cached(key, fn):
    """Cached result; with several checks running at once, a shared service is asked once."""
    if key in _cache:
        return _cache[key]
    with _locks_lock:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        if key not in _cache:
            _cache[key] = fn()
    return _cache[key]


def _host_open(host, port, timeout=0.3):
    try:
        with socket.create_connection((host, int(port or 5432)), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def _path_exists(path):
    return _cached(("path", path), lambda: os.path.exists(path))


def layers_of(qlr):
    """[(layer name, provider, datasource)] of the layers in a QLR."""
    try:
        root = ET.fromstring(qlr or "")
    except ET.ParseError:
        return []
    out = []
    for ml in root.iter("maplayer"):
        name = (ml.findtext("layername") or "").strip()
        provider = (ml.findtext("provider") or "").strip()
        source = ml.findtext("datasource") or ""
        out.append((name, provider, source))
    return out


def _file_part(source):
    """The file path of an OGR/GDAL source, or None if it is not a plain file/network path."""
    path = source.split("|")[0].strip()
    if not path or path.startswith(("/vsicurl", "/vsis3", "/vsiaz", "/vsigs", "http://", "https://", "<")):
        return None
    if re.match(r"^[A-Za-z]+:(?![\\/])", path):        # PG:, WMS:, GPKG:… not a file
        return None
    if path.startswith(("/vsizip/", "/vsigzip/")):
        path = path.split("/", 2)[2]
    return path


def _with_params(url, params):
    return url + ("&" if "?" in url else "?") + urlencode(params)


def _fetch(url):
    """(text, None) or (None, reason)."""
    def get():
        try:
            return http_get(url, timeout_ms=WEB_TIMEOUT_MS).decode("utf-8", errors="replace"), None
        except IOError as e:
            message = str(e)
            if "403" in message or "Forbidden" in message:
                return None, "storitev zavrne dostop (403)"
            if "404" in message or "Not Found" in message:
                return None, "storitev ne obstaja (404)"
            return None, "storitev se ne odziva"
    return _cached(("url", url), get)


def _check_arcgis(source):
    m = re.search(r"url='([^']+)'", source) or re.search(r"url=(\S+)", source)
    if not m:
        return None
    url = m.group(1)
    text, reason = _fetch(_with_params(url, {"f": "json"}))
    if reason:
        return reason
    try:
        js = json.loads(text)
    except ValueError:
        return "storitev ni vrnila pričakovanega odgovora"
    err = js.get("error") if isinstance(js, dict) else None
    if err:
        code, msg = err.get("code"), err.get("message") or ""
        if code == 499 or "token" in msg.lower():
            return "storitev zahteva prijavo (žeton) – morda deluje le v državnem omrežju"
        if code == 404:
            return "storitev ne obstaja več (404)"
        return f"napaka storitve: {msg or code}"
    return None


def _check_ogc(provider, source):
    """WMS/WMTS/WFS: capabilities answer, and the layer is listed in them."""
    if provider == "wms":
        params = dict(parse_qsl(source, keep_blank_values=True))
        if params.get("type") == "xyz" or "url" not in params:
            return None
        url, layer = unquote(params["url"]), params.get("layers", "").split(",")[0]
        service = "WMTS" if params.get("tileMatrixSet") else "WMS"
    else:                                                 # WFS
        url = (re.search(r"url='([^']+)'", source) or [None, None])[1]
        layer = (re.search(r"typename='([^']+)'", source) or [None, ""])[1]
        service = "WFS"
        if not url:
            return None
    text, reason = _fetch(_with_params(url, {"SERVICE": service, "REQUEST": "GetCapabilities"}))
    if reason:
        return reason
    if "ExceptionReport" in text[:2000] or "ServiceException" in text[:2000]:
        return "storitev vrne napako"
    if layer and layer not in text:
        return f"sloja {layer} ni več v storitvi"
    return None


def check_source(provider, source):
    """None if reachable, else a short reason (Slovene)."""
    if provider in ARCGIS_PROVIDERS:
        return _check_arcgis(source)
    if provider in ("wms", "WFS", "wfs"):
        return _check_ogc(provider.lower(), source)
    if provider in OTHER_WEB or provider in ("memory", "virtual", ""):
        return None
    if provider in ("postgres", "postgresraster", "mssql", "oracle", "hana"):
        uri = QgsDataSourceUri(source)
        host, port = uri.host(), uri.port()
        if not host:
            return None
        if host == config.get("cpa_host") and str(port or "5432") == str(config.get("cpa_port")):
            ok = cpa_available()
        else:
            ok = _cached(("host", host, port), lambda: _host_open(host, port))
        return None if ok else f"baza na {host} ni dosegljiva"
    if source.lstrip().startswith("<VRTDataset"):          # VRT kept as text: check its first tiles
        return _vrt_tiles_missing(source, None)
    path = _file_part(source)
    if path is None:
        return None
    if not _path_exists(path):
        drive = re.match(r"^([A-Za-z]:)", path)
        hint = f" (pogon {drive.group(1)} ni povezan?)" if drive else ""
        return f"{path} ni dosegljiv{hint}"
    if path.lower().endswith(".vrt"):                      # VRT file: its first tiles too
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                text = f.read(200000)
        except OSError:
            return None
        return _vrt_tiles_missing(text, os.path.dirname(path))
    return None


def _vrt_tiles_missing(text, folder):
    """Reason if one of the first tiles of a VRT is missing, else None."""
    for attrs, name in re.findall(r"<SourceFilename([^>]*)>([^<]+)<", text)[:3]:
        name = name.strip()
        if 'relativeToVRT="1"' in attrs:
            if folder is None:
                continue
            name = os.path.join(folder, name)
        if not _path_exists(name):
            return f"{name} ni dosegljiv"
    return None


def check_qlr(qlr):
    """[(layer name, reason)] of the unreachable layers of a QLR (empty list = all reachable)."""
    missing = []
    for name, provider, source in layers_of(qlr):
        reason = check_source(provider, source)
        if reason:
            missing.append((name, reason))
    return missing


NO_ANSWER = ("storitev se ne odziva", "baza na ")


def blocks_qgis(reason):
    """True if QGIS would hang on this layer until a timeout (no answer at all).
    Layers whose server answers with an error, or missing files, fail fast."""
    return reason.startswith(NO_ANSWER)


def check_entry(e):
    """(missing layers, number of layers) of one catalogue entry."""
    qlr = e.get("qlr") or ""
    return check_qlr(qlr), len(layers_of(qlr))


def check_entries(task, entries):
    """{entry id: (missing layers, total layers)} for a QgsTask."""
    out = {}
    for e in entries:
        if task is not None and task.isCanceled():
            break
        qlr = e.get("qlr") or ""
        out[e["id"]] = (check_qlr(qlr), len(layers_of(qlr)))
    return out


def without_layers(qlr, names):
    """The QLR without the layers with these names (tree nodes and layer definitions)."""
    try:
        root = ET.fromstring(qlr)
    except ET.ParseError:
        return qlr
    names = set(names)
    ids = set()
    for ml_parent in root.iter("maplayers"):
        for ml in list(ml_parent):
            if (ml.findtext("layername") or "").strip() in names:
                ids.add(ml.findtext("id"))
                ml_parent.remove(ml)
    for parent in root.iter():
        for child in list(parent):
            if child.tag == "layer-tree-layer" and child.get("id") in ids:
                parent.remove(child)
    return "<!DOCTYPE qgis-layer-definition>\n" + ET.tostring(root, encoding="unicode")
