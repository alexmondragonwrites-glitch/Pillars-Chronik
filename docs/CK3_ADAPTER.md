# Wächterfeder für Crusader Kings III

Der CK3-Adapter ist das vierte Wächterfeder-Modul. Sein Schwerpunkt ist nicht nur Chronik, sondern eine kompakte politische Analyse rund um den aktuellen Herrscher: Familie, Dynastie, direkte Vasallen, Titel, Kriege, wichtige Ereignisse und später direkte Nachbarreiche.

## Status

**MVP vorbereitet und gegen einen echten CK3-Save im Format 1.19.0.4 strukturell validiert.**

Der Adapter arbeitet ausschließlich lesend. Originalspielstände werden nicht verändert. Der getestete Save verwendet CK3s Save-Envelope mit `meta` und `gamestate`; der große Weltzustand bleibt außerhalb der Wächterfeder-Ausgaben.

## Zielbild

Die Wächterfeder beobachtet CK3 in drei Ringen:

1. **Ring 1:** Spielerherrscher, Ehepartner, Kinder, Eltern, Geschwister, Erbe, eigene Titel und mächtige Vasallen.
2. **Ring 2:** direkte Vasallen, laufende Kriege und später direkte Nachbarreiche.
3. **Ring 3:** politisch relevante externe Charaktere, die durch Ansprüche, Bündnisse, Kriege oder Erbfolgen wichtig werden.

Der Snapshot soll deshalb nie die komplette CK3-Welt duplizieren.

## Speicherorte

Unter Windows prüft Wächterfeder unter anderem:

```text
%USERPROFILE%\Documents\Paradox Interactive\Crusader Kings III\save games
```

OneDrive-Dokumente werden ebenfalls berücksichtigt. Vorhandene Steam-Cloud-Ordner für CK3 werden zusätzlich sondiert.

## Lokale Ausgaben

```text
.wachterfeder/ck3/ck3.snapshot.json
.wachterfeder/ck3/ck3.delta.json
.wachterfeder/ck3/history/*.delta.json
```

`ck3.snapshot.json` ist nur der aktuelle Vergleichsstand. Historisch gespeichert werden ausschließlich kompakte Deltas.

## Zwei Analysestufen

### 1. Envelope und Metadaten

Ohne weitere Werkzeuge kann Wächterfeder bereits `.ck3`-Saves finden, den neuesten Save bestimmen, SHA-256 bilden, das Save-Envelope prüfen, ZIP/CRC validieren, `meta` und `gamestate` erkennen und sichere Metadaten als Fallback lesen.

### 2. Tiefe Weltanalyse mit Rakaly

CK3 verwendet für große Teile des Saves ein binäres Jomini-Format. Für die tiefe Analyse nutzt Wächterfeder optional **Rakaly CLI** als Decoder. Rakaly kann CK3-Saves lesen und in JSON überführen. Die temporäre Vollkonvertierung wird anschließend verworfen; dauerhaft speichert Wächterfeder nur den normalisierten Ausschnitt rund um den Spieler.

Rakaly wird gesucht über einen im CK3-Reiter ausgewählten Pfad, `WACHTERFEDER_RAKALY`, `tools/wachterfeder/bin/rakaly.exe` oder den normalen `PATH`. Die Drittanbieter-Binärdatei wird nicht ins Repository eingecheckt.

## Normalisierter CK3-Zustand

Die erste tiefe Stufe extrahiert unter anderem Spielercharakter und Basisdaten, Traits und Skills, Dynastiehaus, Kultur und Glaube, Gold/Stress/Gesundheit/Prestige/Frömmigkeit/Furcht soweit vorhanden, Ehepartner, Kinder, Eltern und Geschwister, eigene Titel und Primärtitel, direkte Vasallen einschließlich Machtindikatoren, laufende Kriege mit Beteiligung des Spielers sowie persistente Event-/Story-/Memory-Signale.

Direkte Karten-Nachbarn folgen in Stufe 2, weil dafür die lokalen CK3-Kartendaten die robustere Quelle sind als ein riesiger Welt-Snapshot.

## Event-Analyse

Events werden bewusst in drei Vertrauensstufen getrennt.

### Gespeichert / belegt

Der Save enthält persistente Informationen wie Character Memories, Stories, wichtige Aktionen, Entscheidungen und verschiedene Trigger-/Event-Zustände. Solche Daten können als Save-Beleg verwendet werden.

Wichtig: Eine rohe Event-ID im Save bedeutet **nicht automatisch**, dass dieses Event dem Spieler angezeigt wurde. Sie kann auch zu Queue, Cooldown oder globalem Zustand gehören.

### Aus Delta rekonstruiert

Zwei aufeinanderfolgende Saves erlauben semantische Timeline-Kandidaten, zum Beispiel Kind neu in der Familie, Familienmitglied entfernt, Titel gewonnen oder verloren, Vasall hinzugekommen oder weggefallen sowie neue persistente Character Memories. Weitere Fälle wie Hochzeit, Nachfolge, Krieg, Bündnis und Fraktionsänderungen werden ergänzt, sobald die Feldkartierung real validiert ist.

Diese Einträge werden als `save_diff` oder `persistent_memory` gekennzeichnet und nicht künstlich als exakte Eventoption ausgegeben.

### Exakt geloggt

Für ein wirklich lückenloses Protokoll wie „Event X erschien und Option B wurde gewählt“ ist eine spätere Runtime-Schicht vorgesehen. CK3-Modding bietet `on_action`-Hooks und Log-Ausgaben, womit viele Systemereignisse beobachtet werden können, ohne Vanilla-Events zu überschreiben. Nicht jedes beliebige Popup besitzt jedoch automatisch einen universellen sicheren Hook.

Daher gilt in der Chronik:

- **exakt:** Event/Option eindeutig durch Save oder Runtime-Log belegt,
- **belegt:** persistenter Zustand oder Memory,
- **rekonstruiert:** eindeutige/hochplausible Änderung aus zwei Saves,
- **unbekannt:** Daten reichen nicht für eine sichere Aussage.

## CLI

Speicherorte prüfen:

```powershell
python tools/wachterfeder/ck3.py paths
```

Save analysieren:

```powershell
python tools/wachterfeder/ck3.py inspect `
  --save "$env:USERPROFILE\Documents\Paradox Interactive\Crusader Kings III\save games\DEIN_SAVE.ck3"
```

Mit explizitem Rakaly-Pfad:

```powershell
python tools/wachterfeder/ck3.py inspect `
  --save "C:\...\DEIN_SAVE.ck3" `
  --rakaly "C:\Tools\rakaly.exe"
```

## Nächste Schritte

1. Rakaly an einem echten Nutzer-Save gegen die normalisierten Felder validieren.
2. Familie, Vasallen, Titel und laufende Kriege an realen IDs verifizieren.
3. Lokale CK3-Kartendaten anbinden und echte direkte Nachbarreiche bestimmen.
4. Risiko-/Nachfolgeanalyse auf den normalisierten Zustand setzen.
5. Runtime-Logger für beobachtbare Event-/on_action-Signale als optionale Stufe ergänzen.
