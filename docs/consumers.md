# Konsumenten einrichten: mailbox.org und meetergo

Diese Seite beschreibt, wie die beiden Konsumenten den Milchglas-Feed lesen (Spec OR10,
D-4), und hält die Ergebnisse der Gates AC-0.1, AC-0.2 und AC-0.4 fest (MAN-1). Sie ist
bewusst auf Deutsch (Spec Q-7). Hostnamen, Feed-Adressen, Tokens und Kontonamen gehören
nicht hierher.

## Feed-Adresse weitergeben

Die Feed-Adresse lautet `https://<host>/f/<token>.ics`. Das Token gibt `init` oder
`rotate-token` einmal auf dem Server aus; auf dem Server liegt danach nur sein SHA-256
(Spec D-14).

- Die Adresse ist das Geheimnis. Kopiere sie direkt aus dem Server-Terminal in den
  Dialog des Konsumenten.
- Nie per Mail, Chat oder Kurzlink verschicken und nicht in einem Browser-Tab öffnen:
  Link-Vorschauen, Mail-Scanner, Verlauf und Erweiterungen speichern sie (Threat Model
  T-35).
- Wer die Adresse kennt, sieht nur anonyme Blöcke, aber die Rotation (`rotate-token`)
  ersetzt sie in beiden Konsumenten.

## mailbox.org (Abo eines iCal-Feeds)

Einmalig im Web-Client:

1. Pfeil neben *Neuer Termin* → *Von URL (iCal) importieren* → *iCal-Feed abonnieren*.
2. Feed-Adresse einfügen und bestätigen.
3. Der Kalender erscheint unter *Meine Kalender*. Er ist nur lesbar.

mailbox.org beachtet das `REFRESH-INTERVAL` des Feeds (`PT15M`), nicht den
7-Tage-Standard von Open-Xchange (Messung unten).

## meetergo (ICS-Kalender)

Einmalig pro Profil, nicht pro Termintyp: meetergo verbindet einen ICS-Kalender im
Profil (Eintrag *Proton/ICS Calendar*), und er gilt für alle Termintypen dieses Profils
(meetergo-Hilfe „Connecting ICS calendars“, Stand 2026-09-16; im Gate bestätigt).

- meetergo verlangt eine öffentlich erreichbare HTTPS-Adresse ohne Anmeldung.
- Jeder Termin im ICS-Kalender blockiert, auch ganztägige; ausgenommen sind nur Termine
  mit Status frei und abgesagte (meetergo-Hilfe, Stand 2026-07-28). Milchglas schreibt
  jeden Block als `TRANSP:OPAQUE` und `STATUS:CONFIRMED`.
- Buchungsfenster: Jeder Termintyp darf höchstens `window_days` - 3 Kalendertage im
  Voraus buchbar sein (Standard 33 - 3 = 30). Ein Fenster in Werktagen ist in
  Kalendertagen länger. Ein neuer Termintyp startet mit 30 Kalendertagen; ein Fenster
  „Indefinitely“ ist nicht zulässig. Wer ein Fenster verlängert, erhöht vorher
  `window_days` in `config.json` (Spec L2, Q-2).

## Gate-Ergebnisse (MAN-1)

Testfeed: der Header, den der Code ausliefert (ohne `METHOD`, `REFRESH-INTERVAL` und
`X-PUBLISHED-TTL` `PT15M`), erzeugt mit `milchglas.core.emit` von Version 0.3.1. Drei
synthetische Blöcke „Blocker Privat“: Di 2026-11-10 09:00–10:00Z, Mi 2026-11-11
13:00–14:30Z, Do 2026-11-12 ganztägig (`VALUE=DATE`). Version 2 verschiebt den
Dienstagsblock auf 10:00–11:00Z, mit neuer UID wie bei einem echten Refresh. Der Feed lag
auf einer öffentlichen HTTPS-Adresse mit `content-type: text/calendar` und einem
CDN-Cache von höchstens 10 Minuten (`max-age=600`). Die Testkalender sind in beiden
Konsumenten wieder entfernt.

### AC-0.1 mailbox.org: bestanden (2026-11-03)

| Beobachtung | Ergebnis |
|---|---|
| Abo angelegt | 2026-11-02, etwa 19:55 UTC |
| Erscheint unter *Meine Kalender* | ja |
| Drei Blöcke sichtbar | ja; der Export enthält die Original-UIDs und -Zeiten, `TRANSP:OPAQUE`, Status belegt |
| Darstellung des Ganztagsblocks | als ganztägiger Termin, Status belegt (Export: `VALUE=DATE`, `X-MICROSOFT-CDO-ALLDAYEVENT:TRUE`) |
| `DTSTAMP` | Open-Xchange ersetzt ihn durch die eigene Importzeit; sonst unverändert |
| Version 2 live | 2026-11-03 08:09:12 UTC |
| Version 2 in mailbox.org sichtbar | spätestens 08:28:58 UTC, also höchstens 20 Minuten danach (inklusive bis zu 10 Minuten CDN-Cache) |
| `PT15M` beachtet | ja; nicht der 7-Tage-Standard von Open-Xchange (V-1 bestanden) |
| UID-Wechsel | alter Block entfernt, neuer Block da, kein Duplikat (08:32 UTC) |
| Header ohne `METHOD` angenommen | ja |

### AC-0.2 meetergo: bestanden (2026-11-03)

| Beobachtung | Ergebnis |
|---|---|
| Geprüfter Termintyp | Termintyp I (der genutzte); der ICS-Kalender gilt profilweit, also auch für Termintyp II |
| Zeitblock Mi 13:00–14:30Z nicht buchbar | ja |
| Ganztägiger Do ohne buchbaren Slot | ja |
| Di-Block (Version 1) | lag außerhalb der Verfügbarkeit des Termintyps und belegt hier nichts |
| Zeit bis zum ersten Block nach dem Verbinden | nicht gemessen; beim ersten Blick auf die Buchungsseite (2026-11-03 07:55 UTC) blockiert |
| Version 2: Di 10:00Z nicht mehr buchbar | spätestens 08:28 UTC, also höchstens 19 Minuten nach Version 2 live (inklusive bis zu 10 Minuten CDN-Cache) |
| Feed ohne Anmeldung als belegt gewertet | ja (V-5 bestanden) |
| Header ohne `METHOD` und `VALUE=DATE` angenommen | ja |

Beide Weiterleitungszeiten liegen innerhalb der 30 Minuten von AC-11.

### AC-0.4 meetergo-Buchungsfenster: bestanden (2026-11-03)

| Termintyp | Buchungsfenster | ≤ 30 Kalendertage |
|---|---|---|
| I | 10 Kalendertage | ja |
| II | 14 Kalendertage | ja |

Weitere Termintypen gibt es nicht. `window_days` bleibt 33.

## Noch offen

- Ob mailbox.org für ein Feed-Abo Zugangsdaten annimmt, ist nicht getestet und wird nicht
  gebraucht: die Adresse selbst ist das Geheimnis (Spec W5).
- Verhalten beider Konsumenten, wenn der Feed nicht erreichbar ist: V-9, MAN-14.
- Keine Duplikate über zwei Refresh-Zyklen mit dem echten Feed: MAN-3.
