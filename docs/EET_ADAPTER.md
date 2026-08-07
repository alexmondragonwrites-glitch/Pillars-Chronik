# Wächterfeder für Baldur's Gate EET

Der EET-Adapter erweitert Wächterfeder um einen read-only Parser für Spielstände der Enhanced Edition Trilogy.

## Ziel des MVP

Der erste Stand reduziert die Screenshot-Abhängigkeit bereits für alle Informationen, die zuverlässig in `BALDUR.GAM` gespeichert sind:

- aktuelles Gebiet und Kampagne,
- Party und Partypositionen,
- Gold,
- Ruf,
- globale Story- und Questvariablen,
- Journal-Einträge,
- kleine Deltas zwischen zwei aufeinanderfolgenden Saves.

Die Originalspielstände und Spielressourcen werden nicht verändert und nicht ins Repository kopiert.

## Lokale Dateien

Nach einer erfolgreichen Analyse entstehen nur zwei relevante Dateien:

```text
.wachterfeder/eet/eet.snapshot.json
.wachterfeder/eet/eet.delta.json
```

`eet.snapshot.json` ist der vollständige aktuelle Vergleichsstand. `eet.delta.json` enthält nur die Änderungen seit dem vorherigen erfolgreichen Lauf.

Historische Deltas liegen unter:

```text
.wachterfeder/eet/history/
```

## Voraussetzungen

Wächterfeder benötigt lokal:

1. einen EET-Saveordner mit `BALDUR.GAM`,
2. den EET/BG2EE-Spielordner mit `chitin.key`,
3. die passende `lang/<sprache>/dialog.tlk`.

Ein vorhandenes WeiDU-Programm oder eines der üblichen `setup-*.exe` wird erkannt, ist für den Save-MVP aber noch nicht zwingend erforderlich.

## Typische Speicherorte

Unter Windows sucht der Adapter unter anderem hier:

```text
%USERPROFILE%\Documents\Baldur's Gate II - Enhanced Edition\save
%USERPROFILE%\Documents\Baldur's Gate II - Enhanced Edition\mpsave
```

Bei OneDrive wird zusätzlich der entsprechende Documents-Pfad geprüft.

## CLI

Speicherorte prüfen:

```powershell
python tools/wachterfeder/eet.py paths
```

Einen Spielstand analysieren:

```powershell
python tools/wachterfeder/eet.py inspect `
  --save "C:\...\Baldur's Gate II - Enhanced Edition\save\000000001-Quick-Save" `
  --game-path "E:\...\Baldur's Gate II - Enhanced Edition" `
  --language de_DE
```

Der `--save`-Parameter kann auf den Saveordner oder direkt auf `BALDUR.GAM` zeigen.

## Delta-Inhalt

Das Delta erfasst derzeit:

- geänderte Metadaten,
- geänderte globale Variablen mit `from` und `to`,
- neue, entfernte oder veränderte Gruppenmitglieder,
- neue Journal-Einträge samt lokal aufgelöstem Text, sofern der Eintrag direkt auf `dialog.tlk` verweist.

## Noch offen: exakte Dialogwahl

Infinity-Engine-Dialoge liegen als `DLG`-Ressourcen vor und verwenden Texte aus `dialog.tlk`. EET-Installationen verfügen durch das Mod-Setup typischerweise bereits über eine WeiDU-kompatible Umgebung. Der nächste Adapter-Schritt wird daraus einen lokalen Dialogindex erzeugen und Save-Deltas gegen Dialogaktionen und globale Variablen abgleichen.

Dabei gilt dieselbe Regel wie bei Pillars: Eine konkrete Spielerantwort wird nur als bestätigt markiert, wenn die Daten den Pfad eindeutig belegen. Andernfalls bleibt sie als rekonstruiert oder unbekannt gekennzeichnet.

## Für die reale EET-Validierung benötigt

Für den nächsten Schritt reichen drei lokale Informationen beziehungsweise Dateien:

1. ein aktueller EET-Saveordner oder mindestens dessen `BALDUR.GAM`,
2. der Pfad zum EET-Spielordner,
3. idealerweise ein zweiter Save nach einer kleinen, klar bekannten Spielsitzung.

Der zweite Save ist besonders wertvoll, weil damit Globals, Journal, Gruppenänderungen und später Dialogaktionen an einem realen Delta getestet werden können.
