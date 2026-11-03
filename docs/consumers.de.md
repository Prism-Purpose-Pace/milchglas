# Consumer-Einrichtung: mailbox.org und meetergo

Deutsche Fassung von [consumers.md](consumers.md). Weichen die beiden voneinander ab, gilt
die englische Seite (D-10). Diese Seite beschreibt, wie die beiden Consumer den
Milchglas-Feed lesen (Spec OR10, D-4), und hält fest, welche Gates bestanden sind (AC-0.1,
AC-0.2, AC-0.4; MAN-1). Hostnamen, Feed-URLs, Tokens, Kontonamen, Kalendernamen und
Details zum Konto eines Betreibers gehören nicht hierher; der Maintainer führt die
ausführliche Aufzeichnung privat.

## Einrichtungsschritte

Jeder Schritt sagt, was zu tun ist, wo, wieso und wie. Menüpunkte stehen so da, wie die
deutschen Weboberflächen sie zeigen.

### Schritt 1: Feed-URL erzeugen

- **WAS:** Token und damit die Feed-URL `https://<host>/f/<token>.ics` erzeugen.
- **WO:** auf dem eigenen Rechner, nie im Web-Terminal der Plattform, denn das ist ein
  Browser-Tab (Spec NFR-O1, Threat Model T-62).
- **WIESO:** Die URL ist das Geheimnis. `init` oder `rotate-token` gibt den Token einmal aus;
  der Server hält nur seinen SHA-256 (Spec D-14). Wer die URL kennt, sieht nur anonyme
  Blöcke.
- **WIE:** `init` ausführen (oder `rotate-token` für eine neue URL). Im Dialog jedes
  Consumers `https://<host>/f/` tippen, den ausgegebenen Token einfügen und `.ics` anhängen.
  Die URL nie per Mail, Chat oder Linkkürzer verschicken und nie in einem Browser-Tab
  öffnen: Linkvorschauen, Mailscanner, Verlauf und Erweiterungen speichern sie (Threat
  Model T-35). Nach einer Rotation die neue URL in beiden Consumern eintragen.

### Schritt 2: In mailbox.org abonnieren

- **WAS:** den Feed einmal als iCal-Feed-Kalender abonnieren.
- **WO:** Webclient von mailbox.org, Kalender.
- **WIESO:** mailbox.org zeigt die belegte Zeit dann als anonyme Blöcke. Es beachtet das
  `REFRESH-INTERVAL` des Feeds (gesetzt über `ttl_seconds`), nicht den 7-Tage-Standard von
  Open-Xchange.
- **WIE:**
  1. Pfeil neben *Neuer Termin* → *Von URL (iCal) importieren* → *iCal-Feed abonnieren*.
  2. Feed-URL einfügen und bestätigen.
  3. Der Kalender erscheint unter *Meine Kalender*. Er ist schreibgeschützt.

### Schritt 3: ICS-Kalender in meetergo verbinden

- **WAS:** den Feed einmal pro Profil verbinden, nicht pro Terminart; er gilt für jede
  Terminart dieses Profils (meetergo-Hilfe „Connecting ICS calendars“, Stand 2026-09-16).
- **WO:** meetergo-Profil, Eintrag *Proton/ICS Calendar*.
- **WIESO:** meetergo bietet belegte Zeit dann nicht mehr an. Es braucht eine öffentlich
  erreichbare HTTPS-URL ohne Anmeldung. Jeder Termin im ICS-Kalender blockiert, ganztägige
  eingeschlossen; nur als frei markierte und abgesagte nicht (meetergo-Hilfe, Stand
  2026-07-28). Milchglas schreibt jeden Block als `TRANSP:OPAQUE` und `STATUS:CONFIRMED`.
- **WIE:** ICS-Kalender mit der Feed-URL hinzufügen und speichern.

### Schritt 4: Buchungsfenster in meetergo begrenzen

- **WAS:** keine Terminart darf weiter als `window_days` - 3 Kalendertage im Voraus buchbar
  sein (Spec Q-2).
- **WO:** meetergo, Einstellungen jeder Terminart.
- **WIESO:** Blöcke gibt es nur bis heute + `window_days` (Spec L2); spätere Tage wären frei.
- **WIE:** das Buchungsfenster jeder Terminart prüfen. Ein Fenster in Werktagen ist in
  Kalendertagen länger; ein unbegrenztes Fenster ist nicht erlaubt. Eine neue Terminart
  beginnt mit 30 Kalendertagen. Vor dem Verlängern eines Fensters `window_days` in
  `config.json` erhöhen.

## Gate-Ergebnisse (MAN-1)

Geprüft mit einem synthetischen Testfeed mit dem ausgelieferten Header (kein `METHOD`,
`REFRESH-INTERVAL` und `X-PUBLISHED-TTL` `PT15M`), mit zwei UTC-Blöcken und einem
ganztägigen Block (`VALUE=DATE`). Eine zweite Version verschob einen Block, mit neuer UID wie
bei einem echten Refresh.

MAN-2, der Ausweg für einen Consumer, der den Header ohne `METHOD` oder den ganztägigen
Block ablehnt, war nicht nötig: Beide Consumer akzeptierten beides.

### AC-0.1 mailbox.org: bestanden

| Beobachtung | Ergebnis |
|---|---|
| Erscheint unter *Meine Kalender* | ja |
| Alle Blöcke sichtbar | ja, mit `TRANSP:OPAQUE` und Status belegt |
| Darstellung des ganztägigen Blocks | als ganztägiger Termin, Status belegt |
| Header ohne `METHOD` akzeptiert | ja |
| Änderung sichtbar | innerhalb der 30 Minuten von AC-11 |
| `PT15M` beachtet | ja, nicht der 7-Tage-Standard (V-1 bestanden) |
| UID-Wechsel | alter Block entfernt, neuer Block da, kein Duplikat |

### AC-0.2 meetergo: bestanden

| Beobachtung | Ergebnis |
|---|---|
| Zeitblock nicht buchbar | ja |
| Ganztägiger Block: Tag ohne buchbaren Slot | ja |
| Feed ohne Anmeldung als belegt behandelt | ja (V-5 bestanden) |
| Header ohne `METHOD` und `VALUE=DATE` akzeptiert | ja |
| Änderung wirksam | innerhalb der 30 Minuten von AC-11 |
| Geltungsbereich | profilweit, jede Terminart |

### AC-0.4 meetergo-Buchungsfenster: bestanden

| Beobachtung | Ergebnis |
|---|---|
| Jedes Buchungsfenster ≤ `window_days` - 3 Kalendertage | ja |
| `window_days` | bleibt 33 |

## Noch offen

- Ob mailbox.org Zugangsdaten für ein Feed-Abo annimmt, ist ungetestet und nicht nötig: Die
  URL selbst ist das Geheimnis (Spec W5).
- Wie sich beide Consumer verhalten, solange der Feed nicht erreichbar ist: V-9, MAN-14.
- Keine Duplikate über zwei Refresh-Zyklen mit dem echten Feed: MAN-3.
