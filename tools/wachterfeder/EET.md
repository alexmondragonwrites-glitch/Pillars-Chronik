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

## Optionaler EEex-Combat-Logger

Wenn EEex im EET-Spielordner installiert ist, kann Wächterfeder zusätzlich einen kleinen Laufzeit-Logger installieren. Das geht jetzt direkt im **EET-Tab der gemeinsamen Wächterfeder-Oberfläche**. Dort werden außerdem sichtbar angezeigt:

```text
EEex erkannt / nicht erkannt
Wächterfeder-Logger installiert / nicht installiert
Log vorhanden / noch kein Log
```

Die Installation erfolgt nur nach einem ausdrücklichen Klick auf **„Combatlogger installieren“** und legt genau eine Modder-Lua-Datei an:

```text
<BG2EE>\override\M_WFLOG.lua
```

Alternativ bleibt der bisherige Helfer verfügbar:

```text
EET Combatlogger installieren.cmd
```

Das Laufzeitprotokoll bleibt lokal:

```text
.wachterfeder/eet/runtime/combat.jsonl
```

Version 1 erfasst tatsächlichen HP-Verlust nach einem EEex-Damage-Effekt, Quelle und Ziel soweit auflösbar, HP vor/nach dem Effekt und `lethal_candidate` bei HP <= 0. `lethal_candidate` ist noch kein separat bestätigter Tod.

EET weiterhin ausschließlich über `InfinityLoader.exe` starten.

Die Delta-Ausgabe ergänzt unter anderem:

```text
summary.party_hit_point_changes
summary.party_conversations
summary.dialogue_events_considered
summary.dialogue_high_confidence
summary.dialogue_medium_confidence
summary.combat_events
```

und unter `changes`:

```text
party_hit_points
party_conversations
dialogue_resolution
combat_log
```

## Aussagekraft

Ein gestiegener Gesprächszähler belegt eine neue Interaktion, aber nicht für sich allein die exakte Spielerantwort. Erst eine eindeutige Kombination aus Dialogstruktur und beobachtbaren Save-Änderungen darf eine Antwort als bestätigt markieren. Wo diese Evidenz fehlt, bleibt Wächterfeder ausdrücklich bei einer niedrigeren Sicherheit.
