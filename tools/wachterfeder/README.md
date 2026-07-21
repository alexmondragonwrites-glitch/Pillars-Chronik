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

## Savegame analysieren

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

## Dialoggraphen verbinden

Die `.conversation`-Dateien der lokalen Spielinstallation können mit einem erzeugten Save-Snapshot verbunden werden:

```powershell
python tools/wachterfeder/dialogues.py `
  .wachterfeder\serin.snapshot.json `
  "C:\Pfad\zu\PillarsOfEternity_Data\data\conversations\07_gilded_vale" `
  --output .wachterfeder\serin-dialoge.json
```

Mit lokalisierten Texten:

```powershell
python tools/wachterfeder/dialogues.py `
  .wachterfeder\serin.snapshot.json `
  "C:\Pfad\zu\PillarsOfEternity_Data\data\conversations\07_gilded_vale" `
  --stringtable-root "C:\Pfad\zu\PillarsOfEternity_Data\data\localized\de\text\conversations\07_gilded_vale" `
  --output .wachterfeder\serin-dialoge-de.json
```

Der Dialogreport enthält:

- alle im Save markierten Nodes samt Typ, Sprecher-GUID und Verbindungen,
- sichere Kanten zwischen tatsächlich abgespielten Nodes,
- mehrdeutige oder wiederholt durchlaufene Verzweigungen,
- Bedingungen und Script-Aufrufe,
- hervorgehobene storyrelevante Folgen wie Quest-, Dispositions-, Gruppen- und Globalvariablenänderungen,
- optional den deutschen oder englischen Originaltext aus der passenden `.stringtable`.

`MarkedAsRead` ist kein garantiert chronologisches Protokoll. Wiederholbare Gespräche können mehrere durchlaufene Zweige enthalten. Wächterfeder gibt deshalb belegte Teilgraphen aus und erfindet keine lineare Reihenfolge, wenn der Save sie nicht beweist.

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

Der anschließend bereitgestellte Ordner `07_gilded_vale` enthielt 121 Dialoggraphen. Alle 20 im Save referenzierten Gespräche konnten eindeutig zugeordnet werden. Dabei wurden unter anderem Dispositionsänderungen, Queststarts, Gruppenänderungen, Gegenstandsaktionen, Cutscenes und gesetzte Globalvariablen erkannt.

Der Testsave, vollständige Snapshots, extrahierte Dialogtexte und Spielressourcen werden nicht ins öffentliche Repository eingecheckt.

## Tests

```powershell
python -m unittest discover -s tools/wachterfeder/tests -v
```

Die Tests decken Pfaderkennung, Originalschutz, XML-Metadaten, Charakterwerte, globale Variablen, BitArray-basierte Dialogzustände, Dialoggraphen, lokalisierte Stringtables sowie sichere und mehrdeutige Pfadkanten ab.

## Nächste Schritte

1. Deutsche und optional englische `.stringtable`-Dateien mit den Dialoggraphen verbinden.
2. Zwei aufeinanderfolgende Saves vergleichen, um neu gespielte Nodes und geänderte Questvariablen zeitlich zu isolieren.
3. Sprecher-GUIDs über lokale Game-Daten in lesbare Namen übersetzen.
4. Aus dem Diff eine bestätigungspflichtige Chronik-Vorschau erzeugen.
