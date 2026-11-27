"""CSV-export van de getoonde periode."""

import csv
import io

CSV_COLUMNS = ("bucket", "kind", "source", "label", "download_bytes", "upload_bytes", "total_bytes")


def csv_safe(value):
    """Voorkom dat een spreadsheet een apparaatnaam als formule uitvoert (CSV-injectie)."""
    value = str(value or "")
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def csv_text(rows):
    """Zet de gegroepeerde rijen om in CSV-tekst, met BOM zodat Excel de UTF-8-tekens goed leest."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow([row["bucket"], row["kind"], csv_safe(row["source"]), csv_safe(row["label"]),
                         row["rx"], row["tx"], row["rx"] + row["tx"]])
    return "\ufeff" + out.getvalue()
