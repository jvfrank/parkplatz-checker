# Parkplatz-Checker Klinikum (Parken Mannheim)

Prüft alle 15 Minuten das Kundenportal (Objekt „Klinikum“, die nächsten 3 Monate)
und schickt dir eine Push-Nachricht aufs Handy, wenn ein Angebot auftaucht
oder sich die Anzeige ändert. Läuft kostenlos auf GitHub – dein Rechner muss nicht an sein.

## Einrichtung (ca. 10 Minuten)

1. **ntfy-App** installieren (iOS/Android, kostenlos) → „+“ → Thema abonnieren,
   z.B. `julius-parken-x7k2q9` (zufällig wählen, jeder mit dem Namen kann mitlesen).
2. **GitHub-Konto** anlegen → neues **privates** Repository erstellen.
3. Die Dateien hochladen (`check_parking.py`, `README.md` und
   `.github/workflows/check.yml` – den Ordnerpfad genau so übernehmen).
4. Im Repo: **Settings → Secrets and variables → Actions → New repository secret**
   Name: `NTFY_TOPIC`, Wert: dein Themenname aus Schritt 1.
5. **Actions**-Tab → „Parkplatz-Check“ → **Run workflow**.
   Nach 1–2 Minuten kommt „Parkplatz-Checker läuft ✅“ aufs Handy.

## Kontrolle
Bei jedem Lauf werden Screenshots der Suchergebnisse gespeichert
(Actions → Lauf anklicken → „screenshots“). Schick mir nach dem ersten Lauf
gern den Screenshot bzw. das Log – dann passe ich die Erkennung genau an
den Text an, den das Portal bei „nichts frei“ anzeigt.

## Anpassen
- Takt: Zeile `cron` in `check.yml` (GitHub führt geplante Läufe oft mit Verzögerung aus).
- Anderes Objekt / mehr Monate: `OBJEKT` und `MONATE_VORAUS` in `check.yml`.
