"""Every external address AGIS uses, in one place.

The defaults below are the production values. Nothing in this file needs to be
edited for testing: any value can be overridden in the QGIS settings under
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

from qgis.core import QgsSettings

DEV_GROUP = "agis/dev"
USER_GROUP = "agis/urls"
# Web service addresses a user may change in the Nastavitve tab (no DEV marker)
USER_KEYS = ("gurs_wfs_url", "geohub_research_url", "geohub_evrd_url")
B64_PREFIX = "b64:"


DEFAULTS = {
    # --- CPA database -------------------------------------------------------
    # "cpa" is a public, read-only account, so it is fine that it can be read
    # from this file. base64 only keeps it out of plain sight; it is not
    # meant as protection.
    "cpa_host": "b64:bWFqYWRi",
    "cpa_port": "b64:NTQzMg==",
    "cpa_database": "b64:Q1BBX0FuYWxpemE=",
    "cpa_user": "b64:Y3Bh",
    "cpa_password": "b64:Y3Bh",

    # --- CPA tables / views -------------------------------------------------
    # Checked against the CPA_Analiza dump of 2026-09-25.
    # Layer catalogue (one QLR per row). TODO (plan C9): table not yet in CPA_Analiza.
    "cpa_catalogue_schema": "public",
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
    "official_catalogue_url": "https://raw.githubusercontent.com/matjash/AGIS/master/catalogue/agis_viri.db",
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
    """Value for ``key``: dev override, else the user's own value (web services only), else the default."""
    if key not in DEFAULTS:
        raise KeyError(f"Unknown AGIS config key: {key}")
    s = QgsSettings()
    value = s.value(f"{DEV_GROUP}/{key}", None)
    if value in (None, "") and key in USER_KEYS:
        value = s.value(f"{USER_GROUP}/{key}", None)
    return decode(DEFAULTS[key] if value in (None, "") else value)


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
