# Wächterfeder für Warhammer 40,000: Rogue Trader

Der Rogue-Trader-Adapter ist das dritte Wächterfeder-Modul. Er ist bereits so vorbereitet, dass ein späterer großer Run nicht erst als technischer Testlauf herhalten muss.

## Status

**Vorbereitet, noch nicht gegen einen echten Nutzer-Save validiert.**

Der Adapter arbeitet ausschließlich lesend. Er verändert weder Spielstände noch die Rogue-Trader-Installation.

Die aktuelle Stufe verfolgt bewusst zwei Ziele:

1. `.zks`-Spielstände zuverlässig finden, prüfen und vergleichen,
2. die interne Owlcat-Struktur kompakt kartieren, ohne komplette Save-Inhalte in immer größere JSON-Dateien zu duplizieren.

Sobald ein echter Save verfügbar ist, können wir stabile Feldzuordnungen für Quests, Convictions, Gefolge, Ruf, Etudes und weitere Chronikdaten ergänzen, ohne die Basis neu zu schreiben.

## Typischer Speicherort

Unter Windows prüft Wächterfeder insbesondere:

```text
%USERPROFILE%\AppData\LocalLow\Owlcat Games\Warhammer 40000 Rogue Trader\Saved Games
```

Zusätzlich wird der von Owlcat-Werkzeugen verwendete Kurzname `WH 40000 RT` berücksichtigt.

## Lokale Ausgaben

Nach einer erfolgreichen Analyse entstehen:

```text
.wachterfeder/rogue-trader/rogue-trader.snapshot.json
.wachterfeder/rogue-trader/rogue-trader.delta.json
.wachterfeder/rogue-trader/history/*.delta.json
```

`rogue-trader.snapshot.json` ist nur der aktuelle Vergleichsstand. Es werden keine fortlaufenden Vollsnapshots erzeugt.

`rogue-trader.delta.json` enthält ausschließlich Änderungen gegenüber dem letzten erfolgreichen Lauf.

Damit bleibt die Datenmenge auch bei einem sehr langen Run beherrschbar.

## Was der vorbereitete Adapter bereits kann

- `.zks`-Spielstände automatisch finden,
- neuesten Save bestimmen,
- SHA-256 des Original-Saves berechnen,
- Archiv und CRC-Werte read-only prüfen,
- enthaltene Dateien mit Größe und CRC inventarisieren,
- JSON-Dokumente erkennen,
- deren Struktur kompakt sondieren,
- story- und charakterrelevante skalare Kandidaten erfassen,
- zwei aufeinanderfolgende Saves gegeneinander diffen,
- geänderte Archivdateien und geänderte Signale getrennt ausgeben,
- beschädigte oder nicht unterstützte Saves sauber ablehnen.

## Kompakter Schema-Probe

Bis wir einen echten Rogue-Trader-Save kartiert haben, speichert Wächterfeder **nicht** den kompletten Inhalt von `player.json` oder anderen großen Save-Dateien.

Stattdessen landen im Snapshot nur:

- Dateinamen und Prüfdaten,
- Top-Level-Schlüssel der JSON-Dokumente,
- Pfade und Datentypen potenziell interessanter Felder,
- eine begrenzte Menge passender skalarer Werte.

Der Probe achtet derzeit unter anderem auf Begriffe aus diesen Bereichen:

- Quest / Objective / Etude,
- Conviction, Dogmatic, Iconoclast, Heretic,
- Reputation / Faction,
- Companion / Party,
- Dialogue / Answer / Choice,
- Romance / Relationship,
- Area / Location / Chapter,
- Career / Archetype / Level / Experience,
- Profit Factor,
- Ship / Colony.

Diese Treffer sind zunächst **Kandidaten**. Sie werden erst nach Real-Save-Validierung als konkrete Spielbedeutung dokumentiert.

## CLI

Speicherorte prüfen:

```powershell
python tools/wachterfeder/rogue_trader.py paths
```

Einen Save oder einen Ordner mit Saves analysieren:

```powershell
python tools/wachterfeder/rogue_trader.py inspect `
  --save "$env:USERPROFILE\AppData\LocalLow\Owlcat Games\Warhammer 40000 Rogue Trader\Saved Games"
```

Beim ersten Lauf ist das Delta ein Initialzustand. Ab dem zweiten Lauf enthält es nur die Unterschiede.

## Geplante Runtime-Schicht

Owlcat stellt für Rogue Trader ein offizielles Modification Template bereit. Das Spiel unterstützt unter anderem:

- Harmony-Patching,
- `EventBus`-Subscriber,
- Rulebook-Events,
- per-Save gespeicherte Mod-Daten,
- eine integrierte Unity-Mod-Manager-Umgebung.

Darauf soll später ein sehr kleiner **Wächterfeder Runtime Logger** aufsetzen. Er soll nicht den Spielstand verändern, sondern nur eindeutige Ereignisse lokal protokollieren, die aus einem Save-Diff allein schwer zeitlich zu rekonstruieren sind.

Geplanter lokaler Vertrag:

```json
{"event_id":"...","timestamp_utc":"...","event_type":"dialogue_choice","conversation_id":"...","answer_id":"..."}
{"event_id":"...","timestamp_utc":"...","event_type":"quest_changed","quest_id":"...","state":"..."}
{"event_id":"...","timestamp_utc":"...","event_type":"companion_reaction","companion_id":"...","value":1}
```

Diese Runtime-Dateien bleiben ebenfalls unter `.wachterfeder/` und werden nicht eingecheckt.

Offizielle technische Grundlage:

```text
https://github.com/OwlcatOpenSource/RTModificationTemplate
```

## Zielbild für den großen Run

Am Ende sollen drei Datenebenen zusammenlaufen:

```text
Rogue-Trader-Save
      ↓
rogue-trader.snapshot.json   = aktueller Zustand
      ↓
rogue-trader.delta.json      = Änderungen seit dem letzten Save

Runtime Logger
      ↓
runtime.jsonl                = eindeutige Ereignisse in Reihenfolge

Snapshot + Delta + Runtime
      ↓
Chronik / Charakterentwicklung / Entscheidungen / Konsequenzen
```

Damit kann eine spätere Chronik unterscheiden zwischen:

- **bestätigt:** direkt beobachtetes Runtime-Ereignis,
- **belegt:** eindeutige Save-Änderung,
- **rekonstruiert:** plausible Verbindung mehrerer Signale,
- **unbekannt:** Daten reichen nicht für eine sichere Aussage.

## Was für die nächste Validierungsstufe noch fehlt

Ein einziger echter `.zks`-Save reicht für die erste Kartierung. Ideal sind später zwei Saves mit einer kleinen bekannten Änderung dazwischen, zum Beispiel:

1. Save vor einer Questentscheidung,
2. Entscheidung treffen,
3. neuer Save.

Damit können wir exakt sehen, welche Owlcat-Felder für Quest, Dialog, Conviction und Begleiterreaktionen tatsächlich relevant sind.

Bis dahin bleibt der Adapter absichtlich konservativ und updatefest.
