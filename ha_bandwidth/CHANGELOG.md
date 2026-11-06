# Changelog

## 0.2.0

- Klik op een appnaam om de bestemmingen voor de gekozen dag, week, maand of het jaar te bekijken.
- Per bestemming zie je het IP-adres, het protocol, de poort en de hoeveelheid download en upload. Waar beschikbaar wordt de domeinnaam getoond met de herkomst TLS of DNS.
- De bestemmingsmeting werkt voor apps op een Docker-bridge. Verkeer van apps op het gedeelde hostnetwerk blijft opgenomen in de servermeting.
- Bestaande verkeerstotalen blijven bewaard. De bestemmingshistorie begint na deze update.

## 0.1.0

- Eerste versie met upload- en downloadgrafieken voor serververkeer, apps en IP-adressen.
- Dag-, week-, maand- en jaaroverzichten met lokale opslag in SQLite.
