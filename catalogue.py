"""Layer source catalogues: CPA (PostgreSQL), official (SQLite from GitHub), own (SQLite).

Every entry is one row with the same columns in all catalogues; the layer or
group itself is stored as QLR text in the ``qlr`` column.
"""
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from qgis.PyQt.QtCore import QUrl
from qgis.core import Qgis, QgsProviderConnectionException

from . import config
from .externals import (cpa_available, cpa_connection, http_get, log, pg_ident, pg_literal,
                        pn_path, profile_path, sql_value)

FIELDS = ("id", "naziv", "opis", "izvor", "vidnost", "kategorija", "oznake", "nadomestni_id", "vrstni_red", "omogocen",
          "qlr", "qlr_prejsnji", "posodobljeno")
EDITABLE = ("naziv", "opis", "izvor", "vidnost", "kategorija", "oznake", "nadomestni_id", "vrstni_red")
# columns added after the first version: older files / tables may not have them yet
NEWER_COLUMNS = ("oznake", "nadomestni_id")

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS viri (
    id            TEXT PRIMARY KEY,
    naziv         TEXT NOT NULL,
    opis          TEXT,
    izvor         TEXT,
    vidnost       TEXT NOT NULL DEFAULT 'javno',
    kategorija    TEXT,
    oznake        TEXT,
    nadomestni_id TEXT,
    vrstni_red    INTEGER DEFAULT 0,
    omogocen      INTEGER NOT NULL DEFAULT 1,
    qlr           TEXT NOT NULL,
    qlr_prejsnji  TEXT,
    posodobljeno  TEXT
)"""

BUNDLED_OFFICIAL = pn_path("catalogue") / "agis_katalog.db"


def new_entry(**values):
    entry = {f: None for f in FIELDS}
    entry.update(id=str(uuid.uuid4()), vidnost="javno", vrstni_red=0, omogocen=True)
    entry.update(values)
    return entry


def normalize_tags(text):
    """'lidar relief, DMR' -> 'lidar, relief, DMR' (comma or space separated, no duplicates)."""
    import re
    seen, out = set(), []
    for tag in re.split(r"[,;\s]+", text or ""):
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            out.append(tag)
    return ", ".join(out) or None


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class CatalogueError(Exception):
    pass


# ---------------------------------------------------------------------------
class SqliteCatalogue:
    """Official (read-only) or own (writable) catalogue in a SQLite file."""

    def __init__(self, key, title, path, writable):
        self.key, self.title, self.writable = key, title, writable
        self.path = Path(path)
        self.needs_login = False
        if writable:
            self._connect().close()          # creates the file and table

    def _connect(self):
        con = sqlite3.connect(str(self.path))
        if self.writable:
            con.execute(SQLITE_SCHEMA)
            have = {r[1] for r in con.execute("PRAGMA table_info(viri)")}
            for col in NEWER_COLUMNS:
                if col not in have:
                    con.execute(f"ALTER TABLE viri ADD COLUMN {col} TEXT")
            con.commit()
        return con

    def available(self):
        return self.path.exists()

    def entries(self):
        if not self.path.exists():
            return []
        con = self._connect()
        try:
            have = {r[1] for r in con.execute("PRAGMA table_info(viri)")}
            cols = [f if f in have else f"NULL AS {f}" for f in FIELDS]
            rows = con.execute(f"SELECT {', '.join(cols)} FROM viri ORDER BY vrstni_red, naziv").fetchall()
        except sqlite3.Error as e:
            log(f"{self.title}: {e}", Qgis.MessageLevel.Warning)
            return []
        finally:
            con.close()
        result = []
        for row in rows:
            entry = dict(zip(FIELDS, row))
            entry["omogocen"] = bool(entry["omogocen"])
            entry["ima_prejsnji"] = bool(entry["qlr_prejsnji"])
            result.append(entry)
        return result

    def _write(self, sql, params=()):
        if not self.writable:
            raise CatalogueError(f"{self.title} je samo za branje.")
        con = self._connect()
        try:
            with con:
                cur = con.execute(sql, params)
                return cur.rowcount
        finally:
            con.close()

    def add(self, entry):
        values = [entry.get(f) for f in FIELDS]
        values[FIELDS.index("posodobljeno")] = _now()
        values[FIELDS.index("omogocen")] = 1 if entry.get("omogocen", True) else 0
        self._write(f"INSERT INTO viri ({', '.join(FIELDS)}) VALUES ({', '.join('?' * len(FIELDS))})", values)

    def update(self, entry_id, **fields):
        fields = {k: v for k, v in fields.items() if k in EDITABLE}
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            self._write(f"UPDATE viri SET {sets}, posodobljeno = ? WHERE id = ?",
                        list(fields.values()) + [_now(), entry_id])

    def replace_qlr(self, entry_id, qlr):
        self._write("UPDATE viri SET qlr_prejsnji = qlr, qlr = ?, posodobljeno = ? WHERE id = ?",
                    (qlr, _now(), entry_id))

    def undo(self, entry_id):
        n = self._write("UPDATE viri SET qlr = qlr_prejsnji, qlr_prejsnji = qlr, posodobljeno = ? "
                        "WHERE id = ? AND qlr_prejsnji IS NOT NULL", (_now(), entry_id))
        if not n:
            raise CatalogueError("Ni prejšnje različice.")

    def set_enabled(self, entry_id, enabled):
        self._write("UPDATE viri SET omogocen = ?, posodobljeno = ? WHERE id = ?",
                    (1 if enabled else 0, _now(), entry_id))

    def delete(self, entry_id):
        self._write("DELETE FROM viri WHERE id = ?", (entry_id,))


# ---------------------------------------------------------------------------
class PostgresCatalogue:
    """CPA catalogue. Read with the shared cpa account, write with the curator's own login."""

    def __init__(self):
        self.key, self.title = "cpa", "CPA"
        self.writable = True
        self.needs_login = True
        self._login = None          # (user, password) for this QGIS session only
        self.can_delete = False

    @property
    def table(self):
        return pg_ident(config.get("cpa_catalogue_schema"), config.get("cpa_catalogue_table"))

    def available(self):
        return cpa_available()

    def entries(self):
        if not cpa_available():
            return []
        try:
            conn = cpa_connection()
            self._missing = {c for c in NEWER_COLUMNS if not self._column_exists(conn, c)}
            newer = ", ".join(f"{c}::text" if c not in self._missing else "NULL" for c in NEWER_COLUMNS)
            sql = (f"SELECT id::text, naziv, opis, izvor, vidnost, kategorija, {newer}, vrstni_red, omogocen, qlr, "
                   f"qlr_prejsnji IS NOT NULL, posodobljeno::text FROM {self.table} ORDER BY vrstni_red, naziv")
            rows = conn.executeSql(sql)
        except QgsProviderConnectionException as e:
            log(f"Katalog CPA ni dosegljiv: {e}", Qgis.MessageLevel.Warning)
            return []
        result = []
        for row in rows:
            row = [sql_value(v) for v in row]
            entry = dict(zip(("id", "naziv", "opis", "izvor", "vidnost", "kategorija", *NEWER_COLUMNS, "vrstni_red",
                              "omogocen", "qlr", "ima_prejsnji", "posodobljeno"), row))
            entry["qlr_prejsnji"] = None
            result.append(entry)
        return result

    def _column_exists(self, conn, column):
        rows = conn.executeSql(
            "SELECT count(*) FROM pg_attribute WHERE attrelid = "
            f"{pg_literal(self.table)}::regclass AND attname = {pg_literal(column)} AND NOT attisdropped")
        return bool(rows and int(sql_value(rows[0][0])))

    def _writable_fields(self, fields):
        """Leave out columns the CPA table does not have yet (run dev/cpa_catalogue.sql again to add them)."""
        missing = getattr(self, "_missing", set())
        return [f for f in fields if f not in missing]

    # --- login -------------------------------------------------------------
    def logged_in(self):
        return self._login is not None

    def login(self, user, password):
        """Check the login and the right to write; remember it for this session."""
        try:
            conn = cpa_connection(user, password)
            table = pg_literal(self.table)
            rows = conn.executeSql(f"SELECT has_table_privilege(current_user, {table}, 'INSERT,UPDATE'), "
                                   f"has_table_privilege(current_user, {table}, 'DELETE')")
        except QgsProviderConnectionException as e:
            raise CatalogueError(f"Prijava ni uspela: {e}")
        if not (rows and sql_value(rows[0][0])):
            raise CatalogueError("Ta prijava nima pravic za urejanje kataloga CPA.")
        self._login = (user, password)
        self.can_delete = bool(sql_value(rows[0][1]))

    @property
    def user(self):
        return self._login[0] if self._login else None

    def logout(self):
        self._login = None
        self.can_delete = False

    def _execute(self, sql):
        if not self._login:
            raise CatalogueError("Za urejanje kataloga CPA se je treba prijaviti.")
        try:
            return cpa_connection(*self._login).executeSql(sql)
        except QgsProviderConnectionException as e:
            raise CatalogueError(str(e))

    def _id(self, entry_id):
        return f"{pg_literal(str(uuid.UUID(str(entry_id))))}::uuid"

    # --- writing -----------------------------------------------------------
    def add(self, entry):
        cols = self._writable_fields([f for f in FIELDS if f not in ("posodobljeno", "qlr_prejsnji")])
        values = []
        for f in cols:
            v = entry.get(f)
            values.append(f"{pg_literal(str(v))}::uuid" if f == "id" else pg_literal(v))
        self._execute(f"INSERT INTO {self.table} ({', '.join(cols)}) VALUES ({', '.join(values)})")

    def update(self, entry_id, **fields):
        allowed = self._writable_fields(EDITABLE)
        fields = {k: v for k, v in fields.items() if k in allowed}
        if fields:
            sets = ", ".join(f"{k} = {pg_literal(v)}" for k, v in fields.items())
            self._execute(f"UPDATE {self.table} SET {sets}, posodobljeno = now() WHERE id = {self._id(entry_id)}")

    def replace_qlr(self, entry_id, qlr):
        self._execute(f"UPDATE {self.table} SET qlr_prejsnji = qlr, qlr = {pg_literal(qlr)}, "
                      f"posodobljeno = now() WHERE id = {self._id(entry_id)}")

    def undo(self, entry_id):
        self._execute(f"UPDATE {self.table} SET qlr = qlr_prejsnji, qlr_prejsnji = qlr, posodobljeno = now() "
                      f"WHERE id = {self._id(entry_id)} AND qlr_prejsnji IS NOT NULL")

    def set_enabled(self, entry_id, enabled):
        self._execute(f"UPDATE {self.table} SET omogocen = {pg_literal(bool(enabled))}, posodobljeno = now() "
                      f"WHERE id = {self._id(entry_id)}")

    def delete(self, entry_id):
        if not self.can_delete:
            raise CatalogueError("Ta prijava nima pravice brisati iz kataloga CPA – vir lahko skrijete za vse.")
        self._execute(f"DELETE FROM {self.table} WHERE id = {self._id(entry_id)}")


# ---------------------------------------------------------------------------
# Official catalogue: download, cache, fallback to the bundled copy
# ---------------------------------------------------------------------------
def official_cache_path():
    """Downloaded copy of Katalog AGIS in the QGIS profile (agis_katalog.db).
    A copy under the old name (uradni_katalog.db, before 1.9.1) is renamed once."""
    path = profile_path("agis_katalog.db")
    old = profile_path("uradni_katalog.db")
    if old.exists():
        try:
            if path.exists():
                old.unlink()
            else:
                old.replace(path)
        except OSError:
            pass
    return path


def _last_change(path):
    """Newest 'posodobljeno' in a catalogue file ('' if none or unreadable)."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return con.execute("SELECT coalesce(max(posodobljeno), '') FROM viri").fetchone()[0] or ""
        finally:
            con.close()
    except sqlite3.Error:
        return ""


def official_path():
    """The downloaded copy, unless the copy bundled with the plugin is newer
    (e.g. a plugin update that comes before the file on GitHub is updated)."""
    cache = official_cache_path()
    if not cache.exists():
        return BUNDLED_OFFICIAL
    if BUNDLED_OFFICIAL.exists() and _last_change(BUNDLED_OFFICIAL) > _last_change(cache):
        return BUNDLED_OFFICIAL
    return cache


def _is_catalogue(path):
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            con.execute("SELECT id, naziv, qlr FROM viri LIMIT 1").fetchall()
            return True
        finally:
            con.close()
    except sqlite3.Error:
        return False


def download_official(task=None):
    """Download the official catalogue into the profile cache. Returns the path.
    Raises IOError; the existing cache is kept if anything goes wrong."""
    url = config.get("official_catalogue_url")
    cache = official_cache_path()
    tmp = cache.with_suffix(".download")
    if url.startswith("file:"):
        shutil.copyfile(QUrl(url).toLocalFile(), tmp)
    else:
        tmp.write_bytes(http_get(url, timeout_ms=30000))
    if not _is_catalogue(tmp):
        tmp.unlink(missing_ok=True)
        raise IOError("Prenesena datoteka ni katalog AGIS.")
    tmp.replace(cache)
    return str(cache)


def export_catalogue(entries, path):
    """Write entries to a new SQLite catalogue file (for publishing the official list)."""
    path = Path(path)
    if path.exists():
        path.unlink()
    con = sqlite3.connect(str(path))
    try:
        with con:
            con.execute(SQLITE_SCHEMA)
            from .qlr_tools import without_cpa_login
            for e in entries:
                values = [e.get(f) for f in FIELDS]
                values[FIELDS.index("qlr")] = without_cpa_login(e.get("qlr") or "")
                values[FIELDS.index("qlr_prejsnji")] = None
                values[FIELDS.index("omogocen")] = 1 if e.get("omogocen", True) else 0
                values[FIELDS.index("posodobljeno")] = e.get("posodobljeno") or _now()
                con.execute(f"INSERT INTO viri ({', '.join(FIELDS)}) VALUES ({', '.join('?' * len(FIELDS))})",
                            values)
    finally:
        con.close()


# ---------------------------------------------------------------------------
class Catalogues:
    """All catalogues in fixed order: CPA -> official -> own."""

    def __init__(self):
        self.cpa = PostgresCatalogue()
        self.own = SqliteCatalogue("moji", "Moji viri", profile_path("moji_viri.db"), writable=True)
        self.official = SqliteCatalogue("uradni", "Katalog AGIS", official_path(), writable=False)

    def all(self, official_enabled=True):
        result = [self.cpa]
        if official_enabled:
            self.official.path = official_path()
            result.append(self.official)
        result.append(self.own)
        return result

    def by_key(self, key):
        return {"cpa": self.cpa, "uradni": self.official, "moji": self.own}[key]

    def entries(self, official_enabled=True, include_hidden=False):
        """Merged list; an id that appears in several catalogues is shown once (first wins).
        include_hidden: True, False or the keys of the catalogues whose hidden entries are included."""
        seen, result = set(), []
        for cat in self.all(official_enabled):
            with_hidden = include_hidden if isinstance(include_hidden, bool) else cat.key in include_hidden
            for e in cat.entries():
                if e["id"] in seen:
                    continue
                if not e["omogocen"] and not with_hidden:
                    continue
                seen.add(e["id"])
                e["katalog"] = cat.key
                result.append(e)
        return result
