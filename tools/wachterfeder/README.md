# Wächterfeder MVP

Wächterfeder ist die lokale Brücke zwischen einem *Pillars of Eternity*-Spielstand und der Serin-Chronik. Das Werkzeug arbeitet ausschließlich lesend und verändert keinen Originalspielstand.

## Ein-Klick-Oberfläche unter Windows

Nach dem ersten Aktualisieren des Repositorys genügt ein Doppelklick auf:

```text
Wachterfeder starten.bat
```

Die kleine Desktop-Oberfläche bietet:

- automatische Auswahl des neuesten Pillars-Spielstands,
- freie Auswahl einer anderen `.savegame`-Datei,
- einmalige Auswahl der lokalen Pillars-Installation,
- einen großen Knopf **„Serin auswerten“**,
- automatische Erstellung von Snapshot und deutschem Dialogreport,
- einen lokalen Verlauf unter `.wachterfeder/history/`,
- direktes Öffnen des Ergebnisordners.

Der bekannte Installationspfad

```text
E:\SteamLibrary\steamapps\common\Pillars of Eternity
```

wird automatisch vorgeschlagen, sofern er auf dem Rechner existiert. Die App benötigt keine zusätzlichen Python-Pakete; die Oberfläche verwendet das mit Python gelieferte Tkinter.

Alle Spielstände, Konfigurationen und erzeugten Reports bleiben im ignorierten Ordner `.wachterfeder/` und gelangen nicht ins Repository.

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

## Lokale Spielinstallation verbinden

Originaldialoge und Lokalisierungsdateien werden nicht ins Repository kopiert. Wächterfeder speichert ausschließlich den lokalen Datenpfad und die Sprache in `.wachterfeder/config.json`. Dieser gesamte Ordner ist per `.gitignore` ausgeschlossen.

Der Pfad kann der Spielordner oder ein beliebiger Unterordner innerhalb von `PillarsOfEternity_Data\data` sein. Für die aktuelle Installation funktioniert beispielsweise direkt:

```powershell
python tools/wachterfeder/local_dialogues.py configure `
  "E:\SteamLibrary\steamapps\common\Pillars of Eternity\PillarsOfEternity_Data\data\localized\de\text\conversations"
```

Wächterfeder ermittelt daraus automatisch:

```text
E:\SteamLibrary\steamapps\common\Pillars of Eternity\PillarsOfEternity_Data\data\conversations
E:\SteamLibrary\steamapps\common\Pillars of Eternity\PillarsOfEternity_Data\data\localized\de\text\conversations
```

Gespeicherte Pfade prüfen:

```powershell
python tools/wachterfeder/local_dialogues.py status
```

Einen Save-Snapshot anschließend mit den lokalen Dialogen verbinden:

```powershell
python tools/wachterfeder/local_dialogues.py report `
  .wachterfeder\serin.snapshot.json `
  --output .wachterfeder\serin-dialoge-de.json
```

Alternativ kann ein Pfad einmalig ohne Konfigurationsdatei übergeben werden:

```powershell
python tools/wachterfeder/local_dialogues.py report `
  .wachterfeder\serin.snapshot.json `
  --game-path "E:\SteamLibrary\steamapps\common\Pillars of Eternity" `
  --language de `
  --output .wachterfeder\serin-dialoge-de.json
```

Mit `--remember` wird ein erfolgreich geprüfter `--game-path` lokal gespeichert.

## Dialoggraphen direkt verbinden

Für Sonderfälle kann der niedrigere Dialogparser weiterhin mit expliziten Ordnern aufgerufen werden:

```powershell
python tools/wachterfeder/dialogues.py `
  .wachterfeder\serin.snapshot.json `
  "E:\SteamLibrary\steamapps\common\Pillars of Eternity\PillarsOfEternity_Data\data\conversations" `
  --stringtable-root "E:\SteamLibrary\steamapps\common\Pillars of Eternity\PillarsOfEternity_Data\data\localized\de\text\conversations" `
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

Alle 20 im Save referenzierten Gespräche konnten eindeutig mit lokalen Dialoggraphen und deutschen Stringtables verbunden werden. Dabei wurden unter anderem Dispositionsänderungen, Queststarts, Gruppenänderungen, Gegenstandsaktionen, Cutscenes und gesetzte Globalvariablen erkannt.

Der Testsave, vollständige Snapshots, extrahierte Dialogtexte und Spielressourcen werden nicht ins öffentliche Repository eingecheckt.

## Tests

```powershell
python -m unittest discover -s tools/wachterfeder/tests -v
```

Die Tests decken Pfaderkennung, Originalschutz, XML-Metadaten, Charakterwerte, globale Variablen, BitArray-basierte Dialogzustände, Dialoggraphen, lokalisierte Stringtables, lokale Installationspfade, die Ein-Klick-Pipeline sowie sichere und mehrdeutige Pfadkanten ab.

## Nächste Schritte

1. Zwei aufeinanderfolgende Saves vergleichen, um neu gespielte Nodes und geänderte Questvariablen zeitlich zu isolieren.
2. Sprecher-GUIDs über lokale Game-Daten in lesbare Namen übersetzen.
3. Aus dem Diff eine bestätigungspflichtige Chronik-Vorschau erzeugen.
