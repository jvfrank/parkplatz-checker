"""
Prüft das Kundenportal von Parken Mannheim auf freie Dauerparkplätze (Objekt "Klinikum")
und schickt bei einem Treffer oder einer Änderung eine Push-Nachricht über ntfy.sh.
 
Umgebungsvariablen:
  NTFY_TOPIC   Pflicht. Dein geheimer ntfy-Themenname, z.B. "julius-parken-x7k2q9"
  OBJEKT       Optional. Standard: "Klinikum"
  MONATE_VORAUS Optional. Wie viele Monate ab jetzt durchsucht werden (Standard: 3)
"""
import hashlib
import json
import os
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path
 
from playwright.sync_api import sync_playwright
 
URL = "https://kundenportal.parken-mannheim.de/iPCP/contract/create?t=2"
OBJEKT = os.environ.get("OBJEKT", "Klinikum")
# Das Portal erlaubt nur 1 Monat Vorlauf -> aktueller + nächster Monat reichen
MONATE_VORAUS = min(int(os.environ.get("MONATE_VORAUS", "2")), 2)
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
STATE_FILE = Path("state/last_result.json")
SHOT_DIR = Path("screenshots")
 
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]
 
# Wörter, die auf "nichts frei" hindeuten
NEGATIV = re.compile(r"ausgebucht|keine?\s+(freien?|verfügbaren?)|kein\s+parkplatz|nicht\s+verfügbar|"
                     r"keine\s+ergebnisse|keine\s+tarife|warteliste", re.I)
# Wörter, die auf ein buchbares Angebot hindeuten
POSITIV = re.compile(r"€|eur\b|vertrag\s+(abschließen|erstellen)|jetzt\s+buchen|auswählen|weiter", re.I)
 
 
def notify(title: str, msg: str, prio: str = "high") -> None:
    print(f"[NOTIFY] {title}: {msg}")
    if not NTFY_TOPIC:
        print("NTFY_TOPIC fehlt – keine Push-Nachricht gesendet.")
        return
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=msg.encode("utf-8"),
        headers={"Title": title.encode("utf-8"), "Priority": prio,
                 "Tags": "car,parking", "Click": URL},
    )
    urllib.request.urlopen(req, timeout=20)
 
 
def select_containing(page, option_text: str):
    """Findet das <select>, das eine Option mit diesem Text enthält."""
    for sel in page.locator("select").all():
        texts = [t.strip() for t in sel.locator("option").all_inner_texts()]
        if any(option_text.lower() == t.lower() for t in texts):
            return sel, texts
    return None, []
 
 
def pf_select(page, sel, label: str) -> None:
    """Wählt eine Option in einem PrimeFaces-Menü (verstecktes <select> + sichtbares Widget)."""
    sel_id = sel.get_attribute("id") or ""
    base = sel_id[:-6] if sel_id.endswith("_input") else sel_id
    esc = base.replace(":", "\\:")
    widget = page.locator(f"#{esc}")
    if base and widget.count() and widget.first.is_visible():
        widget.first.click()
        panel = page.locator(f"#{esc}_panel")
        panel.wait_for(state="visible", timeout=10000)
        item = panel.locator(f"li[data-label=\"{label}\"]")
        if not item.count():
            item = panel.locator("li", has_text=label)
        item.first.click()
    else:
        sel.select_option(label=label, force=True)
    page.wait_for_load_state("networkidle", timeout=30000)
    page.wait_for_timeout(800)
 
 
def click_search(page) -> None:
    """Klickt den sichtbaren Such-Knopf (der Text existiert mehrfach für Handy/Desktop)."""
    candidates = [
        page.get_by_role("button", name=re.compile(r"suchen", re.I)),
        page.locator("button, input[type=submit], a.ui-button").filter(has_text=re.compile(r"suchen", re.I)),
        page.get_by_text("Parkplatz suchen"),
        page.get_by_text("Suchen", exact=True),
    ]
    for loc in candidates:
        for i in range(loc.count()):
            el = loc.nth(i)
            if el.is_visible():
                el.click()
                return
    raise RuntimeError("Sichtbaren 'Parkplatz suchen'-Knopf nicht gefunden.")
 
 
def pick_month_label(mopts: list[str], month: int) -> str:
    for cand in (MONATE[month - 1], f"{month:02d}", str(month)):
        if cand in mopts:
            return cand
    return mopts[month] if len(mopts) > month else mopts[-1]
 
 
def lines(text: str) -> list[str]:
    return [l.strip() for l in text.splitlines() if l.strip()]
 
 
def search_month(page, year: int, month: int) -> str:
    page.goto(URL, wait_until="networkidle", timeout=60000)
 
    # Cookie-Banner wegklicken, falls vorhanden
    for label in ["Speichern", "Zustimmen", "Alle akzeptieren"]:
        btn = page.get_by_role("button", name=label)
        if btn.count() and btn.first.is_visible():
            try:
                btn.first.click(timeout=3000)
                break
            except Exception:
                pass
 
    before = set(lines(page.inner_text("body")))
 
    objekt_sel, opts = select_containing(page, OBJEKT)
    if objekt_sel is None:
        raise RuntimeError(f"Objekt-Dropdown mit '{OBJEKT}' nicht gefunden.")
    # Erst Datum, dann Objekt (Objektwahl kann Tarife nachladen)
    monat_sel, mopts = select_containing(page, "«Monat»")
    if monat_sel is not None:
        pf_select(page, monat_sel, pick_month_label(mopts, month))
 
    jahr_sel, _ = select_containing(page, "«Jahr»")
    if jahr_sel is not None:
        pf_select(page, jahr_sel, str(year))
 
    objekt_sel, opts = select_containing(page, OBJEKT)
    pf_select(page, objekt_sel, next(o for o in opts if o.lower() == OBJEKT.lower()))
 
    click_search(page)
    page.wait_for_load_state("networkidle", timeout=60000)
    page.wait_for_timeout(3000)  # "Tarife werden abgefragt…" abwarten
 
    SHOT_DIR.mkdir(exist_ok=True)
    page.screenshot(path=str(SHOT_DIR / f"{year}-{month:02d}.png"), full_page=True)
 
    after = lines(page.inner_text("body"))
    neu = [l for l in after if l not in before and "Tarife werden abgefragt" not in l]
    return "\n".join(neu)
 
 
def main() -> int:
    today = date.today()
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(locale="de-DE")
        for i in range(MONATE_VORAUS):
            m = (today.month - 1 + i) % 12 + 1
            y = today.year + (today.month - 1 + i) // 12
            key = f"{y}-{m:02d}"
            try:
                results[key] = search_month(page, y, m)
            except Exception as e:
                results[key] = f"FEHLER: {e}"
            print(f"--- {key} ---\n{results[key] or '(kein neuer Text)'}\n")
        browser.close()
 
    old = {}
    if STATE_FILE.exists():
        old = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    first_run = not old
 
    treffer, geaendert = [], []
    for key, txt in results.items():
        if txt.startswith("FEHLER"):
            continue
        # Frei = Ergebnis wurde angezeigt, aber OHNE "Kein Parkplatz mehr ... verfügbar"
        if txt.strip() and not NEGATIV.search(txt):
            treffer.append(key)
        h = hashlib.sha256(txt.encode()).hexdigest()
        if old.get(key, {}).get("hash") not in (None, h):
            geaendert.append(key)
 
    if treffer:
        notify(f"🅿️ Parkplatz {OBJEKT} evtl. frei!",
               f"Angebot gefunden für: {', '.join(treffer)}. Schnell ins Portal!")
    elif geaendert:
        print(f"(Anzeige geändert für {', '.join(geaendert)}, aber weiterhin nichts frei – keine Nachricht)")
    elif first_run and len(fehler_vorab := [k for k, t in results.items() if t.startswith("FEHLER")]) < len(results):
        notify("Parkplatz-Checker läuft ✅",
               "Erster Durchlauf ok. Du bekommst Bescheid, sobald sich etwas tut.", prio="low")
 
    fehler = [k for k, t in results.items() if t.startswith("FEHLER")]
    if fehler and len(fehler) == len(results):
        notify("Parkplatz-Checker: Fehler", results[fehler[0]][:300], prio="default")
 
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(
        {k: {"hash": hashlib.sha256(t.encode()).hexdigest(), "text": t} for k, t in results.items()},
        ensure_ascii=False, indent=2), encoding="utf-8")
    return 0
 
 
if __name__ == "__main__":
    sys.exit(main())
 
