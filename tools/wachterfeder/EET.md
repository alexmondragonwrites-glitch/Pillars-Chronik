# Wächterfeder für Baldur's Gate EET

Der EET-Adapter arbeitet ausschließlich lesend auf lokalen Spielständen. Er behandelt `BALDUR.GAM` und `BALDUR.SAV` gemeinsam als aktuellen Zustand und schreibt keine Spielressourcen ins Repository.

## Gemeinsame Oberfläche

`Wachterfeder starten.bat` öffnet die gemeinsame Desktop-App mit zwei Tabs:

- **Pillars of Eternity**
- **Baldur's Gate EET**

Für EET werden drei lokale Angaben verwaltet: der übergeordnete `save`-Ordner, der aktuelle Save-Slot und der EET/BG2EE-Spielordner. Persönliche Pfade werden nur unter `.wachterfeder/` gespeichert und nicht committed.

Ein typischer EET-Save sieht so aus:

```text
Baldur's Gate - Enhanced Edition Trilogy/
└── save/
    ├── 000000000-Auto-Save/
    ├── 000000001-Quick-Save/
    │   ├── BALDUR.GAM
    │   ├── BALDUR.SAV
    │   ├── BALDUR.bmp
    │   └── PORTRT0.bmp ... PORTRT5.bmp
    └── weitere Save-Slots/
```

Für die maschinelle Chronik werden normalerweise nur `BALDUR.GAM` und `BALDUR.SAV` benötigt. Die BMP-Dateien sind optional und können später für eine visuelle Partychronik verwendet werden.

## Umgeleitete Windows-Dokumentordner

`EET Spielstand finden.cmd` fragt den von Windows registrierten Dokumentordner ab. Dadurch funktionieren auch Installationen, bei denen **Dokumente** auf ein anderes Laufwerk verschoben wurde. Danach werden insbesondere diese Unterordner geprüft:

```text
Baldur's Gate - Enhanced Edition Trilogy\save
Baldur's Gate - Enhanced Edition Trilogy\mpsave
Baldur's Gate II - Enhanced Edition\save
Baldur's Gate II - Enhanced Edition\mpsave
```

## Einmalige Einrichtung per CLI

Alternativ zur Oberfläche kann der lokale EET/BG2EE-Spielordner gespeichert werden:

```powershell
python tools/wachterfeder/eet_session.py configure "D:\Games\BG_Modded\BG2EE"
```

Gespeichert werden nur lokale Einstellungen unter `.wachterfeder/eet/config.json`. Der Ordner ist git-ignoriert.

## Session auswerten

Über die gemeinsame Oberfläche genügt im EET-Tab der Knopf **„Baldur's Gate auswerten“**.

## Ausgaben

```text
.wachterfeder/eet/eet.snapshot.json
.wachterfeder/eet/eet.delta.json
.wachterfeder/eet/history/*.delta.json
```

Der Snapshot enthält den vollständigen aktuellen Stand. Das Delta enthält nur Änderungen seit der vorherigen erfolgreichen Auswertung.

Aktuell erfasst werden:

- Kampagne, Kapitel, Gebiet, Gold und Ruf,
- Party-Zusammensetzung,
- XP, Level, maximale und aktuelle Trefferpunkte, Attribute, Klasse und Kit der Gruppenmitglieder,
- aktuelle HP-Änderungen zwischen zwei Saves separat unter `party_hit_points`,
- GLOBAL-Variablen,
- neue Journal-Einträge mit Text aus der lokalen `dialog.tlk`,
- lokale Gebietsvariablen aus `BALDUR.SAV`,
- persistente NPC-Gesprächszähler (`NumTimesTalkedTo`) aus gespeicherten ARE-Ressourcen,
- gestiegene Gesprächszähler von aktuellen Party-CREs,
- Änderungen all dieser Werte zwischen zwei Saves.

## Dialogauflösung über die lokale modifizierte Installation

Wächterfeder benutzt für einen neu erkannten NPC- oder Party-Dialog den **lokal installierten WeiDU-Decoder**. Das effektive `DLG` wird nur temporär dekompiliert und nicht ins Repository oder in ein dauerhaftes Rohdialog-Archiv geschrieben.

Der Resolver kombiniert:

- den gestiegenen `NumTimesTalkedTo`-Wert,
- den tatsächlich verwendeten Dialog-ResRef,
- veränderte `GLOBAL`-Variablen,
- neue Journal-Einträge,
- beobachtbare `SetGlobal`-/`IncrementGlobal`- und Journal-Aktionen der möglichen Dialogtransitionen.

Die Ausgabe landet unter:

```text
changes.dialogue_resolution
```

mit den Sicherheitsstufen:

- `high`: genau ein Pfad passt zu beobachtbarer Save-Evidenz; nur dann darf `confirmed_reply` gesetzt werden,
- `medium`: ein Pfad ist plausibel, aber nicht eindeutig genug für eine bestätigte Spielerantwort,
- `low`: Dialog wurde gefunden, die Save-Daten reichen aber nicht zur Pfadbestimmung.

Damit wird eine konkrete Spielerantwort niemals allein aus dem Dialogbaum geraten.

## Optionaler EEex-Runtime-Logger V3

EEex kann zusätzlich als Laufzeit-Sensor dienen. Der **Runtime-Logger V3** beobachtet derzeit zwei Dinge:

- tatsächlichen HP-Verlust rund um die von EEex bereitgestellten Damage-Hooks,
- tatsächliche Aufrufe von `Infinity_SelectDialogueOption`, also die Auswahl einer Dialogantwort durch den Spieler.

Die Installation erfolgt nur nach einem ausdrücklichen Klick auf **„Runtime-Logger installieren/aktualisieren“** im EET-Tab und legt genau eine Modder-Lua-Datei an:

```text
<BG2EE>\override\M_WFLOG.lua
```

Der Logger benutzt absichtlich **kein `io.open`**. EEex Minimal kann die Standard-Lua-`io`-Bibliothek ausblenden. Stattdessen wird der von Beamdog/EEex vorgesehene Engine-Logging-Weg `C:LogSet` + `C:LogMessages` verwendet. Die lokale Runtime-Datei liegt im Spielordner:

```text
<BG2EE>\Wachterfeder-runtime.log
```

Sie ist kein Repository-Inhalt. Beim Entfernen des Wächterfeder-Runtime-Loggers wird auch diese eindeutig benannte lokale Logdatei nach Möglichkeit entfernt.

Nach dem Start über `InfinityLoader.exe` schreibt V3 zuerst einen `runtime_start`-Heartbeat. Die Oberfläche unterscheidet deshalb zwischen:

```text
Runtime-Logger aktuell
wartet auf InfinityLoader-Start
Heartbeat empfangen
```

Erst **„Heartbeat empfangen“** bestätigt, dass der Lua-Runtimekanal in dieser Installation wirklich ausgeführt wurde. Ein bloß vorhandenes Script gilt nicht mehr als Beweis für einen funktionierenden Logger.

### Runtime-Ereignisse

Kampfereignisse enthalten soweit verfügbar Quelle, Ziel, tatsächlichen HP-Verlust, HP vor/nach dem Effekt und `lethal_candidate`. `lethal_candidate` bedeutet nur `HP <= 0` nach diesem Effekt und ist noch kein separat bestätigter Tod.

Bei Dialogen protokolliert V3 zunächst bewusst die rohen Argumente von `Infinity_SelectDialogueOption`, den ausgewählten Charakter, Screen und Game-Ticks. Diese Rohdaten werden **noch nicht automatisch als Dialogtext ausgegeben**. Erst wenn die Argumentstruktur in der realen EET-Installation bestätigt und mit dem lokalen DLG/WeiDU-Resolver verknüpft ist, wird daraus eine konkrete gewählte Antwort.

Die Delta-Ausgabe ergänzt unter anderem:

```text
summary.runtime_events
summary.runtime_starts
summary.live_dialogue_choices
summary.combat_events
summary.combat_damage_total
```

und unter `changes`:

```text
runtime_log
combat_log
live_dialogue_choices
runtime_diagnostics
```

EET weiterhin über `InfinityLoader.exe` starten.

## Aussagekraft

Ein gestiegener Gesprächszähler belegt eine neue persistente Interaktion, aber nicht für sich allein die exakte Spielerantwort. Direkte Gefährtengespräche erhöhen diesen Zähler nicht zuverlässig, weshalb V3 zusätzlich die tatsächliche Auswahlfunktion der Dialog-UI beobachtet.

Auch beim Livekanal gilt: Wächterfeder trennt **Beobachtung** von **Interpretation**. Eine erfasste Dialogauswahl ist ein starkes Runtime-Signal; der konkrete Antworttext wird erst nach bestätigter Zuordnung zum lokalen Dialogbaum als sicher bezeichnet.
