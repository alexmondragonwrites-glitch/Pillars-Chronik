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

Paradox dokumentiert für CK3, dass Events persistenten Zustand erzeugen können, beispielsweise automatisch verwaltete Cooldowns. Persistenter Save-Zustand ist deshalb wertvoll, aber nicht gleichbedeutend mit einem vollständigen Klickprotokoll.

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

### 2. Kompakte Delta-Version 2

Das Delta vergleicht nur einen kleinen Kernzustand. Größere Familien-, Vasallen- oder Eventobjekte werden nur dann in das Delta geschrieben, wenn sie als semantisches Ereignis relevant sind.

### 3. Semantische Timeline

Aus zwei Saves werden unter anderem Kinder, Ehepartner, Todesfälle, Titel, Vasallen, Kriege, Nachfolge, Traits sowie Glaubens-, Kultur- und Regierungswechsel als Timeline-Kandidaten erzeugt.

### 4. Nachfolgeanalyse

Der Snapshot enthält eine aufgelöste Nachfolgelinie mit Primärerbe, soweit die Charakter-IDs im Save auflösbar sind.

### 5. Vasallen-Watchlist

Direkte Vasallen werden nach gespeicherten Macht-/Stärkewerten beobachtet. Nach dem zweiten Real-Save-Test wurde die Heuristik geschärft: Ein abweichender Glaube wird nur noch als Kontextflag geführt und erhöht allein nicht die Aufmerksamkeitsstufe.

### 6. Kriegstitel bereinigen

CK3-interne UI-Tokens wie `ONCLICK`, `TOOLTIP` und Lokalisierungsmarker werden aus sichtbaren Kriegstiteln entfernt.

### 7. Rakaly-Komfort

Nach erfolgreicher Auswahl merkt Wächterfeder den lokalen Rakaly-Pfad. Beim nächsten Start wird er automatisch wieder angeboten.

### 8. Real-Save-Refinements

`ck3_refined.py` ergänzt auf Basis eines echten CK3-1.19.0.5-Ironman-Saves:

- Event-Teilnehmer werden nach Möglichkeit auf Charaktername + ID aufgelöst.
- `end_date` an Memory-/Eventdatensätzen wird als Roh-End-/Ablaufwert behandelt und ausdrücklich nicht als Ereignisdatum erzählt.
- Aktive Kriege erhalten Rollenauflösung, Gegner, Lehnsherr-Bezug, Casus Belli und Zieltitel.
- Gespeicherte Teilnehmerverluste und Attrition bleiben getrennt, solange ihre exakte Summensemantik nicht belegt ist.
- Direkte Vasallen, in deren aktuellem `succession`-Feld der Spieler steht, werden als vorsichtige `inheritance_opportunities` hervorgehoben.
- Lehnsherr-Kontext enthält den gespeicherten Strength-Vergleich und ob aktuell ein Krieg gegen den Lehnsherrn läuft.
- Der Desktop zeigt den strategischen Kontext direkt unter dem CK3-Status.

Die Detailfunde sind zusätzlich in `docs/CK3_REAL_SAVE_FINDINGS.md` dokumentiert.

## Bewusst noch nicht geraten

Folgende Punkte bleiben separat, bis lokale CK3-Spieldaten sicher angebunden sind:

- geografisch exakte Nachbarreiche,
- lesbare Namen für numerische Trait-IDs,
- lesbare Kultur-/Glaubensnamen aus numerischen Save-IDs,
- Meinung und Fraktionsstatus, sofern sie im aktuellen Parser nicht eindeutig aufgelöst sind.

Diese Daten werden nicht aus Vermutungen ergänzt.
