"""Every external address AGIS uses, in one place.

Order in which a value is taken (first one that is set):
  1. dev override (QGIS settings agis/dev/<key>, see below)
  2. the user's own value (web service addresses and the path of the settings
     file, Nastavitve tab)
  3. the organisation settings file (``settings_file``, an .ini on a network
     share - the database server and login live there, not in this public code)
  4. DEFAULTS below

Nothing in this file needs to be edited for testing: any value can be overridden in the QGIS settings under
``agis/dev/<key>`` - use ``dev/agis_dev.py`` from the QGIS Python console
(``use_local()`` / ``use_production()`` / ``show()``). While an override is
active, the AGIS panel shows a "DEV" marker.

Every value can be written as plain text or base64:
    "cpa_user": "cpa",              plain text
    "cpa_user": "b64:Y3Bh",         base64 (prefix "b64:")
The same works for overrides. To get the base64 form of a text, run in the
QGIS Python console:  from agis import config; config.encode("text")
"""
import base64
import configparser
import os
import socket
import threading
from pathlib import Path

from qgis.core import QgsMessageLog, QgsSettings

DEV_GROUP = "agis/dev"
USER_GROUP = "agis/urls"
# Web service addresses a user may change in the Nastavitve tab (no DEV marker)
USER_KEYS = ("gurs_wfs_url", "geohub_research_url", "geohub_evrd_url")
B64_PREFIX = "b64:"
# The user's own path of the organisation settings file (Nastavitve tab, no DEV marker)
SETTINGS_KEY = "agis/settings_file"
SETTINGS_FILE_NAME = "agis_nastavitve.ini"


DEFAULTS = {
    # --- Organisation settings file -------------------------------------------
    # .ini on a share that only the organisation's computers can read. Holds the
    # database server, login and table names; see dev/agis_nastavitve.ini.
    # The default is the drive letter path used on CPA's office computers, so they
    # need no setup. It names no server or share on purpose (this code is public):
    # where V: is not connected (e.g. at home over VPN), the user enters the
    # network path (\\server\share\...) in Nastavitve -> Povezave.
    # If the file is not found, dev/agis_nastavitve.ini is used when present
    # (repo installs only), otherwise AGIS works without the CPA database.
    "settings_file": r"V:\01 CPA - PODATKOVNE ZBIRKE\03 GIS CPA\agis_nastavitve.ini",

    # --- CPA database (from the settings file) ------------------------------
    "cpa_host": "",
    "cpa_port": "5432",
    "cpa_database": "",
    "cpa_user": "",
    "cpa_password": "",

    # --- CPA tables / views -------------------------------------------------
    # Checked against the CPA_Analiza dump of 2026-09-25.
    # Layer catalogue (one QLR per row), created with dev/cpa_catalogue.sql.
    "cpa_catalogue_schema": "agis",
    "cpa_catalogue_table": "agis_viri",
    # List of work layers for "Naloži delovne sloje"
    "cpa_work_schema": "Delovno",
    "cpa_work_table": "Delovni sloji",
    # Local copy of the cadastre (Parcele tab) - materialized view in public,
    # readable by cpa (the source table "Podlage"."ZKN parcele_gurs" is not).
    "cpa_cadastre_schema": "public",
    "cpa_cadastre_table": "ZKN parcele",
    "cpa_cadastre_geom": "geom",
    "cpa_cadastre_key": "fid",
    "cpa_cadastre_ko": "sifko",
    "cpa_cadastre_parcela": "parcela",
    # Copy date: read from the table comment ("Datum zadnje posodobitve: YYYY-MM-DD")
    # unless a column name is given here.
    "cpa_cadastre_date": "",

    # eArheologija and eVRD: copies of the geohub layers (views over the
    # replicator). Column names as on geohub (case does not matter), any SRID.
    # Copy date from the view comment ("Datum zadnje posodobitve: YYYY-MM-DD").
    "cpa_research_schema": "public",
    "cpa_research_table": "mk_arheo_vrste_arh_raziskav",
    "cpa_evrd_schema": "public",
    "cpa_evrd_table": "mk_evrd",

    # --- Web services (users can change these in the Nastavitve tab) ---------
    "gurs_wfs_url": "https://ipi.eprostor.gov.si/wfs-si-gurs-kn/wfs",
    # eArheologija when the CPA copy is not reachable (MapServer or FeatureServer layer)
    "geohub_research_url": "https://geohub.gov.si/ags/rest/services/MK/MK_ARHEO/MapServer/3692",
    # eVRD when the CPA copy is not reachable
    "geohub_evrd_url": "https://geohub.gov.si/ags/rest/services/MK/MK_EVRD/MapServer/0",
    # Official layer catalogue (SQLite file published on GitHub)
    "official_catalogue_url": "https://raw.githubusercontent.com/matjash/AGIS/master/catalogue/agis_katalog.db",
}


def decode(value):
    """Plain text stays as it is; "b64:..." is decoded from base64."""
    value = "" if value is None else str(value)
    if value.startswith(B64_PREFIX):
        return base64.b64decode(value[len(B64_PREFIX):]).decode("utf-8")
    return value


def encode(text):
    """Base64 form of ``text`` with the prefix, ready to paste into DEFAULTS."""
    return B64_PREFIX + base64.b64encode(str(text).encode("utf-8")).decode("ascii")


def get(key):
    """Value for ``key``: dev override, else the user's own value (web services and the
    path of the settings file), else the organisation settings file, else the default."""
    if key not in DEFAULTS:
        raise KeyError(f"Unknown AGIS config key: {key}")
    s = QgsSettings()
    value = s.value(f"{DEV_GROUP}/{key}", None)
    if value in (None, "") and key in USER_KEYS:
        value = s.value(f"{USER_GROUP}/{key}", None)
    if value in (None, "") and key == "settings_file":
        value = s.value(SETTINGS_KEY, None)
    if value in (None, "") and key != "settings_file":
        value = org_settings().get(key)
    return decode(DEFAULTS[key] if value in (None, "") else value)


# ---------------------------------------------------------------------------
# Organisation settings file
# ---------------------------------------------------------------------------
DEV_SETTINGS_FILE = Path(__file__).parent / "dev" / "agis_nastavitve.ini"
SETTINGS_TIMEOUT = 2.0      # seconds; an unreachable share must not freeze QGIS

# section -> {ini key: config key}; "tabele" values are "schema.table"
INI_KEYS = {
    "baza": {"host": "cpa_host", "port": "cpa_port", "database": "cpa_database",
             "user": "cpa_user", "password": "cpa_password"},
    "tabele": {"katalog": ("cpa_catalogue_schema", "cpa_catalogue_table"),
               "delovni_sloji": ("cpa_work_schema", "cpa_work_table"),
               "parcele": ("cpa_cadastre_schema", "cpa_cadastre_table"),
               "earheologija": ("cpa_research_schema", "cpa_research_table"),
               "evrd": ("cpa_evrd_schema", "cpa_evrd_table")},
    "parcele": {"geometrija": "cpa_cadastre_geom", "kljuc": "cpa_cadastre_key", "ko": "cpa_cadastre_ko",
                "parcela": "cpa_cadastre_parcela", "datum": "cpa_cadastre_date"},
}

_org = None                 # {"values": {...}, "path": str|None, "status": str, "needs_login": bool}
_org_lock = threading.Lock()


def read_settings_file(path):
    """Config values from an organisation .ini (raises OSError / configparser.Error)."""
    ini = configparser.ConfigParser(interpolation=None)
    with open(path, encoding="utf-8-sig") as f:
        ini.read_file(f)
    values = {}
    for section, keys in INI_KEYS.items():
        if not ini.has_section(section):
            continue
        for ini_key, target in keys.items():
            raw = ini.get(section, ini_key, fallback="").strip()
            if not raw:
                continue
            if isinstance(target, tuple):
                schema, _, table = raw.partition(".")
                if not table:
                    schema, table = "public", schema
                values[target[0]], values[target[1]] = schema.strip().strip('"'), table.strip().strip('"')
            else:
                values[target] = raw
    return values


def _read_with_timeout(path):
    """(values, status, missing). A path on an unreachable share can block for many seconds, so it
    is read in a thread; after SETTINGS_TIMEOUT it counts as not reachable.
    missing=True: the system said plainly that there is no such file or folder (wrong path, or the
    file is not there yet) - a login to the share would not help."""
    result = {}

    def work():
        try:
            try:
                os.stat(path)
            except (FileNotFoundError, NotADirectoryError):
                result["status"] = "ni najdena"
                result["missing"] = True
                return
            except OSError:             # e.g. no credentials for the share (WinError 5, 1326)
                result["status"] = "ni najdena"
                return
            result["values"] = read_settings_file(path)
            result["status"] = "v redu"
        except (OSError, configparser.Error, UnicodeError) as e:
            result["status"] = f"napaka: {e}"

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(SETTINGS_TIMEOUT)
    if t.is_alive():
        return None, "ni najdena (ni odziva)", False
    return result.get("values"), result.get("status", "ni najdena"), result.get("missing", False)


def org_settings(refresh=False):
    """Values from the organisation settings file (read once per session; refresh=True reads again)."""
    global _org
    current = _org
    if current is None or refresh:
        current = _load_org()           # outside the lock: other threads keep the old values meanwhile
        with _org_lock:
            _org = current
    return current["values"]


def defer_org_settings():
    """Plugin start: don't wait for the settings file. Until it has been read in the background
    (org_settings(refresh=True), e.g. via cpa_available(refresh=True) in a task), AGIS works
    without the organisation database."""
    global _org
    with _org_lock:
        if _org is None:
            _org = {"values": {}, "path": None, "status": "berem …", "needs_login": False}


def org_settings_info():
    """(path used or None, status text) for the Nastavitve tab."""
    org_settings()
    return _org["path"], _org["status"]


def org_needs_login():
    """True if the settings file is on a server that answers (CPA network or VPN) but cannot be
    read - typically a Windows login without credentials for the share (home PC, other account).
    Not when the share can be read and the file is simply not at that path."""
    org_settings()
    return _org["needs_login"]


def settings_server(path=None):
    r"""Server name of a UNC path (\\server\share\... or //server/share/...), else None."""
    path = (get("settings_file") if path is None else path) or ""
    p = path.replace("/", "\\")
    if not p.startswith("\\\\"):
        return None
    server = p[2:].split("\\", 1)[0]
    return server or None


def settings_folder():
    """Folder of the settings file (opened in File Explorer to log in to the share)."""
    path = get("settings_file")
    if not path:
        return None
    import ntpath
    return ntpath.dirname(path) if settings_server(path) else str(Path(path).parent)


def server_answers(host, port=445, timeout=0.5):
    """Does the file server answer on the Windows file sharing port? Providers block this
    port, so a home network without VPN never answers."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def clean_settings_path(text):
    """Path of the settings file as typed or pasted by the user: quotes from "Copy as path"
    removed; a folder gets the file name added. "" stays "" (= use the default)."""
    path = (text or "").strip().strip('"\'').strip()
    if not path:
        return ""
    if not path.lower().endswith(".ini"):
        sep = "/" if "/" in path and "\\" not in path else "\\"
        path = path.rstrip("\\/") + sep + SETTINGS_FILE_NAME
    return path


def user_settings_file():
    """The user's own path of the settings file ("" = the default is used)."""
    return str(QgsSettings().value(SETTINGS_KEY, "") or "")


def set_settings_file(text):
    """Save the user's own path of the settings file ("" or the default = back to the default).
    Returns the cleaned path. Read it again with org_settings(refresh=True)."""
    path = clean_settings_path(text)
    s = QgsSettings()
    if not path or path == default("settings_file"):
        s.remove(SETTINGS_KEY)
    else:
        s.setValue(SETTINGS_KEY, path)
    return path


def _load_org():
    primary = get("settings_file")
    # the built-in default is simply absent on computers outside the organisation: no log entry
    quiet = primary == default("settings_file")
    notes = []
    needs_login = False
    for path in [p for p in (primary, str(DEV_SETTINGS_FILE)) if p]:
        if path == str(DEV_SETTINGS_FILE) and not DEV_SETTINGS_FILE.exists():
            continue
        values, status, missing = _read_with_timeout(path)
        if values is None and path == primary and not missing:
            server = settings_server(path)
            if server and server_answers(server):
                needs_login = True
                status = "ni dostopa – potrebna je prijava v omrežni disk"
        if values is not None:
            if notes:
                QgsMessageLog.logMessage("Nastavitve organizacije: " + "; ".join(notes) +
                                         f" – uporabljam {path}", "AGIS")
            return {"values": values, "path": path, "status": status, "needs_login": needs_login}
        notes.append(f"{path}: {status}")
    if notes and not quiet:
        QgsMessageLog.logMessage("Nastavitve organizacije: " + "; ".join(notes), "AGIS")
    return {"values": {}, "path": None, "needs_login": needs_login,
            "status": notes[0].split(": ", 1)[1] if notes else "ni nastavljena"}


def default(key):
    return decode(DEFAULTS[key])


def set_user(key, value):
    """Save the user's own value for a web service address ("" or the default = back to default)."""
    if key not in USER_KEYS:
        raise KeyError(f"{key} cannot be set by the user")
    value = (value or "").strip()
    s = QgsSettings()
    if not value or value == default(key):
        s.remove(f"{USER_GROUP}/{key}")
    else:
        s.setValue(f"{USER_GROUP}/{key}", value)


def overrides():
    """Dict of all active dev overrides, decoded (empty in normal use)."""
    s = QgsSettings()
    s.beginGroup(DEV_GROUP)
    try:
        return {k: decode(s.value(k)) for k in s.childKeys()
                if k in DEFAULTS and s.value(k) not in (None, "")}
    finally:
        s.endGroup()


def is_dev():
    return bool(overrides())


def dev_label():
    """Short text for the DEV marker in the panel, e.g. 'DEV: localhost'."""
    o = overrides()
    if not o:
        return ""
    return f"DEV: {o['cpa_host']}" if "cpa_host" in o else "DEV"
