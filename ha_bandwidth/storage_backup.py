"""Portable snapshots and transactional restore of the app's measurement tables."""

import sqlite3
from contextlib import closing
from pathlib import Path

MAX_BACKUP_SIZE = 256 * 1024 * 1024
TABLES = {
    "traffic": ("hour", "kind", "source", "label", "rx", "tx"),
    "app_destinations": ("app", "day", "ip", "protocol", "port", "domain", "evidence", "rx", "tx"),
    "ipinfo_cache": ("ip", "asn", "as_name", "as_domain"),
    "traffic_alerts": ("timestamp", "kind", "source", "label", "bps", "baseline_bps", "reason", "interval_start", "leaders"),
}
INTEGER_COLUMNS = {"rx", "tx", "port", "protocol", "bps", "baseline_bps"}
NULLABLE_COLUMNS = {"interval_start"}
# Tabellen die een oudere back-up mag missen. Dan blijft wat er nu in staat ongemoeid.
OPTIONAL_TABLES = {"ipinfo_cache", "traffic_alerts"}


def identifier(name):
    """Geef een tabel- of kolomnaam terug als die uit het vaste schema komt, anders een fout.

    SQLite laat namen niet als parameter toe. Elke naam die in SQL-tekst belandt gaat hier langs,
    zodat een bestand dat je uploadt nooit de vorm van een opdracht kan bepalen.
    """
    if name in TABLES or any(name in columns for columns in TABLES.values()):
        return name
    raise ValueError(f"Onbekende naam in het schema: {name!r}")


def column_check(column):
    column = identifier(column)
    kind = "integer" if column in INTEGER_COLUMNS else "text"
    if column in NULLABLE_COLUMNS:
        return f"typeof({column}) IN ('{kind}', 'null')"
    return f"typeof({column}) = '{kind}'"


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
            # Namen komen uit het vaste schema (identifier()); SQLite staat namen niet als parameter toe.
            # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query, python.lang.security.audit.formatted-sql-query.formatted-sql-query
            schema = connection.execute(f"PRAGMA incoming.table_xinfo({identifier(table)})").fetchall()
            if not metadata or metadata[0] != "table" or tuple(row[1] for row in schema) != columns or any(row[6] for row in schema):
                raise ValueError("Dit bestand bevat geen ondersteunde HA-Bandwidth-database.")
            expected = " AND ".join(column_check(column) for column in columns)
            if table == "traffic_alerts":
                expected += " AND bps >= 0 AND baseline_bps >= 0 AND length(kind) <= 32 AND length(source) <= 250"
                expected += " AND length(label) <= 250 AND length(reason) <= 1000 AND length(leaders) <= 100000"
                # Namen komen uit het vaste schema (identifier()); SQLite staat namen niet als parameter toe.
                # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query, python.lang.security.audit.formatted-sql-query.formatted-sql-query
                valid = connection.execute(
                    f"SELECT COALESCE(MIN({expected}), 1), 0 FROM incoming.traffic_alerts"
                ).fetchone()
            elif table == "ipinfo_cache":
                expected += " AND length(ip) BETWEEN 1 AND 45 AND length(asn) <= 250"
                expected += " AND length(as_name) <= 250 AND length(as_domain) <= 250"
                # Namen komen uit het vaste schema (identifier()); SQLite staat namen niet als parameter toe.
                # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query, python.lang.security.audit.formatted-sql-query.formatted-sql-query
                valid = connection.execute(
                    f"SELECT COALESCE(MIN({expected}), 1), 0 FROM incoming.ipinfo_cache"
                ).fetchone()
            else:
                # Namen komen uit het vaste schema (identifier()); SQLite staat namen niet als parameter toe.
                # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query, python.lang.security.audit.formatted-sql-query.formatted-sql-query
                valid = connection.execute(f"""
                    SELECT COALESCE(MIN(({expected}) AND rx >= 0 AND tx >= 0), 1),
                           COALESCE(SUM(CAST(rx AS REAL) + tx), 0)
                    FROM incoming.{identifier(table)}
                """).fetchone()
            if not valid[0] or not 0 <= valid[1] <= 9e18:
                raise ValueError("De back-up bevat ongeldige meetgegevens.")
            tables[table] = ", ".join(identifier(column) for column in columns)

        # SQLite readers can keep their snapshot while the write lock prevents new measurements.
        connection.execute("BEGIN IMMEDIATE")
        try:
            with closing(sqlite3.connect(rescue)) as before:
                with closing(sqlite3.connect(connection.execute("PRAGMA database_list").fetchone()[2])) as current:
                    current.backup(before)
                before.execute("PRAGMA journal_mode = DELETE")
            for table in TABLES:
                if table in OPTIONAL_TABLES and table not in tables:
                    continue
                # Namen komen uit het vaste schema (identifier()); SQLite staat namen niet als parameter toe.
                # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query, python.lang.security.audit.formatted-sql-query.formatted-sql-query
                connection.execute(f"DELETE FROM main.{identifier(table)}")
                if table in tables:
                    columns = tables[table]
                    # Namen komen uit het vaste schema (identifier()); SQLite staat namen niet als parameter toe.
                    # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query, python.lang.security.audit.formatted-sql-query.formatted-sql-query
                    connection.execute(f"INSERT INTO main.{identifier(table)} ({columns}) SELECT {columns} FROM incoming.{identifier(table)}")
            rescue.replace(previous)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    finally:
        connection.execute("DETACH DATABASE incoming")

