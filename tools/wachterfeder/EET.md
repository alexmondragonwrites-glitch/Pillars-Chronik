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

Über die gemeinsame Oberfläche genügt im EET-Tab der Knopf **„Baldur's Gate auswerten“**. Alternativ:

```powershell
python tools/wachterfeder/eet_session.py inspect --save "PFAD_ZUM_SAVE_SLOT"
```

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
- XP, Level, maximale Trefferpunkte, Attribute, Klasse und Kit der Gruppenmitglieder aus eingebetteten CRE-Daten,
- GLOBAL-Variablen,
- neue Journal-Einträge mit Text aus der lokalen `dialog.tlk`,
- lokale Gebietsvariablen aus `BALDUR.SAV`,
- persistente NPC-Gesprächszähler (`NumTimesTalkedTo`) aus gespeicherten ARE-Ressourcen,
- Änderungen all dieser Werte zwischen zwei Saves.

## Kampfprotokoll

Der Save enthält kein vollständiges zeilenweises Protokoll der sichtbaren Kampfmeldungen. Wächterfeder kann Kämpfe derzeit indirekt über XP-, HP-, Party-, Gebiets- und Actor-Zustände erkennen. Ein vollständiger Live-Combat-Logger ist deshalb als optionale Laufzeit-Erweiterung vorgesehen und soll getrennt vom read-only Save-Parser bleiben.

## Aussagekraft

Ein gestiegener NPC-Gesprächszähler belegt, dass seit dem vorherigen Save erneut mit diesem persistenten Actor gesprochen wurde. Zusammen mit neuen GLOBAL-/Gebietsvariablen und Journal-Einträgen lässt sich dadurch ein großer Teil einer Session eingrenzen.

Die exakt gewählte Spielerantwort wird noch nicht automatisch behauptet. Dafür folgt ein separater DLG-/WeiDU-Resolver, der nur eindeutige Pfade als bestätigt markieren soll.
