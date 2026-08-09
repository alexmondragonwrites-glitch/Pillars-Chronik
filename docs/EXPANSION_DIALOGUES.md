# Dialoge aus Grundspiel und Erweiterungen

Die Wächterfeder-Oberfläche durchsucht die lokale *Pillars of Eternity*-Installation automatisch nach dem Grundspielordner `data` und allen vorhandenen Geschwisterordnern mit dem Präfix `data_expansion`.

Für jedes gefundene Paket werden gemeinsam gelesen:

```text
<Paket>\conversations
<Paket>\localized\de\text\conversations
```

Eine typische Installation enthält damit:

```text
PillarsOfEternity_Data\data
PillarsOfEternity_Data\data_expansion1
PillarsOfEternity_Data\data_expansion2
PillarsOfEternity_Data\data_expansion4
```

In der App genügt die Auswahl des Spielordners oder von `PillarsOfEternity_Data`. Erweiterungsordner müssen nicht einzeln konfiguriert werden. Dialoggraph und Stringtable werden stets aus demselben Datenpaket bevorzugt; bei gleichnamigen Dateien helfen Paketpfad und markierte Node-IDs bei der eindeutigen Zuordnung.

Alle Spielressourcen bleiben lokal und werden nicht ins Repository kopiert.
