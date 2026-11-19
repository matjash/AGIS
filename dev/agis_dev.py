"""Switch AGIS between the real CPA database and a local copy of it.

Run in the QGIS Python console (Plugins > Python Console):

    from agis.dev import agis_dev as d
    d.use_local()          # local copy on localhost:5433/CPA_Analiza
    d.show()               # what is used now
    d.use_production()     # back to the real CPA database

use_local() accepts any setting from config.DEFAULTS as a keyword, e.g.

    d.use_local(cpa_port="5432", official_catalogue_url="file:///C:/test/agis_viri.db")

Values can be plain text or base64 with the "b64:" prefix, as in config.py:

    d.use_local(cpa_password="b64:Y3Bh")

After switching, press the refresh button (↺) in the AGIS panel or restart QGIS.
Nothing here is shipped to users (the dev/ folder is left out of the release zip).
"""
from qgis.core import QgsSettings

from .. import config

LOCAL = {
    "cpa_host": "localhost",
    "cpa_port": "5433",
    "cpa_database": "CPA_Analiza",
    "cpa_user": "cpa",
    "cpa_password": "cpa",
}


def use_local(**changes):
    """Point AGIS at a local copy of the CPA database. Keyword arguments override single settings."""
    values = dict(LOCAL, **changes)
    unknown = set(values) - set(config.DEFAULTS)
    if unknown:
        raise KeyError(f"Unknown settings: {', '.join(sorted(unknown))}")
    s = QgsSettings()
    for key, value in values.items():
        s.setValue(f"{config.DEV_GROUP}/{key}", str(value))
    _recheck()
    show()


def set_value(key, value):
    """Override one setting, e.g. set_value('cpa_cadastre_table', 'parcele_test')."""
    if key not in config.DEFAULTS:
        raise KeyError(f"Unknown setting: {key}")
    QgsSettings().setValue(f"{config.DEV_GROUP}/{key}", str(value))
    _recheck()
    show()


def use_production():
    """Remove all overrides - AGIS uses the real CPA database again."""
    QgsSettings().remove(config.DEV_GROUP)
    _recheck()
    show()


def show():
    """Print every setting and mark the overridden ones."""
    active = config.overrides()
    print("AGIS:", "DEV mode" if active else "production")
    for key in config.DEFAULTS:
        value = config.get(key)
        if "password" in key:
            value = "***"
        print(f"  {'*' if key in active else ' '} {key:28} {value}")
    if active:
        print("  (* = overridden; use_production() removes all overrides)")


def _recheck():
    try:
        from ..externals import cpa_available
        print("CPA database reachable:", cpa_available(refresh=True))
    except Exception as e:  # plugin not loaded yet, etc.
        print("Could not check CPA database:", e)
