# Wächterfeder: Snapshot und Delta

Die Desktop-App erzeugt nach jeder erfolgreichen Auswertung zwei relevante Dateien:

```text
.wachterfeder/serin.snapshot.json
.wachterfeder/serin.delta.json
```

## Vollständiger aktueller Stand

`serin.snapshot.json` enthält weiterhin den vollständigen Zustand des zuletzt analysierten Saves. Die Datei wird bei jedem erfolgreichen Lauf überschrieben und dient anschließend als Vergleichsbasis.

## Nur neu seit dem letzten Save

`serin.delta.json` enthält ausschließlich Änderungen gegenüber der vorherigen erfolgreichen Auswertung:

- geänderte Metadaten wie Ort oder Spielzeit,
- Level, Erfahrung, Fertigkeiten, Talente und andere Spielerwertänderungen,
- geänderte globale Spiel- und Questvariablen mit `from` und `to`,
- vollständig neue Gespräche,
- neue Knoten in bereits bekannten Gesprächen,
- neue abgespielte oder deterministische Dialogkanten,
- neue storyrelevante Scripts,
- neu aufgelöste oder neu fehlende Dialogressourcen.

Lokale Installationspfade werden nicht in das Delta übernommen.

## Interne Vergleichsbasis

Der vollständige lokalisierte Dialogreport wird nicht mehr als sichtbare Ergebnisdatei ausgegeben. Er liegt ausschließlich lokal unter:

```text
.wachterfeder/state/serin-dialoge-de.json
```

Diese Datei wird überschrieben und nur für den nächsten Vergleich benötigt. Sie gehört nicht in Git und muss für die Chronik nicht hochgeladen werden.

## Verlauf

Unter `.wachterfeder/history/` werden künftig nur noch kleine Delta-Dateien gespeichert:

```text
20260724-055218-serin-ashwyn-c60db75b.delta.json
```

Neue vollständige historische Snapshot- oder Dialogreport-Kopien werden nicht mehr angelegt. Bereits vorhandene alte Dateien werden nicht automatisch gelöscht.

## Migration

Existieren bereits `serin.snapshot.json` und `serin-dialoge-de.json`, verwendet der erste Lauf nach dem Update beide automatisch als alte Vergleichsbasis. Anschließend wird der große Dialogreport in den internen `state`-Ordner überführt und die frühere sichtbare Datei entfernt.

Ohne vorhandene Vergleichsbasis wird `initial_snapshot` auf `true` gesetzt. Nur in diesem ersten Lauf kann das Delta den vollständigen Ausgangsstand enthalten. Beim erneuten Analysieren desselben Saves entsteht ein leeres Delta mit `has_changes: false`.

## Semantik

`MarkedAsRead` ist kein garantiert chronologisches Protokoll. Das Delta isoliert zuverlässig neue gelesene Knoten und geänderte Spielwerte, konstruiert bei wiederholbaren Gesprächen aber weiterhin keine unbelegte Reihenfolge.
