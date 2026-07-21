# Dialogarchiv-Prüfung

Der Workflow `.github/workflows/dialog-archive-audit.yml` prüft ein vorübergehend bereitgestelltes `Dialog.7z` innerhalb von GitHub Actions.

Er erzeugt ausschließlich ein Metadaten-Manifest mit:

- Prüfsumme und Dateigröße,
- Anzahl der Dialoggraphen und Stringtables,
- Anzahl deutscher und englischer Lokalisierungen,
- Zuordnung der 20 in Serins Testsave referenzierten Dialogdateien,
- Vorhandensein der zugehörigen deutschen und englischen Stringtables.

Originaldialoge werden nicht als Artefakt hochgeladen und nicht in generierte Repository-Dateien geschrieben. Das Manifest wird als kurzlebiges Actions-Artefakt gespeichert.
