"""Portable snapshots and transactional restore of the app's measurement tables."""

import sqlite3
from contextlib import closing
from pathlib import Path

MAX_BACKUP_SIZE = 256 * 1024 * 1024
TABLES = {
    "traffic": ("hour", "kind", "source", "label", "rx", "tx"),
    "app_destinations": ("app", "day", "ip", "protocol", "port", "domain", "evidence", "rx", "tx"),
    "ipinfo_cache": ("ip", "asn", "as_name", "as_domain"),
}


def snapshot(connection, target):
    with closing(sqlite3.connect(target)) as copy:
        connection.backup(copy)
        copy.execute("PRAGMA journal_mode = DELETE")


def restore(connection, uploaded, rescue, previous):
    """Import only known measurement tables. Roll back on any invalid row or SQL error."""
    connection.execute("PRAGMA trusted_schema = OFF")
    connection.execute("ATTACH DATABASE ? AS incoming", (Path(uploaded).as_uri() + "?mode=ro",))
    try:
        if connection.execute("PRAGMA incoming.quick_check").fetchall()[0][0] != "ok":
            raise ValueError("Het SQLite-bestand is beschadigd.")
        tables = {}
        for table, columns in TABLES.items():
            metadata = connection.execute(
                "SELECT type FROM incoming.pragma_table_list WHERE schema = 'incoming' AND name = ?", (table,)
            ).fetchone()
            if metadata is None and table != "traffic":
                continue  # Older backups can omit newer tables.
            schema = connection.execute(f"PRAGMA incoming.table_xinfo({table})").fetchall()
            if not metadata or metadata[0] != "table" or tuple(row[1] for row in schema) != columns or any(row[6] for row in schema):
                raise ValueError("Dit bestand bevat geen ondersteunde HA-Bandwidth-database.")
            expected = " AND ".join(
                f"typeof({column}) = '{'integer' if column in ('rx', 'tx', 'port', 'protocol') else 'text'}'"
                for column in columns
            )
            if table == "ipinfo_cache":
                expected += " AND length(ip) BETWEEN 1 AND 45 AND length(asn) <= 250"
                expected += " AND length(as_name) <= 250 AND length(as_domain) <= 250"
                valid = connection.execute(
                    f"SELECT COALESCE(MIN({expected}), 1), 0 FROM incoming.ipinfo_cache"
                ).fetchone()
            else:
                valid = connection.execute(f"""
                    SELECT COALESCE(MIN(({expected}) AND rx >= 0 AND tx >= 0), 1),
                           COALESCE(SUM(CAST(rx AS REAL) + tx), 0)
                    FROM incoming.{table}
                """).fetchone()
            if not valid[0] or not 0 <= valid[1] <= 9e18:
                raise ValueError("De back-up bevat ongeldige meetgegevens.")
            tables[table] = ", ".join(columns)

        # SQLite readers can keep their snapshot while the write lock prevents new measurements.
        connection.execute("BEGIN IMMEDIATE")
        try:
            with closing(sqlite3.connect(rescue)) as before:
                with closing(sqlite3.connect(connection.execute("PRAGMA database_list").fetchone()[2])) as current:
                    current.backup(before)
                before.execute("PRAGMA journal_mode = DELETE")
            for table in TABLES:
                if table == "ipinfo_cache" and table not in tables:
                    continue
                connection.execute(f"DELETE FROM main.{table}")
                if table in tables:
                    columns = tables[table]
                    connection.execute(f"INSERT INTO main.{table} ({columns}) SELECT {columns} FROM incoming.{table}")
            rescue.replace(previous)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    finally:
        connection.execute("DETACH DATABASE incoming")

