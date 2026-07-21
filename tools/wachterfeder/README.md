# Wächterfeder MVP

Wächterfeder wird die lokale Brücke zwischen einem *Pillars of Eternity*-Spielstand und der Serin-Chronik. Dieser erste Baustein arbeitet ausschließlich lesend.

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

Einen gefundenen Spielstand inventarisieren:

```powershell
python tools/wachterfeder/wachterfeder.py snapshot `
  "$env:USERPROFILE\Saved Games\Pillars of Eternity\DEIN_SAVE.savegame"
```

Das Werkzeug:

- berechnet die SHA-256-Prüfsumme,
- legt unter `.wachterfeder/cache/` eine schreibgeschützte Arbeitskopie ab,
- prüft, ob das Save als ZIP geöffnet werden kann,
- inventarisiert die enthaltenen Dateien,
- markiert unter anderem `MobileObjects.save`,
- erzeugt daneben ein JSON-Snapshot.

Der Originalspielstand wird weder geöffnet zum Schreiben noch ersetzt.

## Tests

```powershell
python -m unittest discover -s tools/wachterfeder/tests -v
```

## Nächster Schritt

Sobald ein echter Spielstand vorliegt, prüfen wir:

1. welches Kompressionsverfahren die konkrete Spielversion verwendet,
2. welche Dateien tatsächlich enthalten sind,
3. ob `MobileObjects.save` direkt mit dem bekannten SharpSerializer-Ansatz gelesen werden kann,
4. wo gespielte Dialogknoten, Weltzeit und globale Questvariablen gespeichert werden.
