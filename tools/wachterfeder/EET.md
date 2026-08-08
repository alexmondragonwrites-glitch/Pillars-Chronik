# Wächterfeder für Baldur's Gate EET

Der EET-Adapter arbeitet ausschließlich lesend auf lokalen Spielständen. Er behandelt `BALDUR.GAM` und `BALDUR.SAV` gemeinsam als aktuellen Zustand und schreibt keine Spielressourcen ins Repository.

## Einmalige Einrichtung

Aus dem Repository-Stamm den lokalen EET/BG2EE-Spielordner speichern:

```powershell
python tools/wachterfeder/eet_session.py configure "D:\Games\BG_Modded\BG2EE"
```

Gespeichert werden nur Spielordner und Sprache unter `.wachterfeder/eet/config.json`. Der Ordner ist git-ignoriert.

## Session auswerten

Danach genügt ein Doppelklick auf:

```text
EET auswerten.cmd
```

Alternativ:

```powershell
python tools/wachterfeder/eet_session.py inspect
```

Wächterfeder sucht den neuesten Save unter den üblichen EET- und BG2EE-Dokumentordnern. Ein bestimmter Spielstand kann mit `--save` angegeben werden.

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

## Aussagekraft

Ein gestiegener NPC-Gesprächszähler belegt, dass seit dem vorherigen Save erneut mit diesem persistenten Actor gesprochen wurde. Zusammen mit neuen GLOBAL-/Gebietsvariablen und Journal-Einträgen lässt sich dadurch ein großer Teil einer Session eingrenzen.

Die exakt gewählte Spielerantwort wird noch nicht automatisch behauptet. Dafür folgt ein separater DLG-/WeiDU-Resolver, der nur eindeutige Pfade als bestätigt markieren soll.

## Welche Save-Dateien wichtig sind

Für den normalen Session-Vergleich reichen grundsätzlich:

```text
BALDUR.GAM
BALDUR.SAV
```

`BALDUR.bmp` und `PORTRT*.bmp` sind für die Chronologie nicht bei jeder Session nötig. Sie können später optional für eine visuelle Charakter-/Partychronik genutzt werden.
