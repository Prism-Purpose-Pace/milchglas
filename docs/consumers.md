# Konsumenten einrichten: mailbox.org und meetergo

Diese Seite beschreibt, wie die beiden Konsumenten den Milchglas-Feed lesen (Spec OR10,
D-4), und hält fest, welche Gates bestanden sind (AC-0.1, AC-0.2, AC-0.4; MAN-1). Sie ist
bewusst auf Deutsch (Spec Q-7). Hostnamen, Feed-Adressen, Tokens, Kontonamen,
Kalendernamen und Details eines Betreiberkontos gehören nicht hierher; das ausführliche
Protokoll führt der Maintainer privat.

## Feed-Adresse weitergeben

Die Feed-Adresse lautet `https://<host>/f/<token>.ics`. Das Token gibt `init` oder
`rotate-token` einmal auf dem Server aus; auf dem Server liegt danach nur sein SHA-256
(Spec D-14).

- Die Adresse ist das Geheimnis. Kopiere sie direkt aus dem Server-Terminal in den
  Dialog des Konsumenten.
- Nie per Mail, Chat oder Kurzlink verschicken und nicht in einem Browser-Tab öffnen:
  Link-Vorschauen, Mail-Scanner, Verlauf und Erweiterungen speichern sie (Threat Model
  T-35).
- Wer die Adresse kennt, sieht nur anonyme Blöcke; nach einer Rotation (`rotate-token`)
  wird die neue Adresse in beiden Konsumenten eingetragen.

## mailbox.org (Abo eines iCal-Feeds)

Einmalig im Web-Client:

1. Pfeil neben *Neuer Termin* → *Von URL (iCal) importieren* → *iCal-Feed abonnieren*.
2. Feed-Adresse einfügen und bestätigen.
3. Der Kalender erscheint unter *Meine Kalender*. Er ist nur lesbar.

mailbox.org beachtet das `REFRESH-INTERVAL` des Feeds (`PT15M`), nicht den
7-Tage-Standard von Open-Xchange.

## meetergo (ICS-Kalender)

Einmalig pro Profil, nicht pro Termintyp: meetergo verbindet einen ICS-Kalender im
Profil (Eintrag *Proton/ICS Calendar*), und er gilt für alle Termintypen dieses Profils
(meetergo-Hilfe „Connecting ICS calendars“, Stand 2026-09-16).

- meetergo verlangt eine öffentlich erreichbare HTTPS-Adresse ohne Anmeldung.
- Jeder Termin im ICS-Kalender blockiert, auch ganztägige; ausgenommen sind nur Termine
  mit Status frei und abgesagte (meetergo-Hilfe, Stand 2026-07-28). Milchglas schreibt
  jeden Block als `TRANSP:OPAQUE` und `STATUS:CONFIRMED`.
- Buchungsfenster: Jeder Termintyp darf höchstens `window_days` - 3 Kalendertage im
  Voraus buchbar sein (Standard 33 - 3 = 30). Ein Fenster in Werktagen ist in
  Kalendertagen länger; ein unbegrenztes Fenster ist nicht zulässig. Ein neuer
  Termintyp startet mit 30 Kalendertagen. Wer ein Fenster verlängert, erhöht vorher
  `window_days` in `config.json` (Spec L2, Q-2).

## Gate-Ergebnisse (MAN-1)

Geprüft mit einem synthetischen Testfeed, der den ausgelieferten Header trägt (ohne
`METHOD`, `REFRESH-INTERVAL` und `X-PUBLISHED-TTL` `PT15M`), mit zwei UTC-Blöcken und
einem Ganztagsblock (`VALUE=DATE`). Eine zweite Version verschob einen Block, mit neuer
UID wie bei einem echten Refresh.

### AC-0.1 mailbox.org: bestanden

| Beobachtung | Ergebnis |
|---|---|
| Erscheint unter *Meine Kalender* | ja |
| Alle Blöcke sichtbar | ja, mit `TRANSP:OPAQUE` und Status belegt |
| Darstellung des Ganztagsblocks | als ganztägiger Termin, Status belegt |
| Header ohne `METHOD` angenommen | ja |
| Änderung sichtbar | innerhalb der 30 Minuten von AC-11 |
| `PT15M` beachtet | ja, nicht der 7-Tage-Standard (V-1 bestanden) |
| UID-Wechsel | alter Block entfernt, neuer Block da, kein Duplikat |

### AC-0.2 meetergo: bestanden

| Beobachtung | Ergebnis |
|---|---|
| Zeitblock nicht buchbar | ja |
| Ganztägiger Block: Tag ohne buchbaren Slot | ja |
| Feed ohne Anmeldung als belegt gewertet | ja (V-5 bestanden) |
| Header ohne `METHOD` und `VALUE=DATE` angenommen | ja |
| Änderung wirksam | innerhalb der 30 Minuten von AC-11 |
| Geltung | profilweit, für alle Termintypen |

### AC-0.4 meetergo-Buchungsfenster: bestanden

| Beobachtung | Ergebnis |
|---|---|
| Jedes Buchungsfenster ≤ `window_days` - 3 Kalendertage | ja |
| `window_days` | bleibt 33 |

## Noch offen

- Ob mailbox.org für ein Feed-Abo Zugangsdaten annimmt, ist nicht getestet und wird nicht
  gebraucht: die Adresse selbst ist das Geheimnis (Spec W5).
- Verhalten beider Konsumenten, wenn der Feed nicht erreichbar ist: V-9, MAN-14.
- Keine Duplikate über zwei Refresh-Zyklen mit dem echten Feed: MAN-3.
