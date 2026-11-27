"""Versiebeheer voor de database.

De versie staat in `PRAGMA user_version`. Elke migratie is een lijst SQL-opdrachten en wordt in één
transactie uitgevoerd samen met het ophogen van de versie: of alles lukt, of er verandert niets.

Voeg een wijziging toe als nieuwe versie onderaan `MIGRATIONS`. Pas een bestaande versie nooit aan,
want die is al uitgevoerd op bestaande installaties.
"""

import logging

# Versie 1 is het schema van vóór het versiebeheer. Alles is IF NOT EXISTS, zodat een bestaande
# database zonder versienummer er veilig als versie 1 uit komt.
MIGRATIONS = {
    1: [
        """CREATE TABLE IF NOT EXISTS traffic (
               hour TEXT, kind TEXT, source TEXT, label TEXT,
               rx INTEGER NOT NULL, tx INTEGER NOT NULL,
               PRIMARY KEY (hour, kind, source)
           ) WITHOUT ROWID""",
        """CREATE TABLE IF NOT EXISTS app_destinations (
               app TEXT, day TEXT, ip TEXT, protocol INTEGER, port INTEGER, domain TEXT,
               evidence TEXT, rx INTEGER NOT NULL, tx INTEGER NOT NULL,
               PRIMARY KEY (app, day, ip, protocol, port, domain, evidence)
           ) WITHOUT ROWID""",
        """CREATE TABLE IF NOT EXISTS ipinfo_cache (
               ip TEXT PRIMARY KEY, asn TEXT NOT NULL, as_name TEXT NOT NULL, as_domain TEXT NOT NULL
           ) WITHOUT ROWID""",
        """CREATE TABLE IF NOT EXISTS traffic_alerts (
               timestamp TEXT NOT NULL, kind TEXT NOT NULL, source TEXT NOT NULL,
               label TEXT NOT NULL DEFAULT '', bps INTEGER NOT NULL, baseline_bps INTEGER NOT NULL,
               reason TEXT NOT NULL DEFAULT '', interval_start TEXT, leaders TEXT NOT NULL DEFAULT '{}',
               PRIMARY KEY (timestamp, kind, source)
           ) WITHOUT ROWID""",
        "CREATE INDEX IF NOT EXISTS app_destinations_day ON app_destinations(day)",
        "CREATE INDEX IF NOT EXISTS traffic_kind_hour ON traffic(kind, hour)",
        "CREATE INDEX IF NOT EXISTS traffic_kind_source_hour ON traffic(kind, source, hour)",
    ],
}


def latest(migrations=None):
    return max(migrations or MIGRATIONS)


def current_version(db):
    return db.execute("PRAGMA user_version").fetchone()[0]


def migrate(db, migrations=None):
    """Breng de database op de nieuwste versie. Geeft de versie na afloop terug.

    Een database die nieuwer is dan deze app wordt niet aangeraakt: een oudere app kan een
    nieuwer schema niet veilig lezen of aanpassen.
    """
    migrations = MIGRATIONS if migrations is None else migrations
    newest = latest(migrations)
    version = current_version(db)
    if version > newest:
        raise RuntimeError(
            f"De database heeft versie {version}, maar deze versie van HA-Bandwidth kent alleen versie {newest}. "
            "Werk de app bij of zet een back-up van een eerdere versie terug.")
    for target in sorted(number for number in migrations if number > version):
        db.execute("BEGIN IMMEDIATE")
        try:
            for statement in migrations[target]:
                db.execute(statement)
            db.execute(f"PRAGMA user_version = {int(target)}")
        except BaseException:
            db.rollback()
            raise
        db.commit()
        logging.info("Database bijgewerkt naar versie %s", target)
    return current_version(db)
