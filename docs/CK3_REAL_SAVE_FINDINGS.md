# CK3 – Erkenntnisse aus realem Save-Test

Stand: 11. August 2026

## Verifizierter Teststand

Ein echter CK3-Ironman-Save der Version 1.19.0.5 wurde mit Rakaly 0.8.19 tief analysiert. Die Wächterfeder konnte dabei unter anderem zuverlässig auflösen:

- Spielercharakter und Spieltag,
- Ehepartner, Kinder, Eltern und Geschwister,
- eigene Titel und Primärtitel,
- direkte Vasallen,
- Lehnsherr und dessen Titel,
- aktuelle Nachfolgelinie,
- aktive Kriege mit Casus Belli und Teilnehmern,
- mindestens einen persistenten Character-Memory-Datensatz.

## Real-Save-Fund: Memory-Zeitfelder

Ein persistenter `war_won`-Memory-Datensatz enthielt ein `end_date`, das deutlich nach dem aktuellen Spieltag lag. Die vorhandenen offiziellen Paradox-Moddinginformationen belegen, dass Events persistenten, zeitlich begrenzten Zustand und Cooldowns erzeugen können. Sie belegen jedoch nicht, dass das `end_date` eines Character-Memory-Datensatzes das Datum des zugrunde liegenden historischen Ereignisses ist.

Daher gilt ab der Refined-Stufe:

- `date` bzw. `start_date` können als persistente Datumswerte des Datensatzes ausgegeben werden;
- `end_date` bleibt als `raw_end_date` erhalten;
- ein zukünftiges `end_date` wird markiert;
- `end_date` wird niemals automatisch als Ereignisdatum erzählt;
- fehlt ein belegtes Ereignisdatum, lautet der Status ausdrücklich: `im Save nicht eindeutig als Ereignisdatum belegt`.

Quelle für die konservative Persistenzannahme:
- Paradox CK3 Dev Diary #87 – Royal Modding: Events können automatische Cooldown-Flags mit zeitlicher Lebensdauer erzeugen.

## Real-Save-Fund: Lehnsherr und Kriegskontext

Der Save zeigte, dass die bereits vorhandenen Titel- und Casus-Belli-Daten reichen, um einen aktiven Krieg strategisch besser einzuordnen:

- Rolle des Spielers: Angreifer / Verteidiger / sonstiger Teilnehmer,
- Gegner-ID und aufgelöster Charaktername,
- ob der Gegner der eigene Lehnsherr ist,
- Casus-Belli-Typ,
- Anspruchsteller,
- Zieltitel,
- separat gespeicherte Teilnehmerverluste und Attrition.

Verluste und Attrition werden absichtlich nicht zu einer Gesamtzahl addiert, solange ihre exakte CK3-Semantik nicht belegt ist.

## Real-Save-Fund: Vasallen-Nachfolge

Bei direkten Vasallen kann das gespeicherte `succession`-Feld den Spieler enthalten. Wächterfeder hebt solche Fälle künftig als `inheritance_opportunities` hervor.

Wichtig: Dies ist nur die aktuell im Save beobachtete Nachfolgeposition. Sie wird nicht als garantierte spätere Erbschaft dargestellt, da Gesetze, Todesfälle, Geburten, Titelwechsel und andere Spielereignisse die Nachfolge verändern können.

## Real-Save-Fund: Vasallen-Watchlist

Der erste heuristische Entwurf hob einen abweichenden Glauben allein bereits auf `medium` an. Das ist für eine analytische Wächterfeder zu stark.

Ab der Refined-Stufe gilt:

- Macht-/Stärkewerte bestimmen die eigentliche Aufmerksamkeitsstufe;
- abweichender Glaube wird als `context_flag` ausgegeben;
- ein Glaubensunterschied allein macht einen Vasallen nicht automatisch riskanter.

Damit trennt die Ausgabe sauber zwischen beobachteter struktureller Macht und bloßem politisch-religiösem Kontext.

## Noch offen

Für die nächste Stufe werden lokale CK3-Spieldaten benötigt:

- geografisch echte Nachbarreiche,
- lesbare Traitnamen statt numerischer Save-IDs,
- lesbare Kultur- und Glaubensnamen,
- belastbare Fraktions- und Meinungsanalyse,
- spätere exakte Eventoptionen über einen optionalen Runtime-/Mod-Logger.
