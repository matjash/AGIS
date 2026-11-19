"""Turn selected layers/groups into QLR text, check it before it is shared, load it back."""
import base64
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from qgis.PyQt.QtXml import QDomDocument
from qgis.core import (QgsDataSourceUri, QgsLayerDefinition, QgsLayerTree, QgsLayerTreeGroup, QgsPathResolver,
                       QgsProject, QgsReadWriteContext)

from . import config

DB_PROVIDERS = {"postgres", "postgresraster", "oracle", "mssql", "hana", "db2"}
WEB_PROVIDERS = {"wms", "WFS", "wfs", "arcgismapserver", "arcgisfeatureserver", "wcs", "vectortile",
                 "OAPIF", "xyzvectortiles"}
FILE_PROVIDERS = {"ogr", "gdal", "delimitedtext", "spatialite", "virtual", "mdal", "pdal"}
IMAGE_EXT = (".svg", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")


class QlrError(Exception):
    pass


# ---------------------------------------------------------------------------
def export_nodes(nodes):
    """QLR text for the given layer tree nodes (absolute paths, so they can be checked)."""
    if not nodes:
        raise QlrError("Ni izbranih slojev ali skupin.")
    doc = QDomDocument("qgis-layer-definition")
    context = QgsReadWriteContext()
    context.setPathResolver(QgsPathResolver())
    ok, err = QgsLayerDefinition.exportLayerDefinition(doc, nodes, context)
    if not ok:
        raise QlrError(err or "Izvoz QLR ni uspel.")
    return doc.toString()


def load_qlr(qlr_text, project=None, group=None, index=None):
    """Load a QLR into ``group`` (default: the project root) at position ``index``
    (None = at the end). Returns the number of top-level nodes added."""
    project = project or QgsProject.instance()
    group = group or project.layerTreeRoot()
    doc = QDomDocument()
    parsed = doc.setContent(qlr_text)
    ok = parsed[0] if isinstance(parsed, tuple) else bool(parsed)
    if not ok:
        raise QlrError("Neveljaven QLR.")
    # Load into a detached group first, then move the nodes to the wanted place.
    staging = QgsLayerTreeGroup()
    ok, err = QgsLayerDefinition.loadLayerDefinition(doc, project, staging, QgsReadWriteContext())
    if not ok:
        raise QlrError(err or "Nalaganje QLR ni uspelo.")
    nodes = [child.clone() for child in staging.children()]
    if index is None or index < 0 or index > len(group.children()):
        index = len(group.children())
    group.insertChildNodes(index, nodes)
    return len(nodes)


def tree_position(view):
    """(group, index) for new layers: above the selected layer, at the top of the
    selected group, otherwise at the top of the layer tree."""
    root = QgsProject.instance().layerTreeRoot()
    node = view.currentNode() if view is not None else None
    if node is None:
        return root, 0
    if QgsLayerTree.isGroup(node):
        return node, 0
    parent = node.parent() or root
    return parent, parent.children().index(node)


def drop_position(view, pos):
    """(group, index) for a drop at ``pos`` (viewport coordinates) in the layer tree view:
    on a group -> top of the group, upper/lower half of a layer -> above/below it,
    empty space -> the end of the tree."""
    root = QgsProject.instance().layerTreeRoot()
    index = view.indexAt(pos)
    node = view.index2node(index) if index.isValid() else None
    if node is None:
        return root, len(root.children())
    if QgsLayerTree.isGroup(node):
        return node, 0
    parent = node.parent() or root
    row = parent.children().index(node)
    rect = view.visualRect(index)
    return parent, row + (1 if pos.y() > rect.center().y() else 0)


def describe(qlr_text):
    """('skupina'|'sloj', number of layers) – for icons and tooltips."""
    try:
        root = ET.fromstring(qlr_text)
    except ET.ParseError:
        return "sloj", 0
    tree = root.find("layer-tree-group")
    n_layers = len(root.findall(".//maplayer"))
    has_group = tree is not None and tree.find("layer-tree-group") is not None
    return ("skupina" if has_group or n_layers > 1 else "sloj"), n_layers


# ---------------------------------------------------------------------------
# Checks before sharing
# ---------------------------------------------------------------------------
def _strip_params(ds, names):
    """Remove key=value parameters from '&'-style or "key='value'"-style data sources."""
    changed = False
    for name in names:
        new = re.sub(rf"(^|&){name}=[^&]*", "", ds)                    # a=1&password=x&b=2
        new = re.sub(rf"(^|\s){name}=('([^'\\]|\\.)*'|\S*)", "", new)  # url='..' password='x'
        if new != ds:
            changed, ds = True, new
    return ds.strip("& ").replace("&&", "&"), changed


def _check_source(provider, ds, name, warnings, errors):
    """Return the cleaned data source string."""
    if re.search(r"authcfg=['\"]?\w+", ds):
        errors.append(f"»{name}«: uporablja shranjeno prijavo QGIS (authcfg) – drugi uporabniki je nimajo. "
                      "Povežite sloj brez shranjene prijave in poskusite znova.")
        return ds

    if provider in DB_PROVIDERS:
        uri = QgsDataSourceUri(ds)
        if uri.username() or uri.password():
            if uri.host() == config.get("cpa_host"):
                uri.setUsername(config.get("cpa_user"))
                uri.setPassword(config.get("cpa_password"))
                warnings.append(f"»{name}«: osebna prijava zamenjana z javnim računom CPA.")
            else:
                uri.setUsername("")
                uri.setPassword("")
                warnings.append(f"»{name}«: uporabniško ime in geslo odstranjena – uporabnik ju bo moral vnesti.")
            return uri.uri(False)
        return ds

    if provider in WEB_PROVIDERS or "url=" in ds:
        new, changed = _strip_params(ds, ("password", "username", "user"))
        if changed:
            warnings.append(f"»{name}«: uporabniško ime in geslo za spletno storitev odstranjena.")
        return new

    if provider == "memory":
        errors.append(f"»{name}«: začasni sloj – njegovi podatki se v QLR ne shranijo.")
        return ds

    if provider in FILE_PROVIDERS:
        path = ds.split("|")[0]
        if provider == "delimitedtext" and path.startswith("file:"):
            path = path[5:].split("?")[0].lstrip("/")
        if re.match(r"^(/vsi|https?:|ftp:)", path):
            return ds
        if path.startswith(("\\\\", "//")):
            warnings.append(f"»{name}«: datoteka na omrežni poti ({path}) – dosegljiva le v vašem omrežju.")
        elif re.match(r"^([A-Za-z]:[\\/]|/)", path):
            warnings.append(f"»{name}«: lokalna datoteka ({path}) – drugi uporabniki je ne bodo imeli.")
    return ds


def _image_attrs(root):
    """(element, attribute) pairs that may hold an image path in a symbol."""
    for el in root.iter():
        if el.tag == "Option" and el.get("type") == "QString" and el.get("value"):
            yield el, "value"
        elif el.tag == "prop" and el.get("v"):
            yield el, "v"


def check_qlr(qlr_text, embed_images=True):
    """Check (and clean) QLR text before it is shared.
    Returns (clean_qlr, warnings, errors). Errors mean it must not be saved."""
    warnings, errors = [], []
    try:
        root = ET.fromstring(qlr_text)
    except ET.ParseError as e:
        return qlr_text, warnings, [f"Neveljaven QLR: {e}"]

    sources = {}                                   # layer id -> cleaned source
    for ml in root.iter("maplayer"):
        provider = (ml.findtext("provider") or "").strip()
        ds_el = ml.find("datasource")
        name = ml.findtext("layername") or "?"
        if ds_el is not None and ds_el.text:
            ds_el.text = _check_source(provider, ds_el.text, name, warnings, errors)
            sources[ml.findtext("id")] = ds_el.text
    for lt in root.iter("layer-tree-layer"):      # the tree repeats the source
        if lt.get("id") in sources:
            lt.set("source", sources[lt.get("id")])

    embedded, missing = 0, set()
    for el, attr in _image_attrs(root):
        value = el.get(attr)
        if not value.lower().endswith(IMAGE_EXT) or value.startswith(("base64:", "http")):
            continue
        if not re.match(r"^([A-Za-z]:[\\/]|/|\\\\)", value):
            continue                               # relative: QGIS's own SVG library
        path = Path(value)
        if embed_images and path.is_file():
            el.set(attr, "base64:" + base64.b64encode(path.read_bytes()).decode("ascii"))
            embedded += 1
        elif not path.is_file():
            missing.add(value)
        else:
            warnings.append(f"Slika v slogu je lokalna datoteka ({value}) – drugi je ne bodo videli.")
    if embedded:
        warnings.append(f"V slog vdelanih lokalnih slik: {embedded}.")
    for value in sorted(missing):
        warnings.append(f"Slika v slogu ne obstaja ({value}).")

    clean = "<!DOCTYPE qgis-layer-definition>\n" + ET.tostring(root, encoding="unicode")
    return clean, warnings, errors
