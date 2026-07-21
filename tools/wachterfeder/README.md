# Wächterfeder MVP

Wächterfeder ist die lokale Brücke zwischen einem *Pillars of Eternity*-Spielstand und der Serin-Chronik. Das Werkzeug arbeitet ausschließlich lesend und verändert keinen Originalspielstand.

## Speicherstand finden

Unter Windows liegt der normale Steam-/GOG-Ordner meist hier:

```text
%USERPROFILE%\Saved Games\Pillars of Eternity
```

Direkt öffnen:

1. `Win + R` drücken.
2. `%USERPROFILE%\Saved Games\Pillars of Eternity` einfügen.
3. Nach Dateien mit der Endung `.savegame` suchen.

Alternativ öffnet `shell:SavedGames` den Windows-Ordner „Gespeicherte Spiele“. Bei Microsoft-Store-/Game-Pass-Versionen kann unter `Pillars of Eternity` zusätzlich ein numerischer Unterordner liegen.

## Benutzung

Voraussetzung ist Python 3.10 oder neuer. Aus dem Repository-Stamm:

```powershell
python tools/wachterfeder/wachterfeder.py paths
```

Einen Spielstand analysieren:

```powershell
python tools/wachterfeder/wachterfeder.py snapshot `
  "$env:USERPROFILE\Saved Games\Pillars of Eternity\DEIN_SAVE.savegame"
```

Das Werkzeug:

- berechnet die SHA-256-Prüfsumme,
- legt unter `.wachterfeder/cache/` eine schreibgeschützte Arbeitskopie ab,
- prüft ZIP-Struktur und CRC-Werte,
- inventarisiert alle enthaltenen Dateien,
- liest `saveinfo.xml`,
- extrahiert konservativ Level, Erfahrung, Basisattribute, persistierte Fertigkeiten und Talente,
- liest globale Integer-Questvariablen,
- rekonstruiert `ConversationManager.MarkedAsRead`,
- gibt pro Dialogdatei die im Save markierten Node-IDs aus,
- erzeugt einen maschinenlesbaren JSON-Snapshot.

Die extrahierten Fertigkeitswerte sind persistierte Save-Werte. Angezeigte Endwerte im Spiel können durch Herkunft, Hintergrund, Ausrüstung oder andere Modifikatoren abweichen.

## Validierung mit Serins echtem Save

Der erste reale Testsave wurde am 21. Juli 2026 erfolgreich gelesen:

- Spielerin: Serin Ashwyn
- Gebiet: Talholz (`AR_0704_Valewood`)
- Schwierigkeit: Schwer
- Level: 2
- Erfahrung: 1568
- 1937 globale Variablen erkannt
- 20 Dialogdateien in `MarkedAsRead`
- 199 markierte Dialogknoten rekonstruiert
- Talent `TLN_Ancient_Memory` erkannt

Der Testsave selbst und sein vollständiger Snapshot werden nicht ins öffentliche Repository eingecheckt.

## Tests

```powershell
python -m unittest discover -s tools/wachterfeder/tests -v
```

Die Tests decken Pfaderkennung, Originalschutz, XML-Metadaten, Charakterwerte, globale Variablen und die Rekonstruktion eines BitArray-basierten Dialogzustands ab.

## Nächster Schritt

1. Lokale `.conversation`-Dateien und deutsche/englische `.stringtable`-Dateien indexieren.
2. Dateiname und Node-ID mit dem tatsächlichen Dialogtext verbinden.
3. Zwei aufeinanderfolgende Saves vergleichen, um neu gespielte Nodes und geänderte Questvariablen zu isolieren.
4. Aus diesem Diff eine bestätigungspflichtige Chronik-Vorschau erzeugen.
