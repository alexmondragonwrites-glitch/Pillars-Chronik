# CK3 – Recherchebasierte Verbesserungen der Wächterfeder

Stand: 11. August 2026

## Ausgangspunkt

Der erste reale tiefe CK3-Snapshot mit Rakaly zeigte bereits zuverlässig Spieler, Familie, Titel, direkte Vasallen und laufende Kriege. Gleichzeitig wurden drei Schwächen sichtbar:

1. Event-/Memory-Manager wurden teilweise nur als generische Wrapper wie `database` erkannt.
2. CK3-interne UI-Steuercodes blieben in gespeicherten Kriegstiteln erhalten.
3. Der bisherige Delta-Mechanismus konnte bei kleinen Änderungen ganze Listen erneut ablegen.

## Technische Recherche

### Rakaly / Jomini

Rakaly dokumentiert die direkte JSON-Konvertierung binärer CK3-Saves und die Behandlung doppelter Clausewitz-Schlüssel. Die Dokumentation weist außerdem darauf hin, dass neue Content-Patches unbekannte Tokens einführen können und ein aktualisiertes Rakaly erforderlich sein kann.

Quellen:
- https://github.com/rakaly/cli
- https://github.com/rakaly/jomini

Daraus folgen zwei Wächterfeder-Regeln:

- die verwendete Rakaly-Version wird im Snapshot festgehalten;
- der lokal ausgewählte Rakaly-Pfad wird unter `.wachterfeder/ck3/config.json` gespeichert und nicht ins Repository eingecheckt.

### CK3 Events

Paradox dokumentiert für CK3, dass Events persistenten Zustand erzeugen können, beispielsweise automatisch verwaltete Cooldowns. Event-Debugging zeigt zudem Trigger, Scope-Kontext und Lokalisierungsdaten. Persistenter Save-Zustand ist deshalb wertvoll, aber nicht gleichbedeutend mit einem vollständigen Klickprotokoll.

Quelle:
- https://www.paradoxinteractive.com/games/crusader-kings-iii/news/dev-diary-87-royal-modding

Die Wächterfeder trennt deshalb weiterhin:

- `exact`: konkrete Option eindeutig belegt,
- `persistent_state`: Zustand/Memory/Story im Save belegt,
- `save_diff`: Ereignis aus zwei Save-Zuständen rekonstruiert,
- unbekannt: keine ausreichende Evidenz.

## Eingebaute Verbesserungen

### 1. Rekursive Event-Evidenz

`ck3_enhanced.py` steigt durch Manager-Wrapper wie `database` hindurch und sucht erst darunter nach inhaltlichen Datensätzen mit Typ, Event-ID, Datum, State und beteiligten Charakteren.

Damit soll ein Memory nicht mehr als

```json
{"id":"database"}
```

enden, wenn darunter ein konkreter Memory-Datensatz liegt.

### 2. Kompakte Delta-Version 2

Das Delta vergleicht nur einen kleinen Kernzustand:

- Datum und Version,
- Herrscherwerte,
- Primärtitel,
- Erbfolge,
- Familien-IDs,
- Vasallenanzahl,
- aktive Kriegs-IDs.

Größere Familien-, Vasallen- oder Eventobjekte werden nur dann in das Delta geschrieben, wenn sie als semantisches Ereignis relevant sind.

### 3. Semantische Timeline

Aus zwei Saves werden unter anderem erzeugt:

- `child_added`,
- `spouse_added` / `spouse_removed`,
- `death`,
- `title_gained` / `title_lost`,
- `vassal_added` / `vassal_removed`,
- `war_observed_started` / `war_observed_ended`,
- `succession_changed`,
- `trait_gained` / `trait_lost`,
- Glaubens-, Kultur- und Regierungswechsel,
- neue Memories, Stories und wichtige Aktionen.

Der Begriff `observed` bei Kriegen ist absichtlich konservativ: Ein Delta belegt, dass der Krieg zwischen zwei Saves auftaucht bzw. verschwindet, nicht zwingend den exakten Zeitpunkt des Starts oder Endes.

### 4. Nachfolgeanalyse

Der Snapshot erhält einen eigenen Analyseblock mit aufgelöster Nachfolgelinie und Primärerbe, soweit die Charakter-IDs im Save auflösbar sind.

### 5. Vasallen-Watchlist

Direkte Vasallen werden nach gespeicherten Macht-/Stärkewerten beobachtet. Die Watchlist erzeugt `low`, `medium` oder `high` Aufmerksamkeit.

Wichtig: Das ist ausdrücklich eine Heuristik und kein Ersatz für CK3-Meinung, Fraktionsstatus oder die militärische UI-Anzeige.

### 6. Kriegstitel bereinigen

CK3-interne UI-Tokens wie `ONCLICK`, `TOOLTIP` und Lokalisierungsmarker werden aus sichtbaren Kriegstiteln entfernt. Ein realer Testtitel wie der masandaranische Anspruch auf Tabaristan wird dadurch wieder lesbar.

### 7. Rakaly-Komfort

Nach erfolgreicher Auswahl merkt Wächterfeder den lokalen Rakaly-Pfad. Beim nächsten Start wird er automatisch wieder angeboten.

## Bewusst noch nicht geraten

Folgende Punkte bleiben separat, bis lokale CK3-Spieldaten sicher angebunden sind:

- geografisch exakte Nachbarreiche,
- lesbare Namen für numerische Trait-IDs,
- lesbare Kultur-/Glaubensnamen aus numerischen Save-IDs,
- Meinung und Fraktionsstatus, sofern sie im aktuellen Parser nicht eindeutig aufgelöst sind.

Diese Daten werden nicht aus Vermutungen ergänzt.
