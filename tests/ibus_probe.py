#!/usr/bin/env python3
"""Probelauf gegen einen eigenen, abgeschotteten ibus-daemon.

Startet ibus-daemon unter einer privaten Adresse (dein normales IBus bleibt unberührt),
meldet die Engine an, tippt Tastenfolgen in einen simulierten Textpuffer und prüft das Ergebnis.

    python3 tests/ibus_probe.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="wortvorhersage-probe-"))
os.environ.update({
    "IBUS_ADDRESS": f"unix:abstract=wortvorhersage-probe-{os.getpid()}",
    "XDG_CONFIG_HOME": str(TMP / "config"),
    "XDG_DATA_HOME": str(TMP / "data"),
    "XDG_CACHE_HOME": str(TMP / "cache"),
    # Nur unsere Komponente laden, nicht die systemweiten aus /usr/share/ibus/component.
    "IBUS_COMPONENT_PATH": str(TMP / "component"),
})

import warnings  # noqa: E402

import gi  # noqa: E402

sys.path.insert(0, str(PROJEKT))
from wortvorhersage.einstellungen import ENGLISCH  # noqa: E402
from wortvorhersage.texte import text  # noqa: E402

gi.require_version("IBus", "1.0")
from gi.repository import Gio, GLib, IBus  # noqa: E402

M = IBus.ModifierType
# Kommt aus PyGObject beim Auspacken der Vorschlagstabelle im Client, nicht aus der Engine.
warnings.filterwarnings("ignore", message=".*g_object_is_floating.*")


class App:
    """Ein Textfeld, das sich verhält wie eine echte App hinter IBus."""

    def __init__(self, bus):
        self.text = ""
        self.leiste = []
        self.leiste_sichtbar = False
        self.cursor = None
        self.ic = bus.create_input_context("probe")
        self.ic.set_capabilities(IBus.Capabilite.FOCUS | IBus.Capabilite.PROPERTY | IBus.Capabilite.LOOKUP_TABLE
                                 | IBus.Capabilite.SURROUNDING_TEXT)
        self.ic.connect("commit-text", lambda _, t: self._einfuegen(t.get_text()))
        self.ic.connect("delete-surrounding-text", self._loeschen)
        self.ic.connect("forward-key-event", self._weitergeleitet)
        self.ic.connect("update-lookup-table", self._leiste)
        self.ic.connect("hide-lookup-table", lambda _: setattr(self, "leiste_sichtbar", False))
        self.menue = {}
        # Wie eine App, die den Text vor dem Cursor nicht (mehr) meldet: Löschen darüber verpufft.
        self.umgebung_eingefroren = False
        self.ic.connect("register-properties", self._menue)
        self.ic.connect("update-property", lambda _, e: self.menue.update({e.get_key(): e}))
        self.ic.focus_in()
        bus.set_global_engine("wortvorhersage")
        for _ in range(100):
            self.warten(0.05)
            engine = self.ic.get_engine()
            if engine and engine.get_name() == "wortvorhersage":
                break
        else:
            raise SystemExit("Engine startet nicht")

    def _einfuegen(self, text):
        self.text += text
        self._umgebung()

    def _loeschen(self, _, versatz, anzahl):
        if self.umgebung_eingefroren:
            return
        assert versatz == -anzahl, (versatz, anzahl)
        self.text = self.text[:versatz]
        self._umgebung()

    def _weitergeleitet(self, _, keyval, keycode, state):
        if not state & M.RELEASE_MASK:
            self._taste_in_app(keyval)

    def _leiste(self, _, tabelle, sichtbar):
        self.leiste = [tabelle.get_candidate(i).get_text() for i in range(tabelle.get_number_of_candidates())]
        self.leiste_sichtbar = sichtbar
        self.cursor = tabelle.get_cursor_pos() if tabelle.is_cursor_visible() else None

    def _menue(self, _, liste):
        self.menue = {}
        i = 0
        while (eintrag := liste.get(i)) is not None:
            self.menue[eintrag.get_key()] = eintrag
            i += 1

    def _umgebung(self):
        if self.umgebung_eingefroren:
            return
        self.ic.set_surrounding_text(IBus.Text.new_from_string(self.text), len(self.text), len(self.text))

    def _taste_in_app(self, keyval):
        if keyval == IBus.KEY_BackSpace:
            self.text = self.text[:-1]
        elif keyval in (IBus.KEY_Return, IBus.KEY_KP_Enter):
            self.text += "\n"
        else:
            zeichen = IBus.keyval_to_unicode(keyval)
            if zeichen.isprintable():
                self.text += zeichen
        self._umgebung()

    def taste(self, keyval, state=0):
        if not self.ic.process_key_event(keyval, 0, state):
            self._taste_in_app(keyval)
        self.ic.process_key_event(keyval, 0, state | M.RELEASE_MASK)
        self.warten(0.03)

    def tippen(self, text):
        for zeichen in text:
            self.taste(IBus.unicode_to_keyval(zeichen))

    def warten(self, sekunden):
        ende = time.monotonic() + sekunden
        kontext = GLib.MainContext.default()
        while time.monotonic() < ende:
            kontext.iteration(False)
            time.sleep(0.005)

    def neu(self):
        self.text = ""
        self.ic.reset()
        self._umgebung()
        self.warten(0.05)


def einstellen(**werte):
    """Setzt Einstellungen (deutsche Namen); ersetzt dabei auch die englische Schreibweise."""
    pfad = TMP / "config/wortvorhersage/einstellungen.ini"
    zeilen = pfad.read_text(encoding="utf-8").splitlines() if pfad.exists() else ["[wortvorhersage]"]
    for name, wert in werte.items():
        namen = (name, ENGLISCH.get(name, name))
        zeilen = [z for z in zeilen if z.split("=")[0].strip() not in namen] + [f"{name} = {wert}"]
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text("\n".join(zeilen) + "\n", encoding="utf-8")


FEHLER = []


def pruefe(beschreibung, ist, soll):
    ok = ist == soll
    print(f"{'ok ' if ok else 'FEHLER'}  {beschreibung}: {ist!r}" + ("" if ok else f" (erwartet {soll!r})"))
    if not ok:
        FEHLER.append(beschreibung)


def main():
    (TMP / "component").mkdir()
    starter = PROJEKT / "ibus-engine-wortvorhersage"
    xml = subprocess.run([starter, "--komponente", starter], capture_output=True, text=True, check=True).stdout
    (TMP / "component/wortvorhersage.xml").write_text(xml, encoding="utf-8")
    # Die Prüfungen tippen Deutsch, auch wenn die Systemsprache Englisch ist.
    einstellen(sprachen="de, en")
    daemon = subprocess.Popen(["ibus-daemon", "--address", os.environ["IBUS_ADDRESS"], "--panel=disable",
                               "--config=disable", "--emoji-extension=disable", "--cache=none"],
                              stderr=None if os.environ.get("PROBE_DEBUG") else subprocess.DEVNULL)
    try:
        # IBus.Bus() ist ein Singleton und verbindet sich nicht neu, also erst warten, bis der Daemon lauscht.
        for _ in range(200):
            try:
                Gio.DBusConnection.new_for_address_sync(
                    os.environ["IBUS_ADDRESS"], Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT, None, None).close_sync()
                break
            except GLib.Error:
                time.sleep(0.05)
        else:
            raise SystemExit("ibus-daemon startet nicht")
        IBus.init()
        bus = IBus.Bus()

        if not any(e.get_name() == "wortvorhersage" for e in bus.list_engines()):
            raise SystemExit("Komponente wurde nicht geladen")

        app = App(bus)

        # --- Windows-Modus
        app.tippen("Ich gla")
        pruefe("Text kommt direkt in der App an", app.text, "Ich gla")
        pruefe("Leiste sichtbar", app.leiste_sichtbar, True)
        pruefe("erster Vorschlag nach „ich“", app.leiste[:1], ["glaube"])
        pruefe("noch nichts ausgewählt", app.cursor, None)
        app.taste(IBus.KEY_Up)
        pruefe("Pfeil hoch wählt ersten Vorschlag", app.cursor, 0)
        pruefe("Pfeil hoch geht nicht an die App", app.text, "Ich gla")
        app.taste(IBus.KEY_Right)
        pruefe("Pfeil rechts", app.cursor, 1)
        app.taste(IBus.KEY_Left)
        app.taste(IBus.KEY_Return)
        pruefe("Enter übernimmt mit Leerzeichen", app.text, "Ich glaube ")
        pruefe("nächstes Wort wird vorgeschlagen", app.leiste_sichtbar and len(app.leiste) > 0, True)
        app.tippen(",")
        pruefe("Satzzeichen rückt an das Wort", app.text, "Ich glaube,")

        app.neu()
        app.tippen("das hau")
        pruefe("Vorschläge für „hau“", app.leiste[:1], ["Haus"])
        app.taste(IBus.KEY_Up)
        app.taste(IBus.KEY_space)
        pruefe("Großschreibung wird korrigiert", app.text, "das Haus ")

        app.neu()
        app.tippen("Hallo")
        app.taste(IBus.KEY_Up)
        app.taste(IBus.KEY_Escape)
        pruefe("Esc schließt Leiste", app.leiste_sichtbar, False)
        app.tippen(" Pizz")
        pruefe("Emoji als letzter Vorschlag", app.leiste[-1:], ["🍕"])
        app.taste(IBus.KEY_Up)
        for _ in range(5):
            app.taste(IBus.KEY_Right)
        app.taste(IBus.KEY_Return)
        pruefe("Emoji ersetzt das Wort", app.text, "Hallo 🍕 ")

        app.neu()
        app.tippen("Zeile hoc")
        app.taste(IBus.KEY_Down)
        pruefe("Pfeil runter ohne Auswahl geht an die App, Kontext weg", app.leiste_sichtbar, False)

        # --- App meldet veralteten Text: nicht darüber löschen („kuchKuchen“)
        app.neu()
        app.tippen("der ")
        app.umgebung_eingefroren = True
        app.tippen("kuch")
        app.taste(IBus.KEY_Up)
        app.taste(IBus.KEY_Return)
        app.warten(0.1)
        pruefe("veralteter Text vor dem Cursor → Rücktasten", app.text, "der Kuchen ")
        app.umgebung_eingefroren = False

        # --- App ohne umgebenden Text (z. B. Terminal): Korrektur über zurückgeschickte Rücktasten
        app.ic.set_capabilities(IBus.Capabilite.FOCUS | IBus.Capabilite.PROPERTY | IBus.Capabilite.LOOKUP_TABLE)
        app.ic.focus_out()
        app.ic.focus_in()
        app.warten(0.1)
        app.neu()
        app.tippen("ein hau")
        app.taste(IBus.KEY_Up)
        app.taste(IBus.KEY_Return)
        app.warten(0.1)
        pruefe("Korrektur per Rücktaste", app.text, "ein Haus ")
        app.ic.set_capabilities(IBus.Capabilite.FOCUS | IBus.Capabilite.PROPERTY | IBus.Capabilite.LOOKUP_TABLE
                                | IBus.Capabilite.SURROUNDING_TEXT)

        # --- Lernen und eigene Wörter
        app.neu()
        app.tippen("Quarkstrudel Quarkstrudel Quarkstrudel ")
        app.neu()
        app.tippen("Quar")
        pruefe("gelerntes Wort", app.leiste[:1], ["Quarkstrudel"])
        (TMP / "config/wortvorhersage/eigene_woerter.txt").write_text("Zwetschgendatschi\n", encoding="utf-8")
        app.ic.focus_out()
        app.ic.focus_in()
        app.warten(0.1)
        app.neu()
        app.tippen("zwe")
        pruefe("eigenes Wort", app.leiste[:1], ["Zwetschgendatschi"])

        # --- Tab-Modus
        einstellen(modus="tab")
        app.ic.focus_out()
        app.ic.focus_in()
        app.warten(0.1)
        app.neu()
        app.tippen("Ich gla")
        app.taste(IBus.KEY_Up)
        pruefe("Pfeil hoch tut im Tab-Modus nichts Besonderes", app.cursor, None)
        app.neu()
        app.tippen("Ich gla")
        app.taste(IBus.KEY_Tab)
        pruefe("Tab übernimmt", app.text, "Ich glaube ")
        app.neu()
        app.tippen("übe")
        zweiter = app.leiste[1]
        app.taste(IBus.KEY_2, M.MOD1_MASK)
        pruefe("Alt+2 übernimmt zweiten Vorschlag", app.text, zweiter + " ")

        # --- Menü in der Systemleiste
        pruefe("Menü ohne Untermenüs", any(e.get_prop_type() == IBus.PropType.MENU for e in app.menue.values()), False)
        pruefe("Tab-Modus im Menü markiert", app.menue["modus.tab"].get_state(), IBus.PropState.CHECKED)
        app.ic.property_activate("modus.windows", IBus.PropState.CHECKED)
        app.warten(0.1)
        pruefe("Menü schaltet auf Windows-Modus", app.menue["modus.windows"].get_state(), IBus.PropState.CHECKED)
        pruefe("anderer Modus abgehakt", app.menue["modus.tab"].get_state(), IBus.PropState.UNCHECKED)
        app.neu()
        app.tippen("Ich gla")
        app.taste(IBus.KEY_Up)
        pruefe("Windows-Modus wirkt sofort", app.cursor, 0)
        app.ic.focus_out()
        app.ic.focus_in()
        app.warten(0.1)
        pruefe("letztes Wort bleibt nach Fokuswechsel im Menü",
               app.menue["wort_merken"].get_label().get_text(), text("wort_merken_mit", wort="Ich"))

        # --- aus
        einstellen(modus="aus")
        app.ic.focus_out()
        app.ic.focus_in()
        app.warten(0.1)
        app.neu()
        app.tippen("Ich gla")
        pruefe("Modus aus zeigt nichts", app.leiste_sichtbar, False)
        app.taste(IBus.KEY_Tab)
        pruefe("Tab geht im Modus aus an die App", app.text, "Ich gla")

        # --- Passwortfeld
        einstellen(modus="windows")
        app.ic.focus_out()
        app.ic.focus_in()
        app.ic.set_content_type(IBus.InputPurpose.PASSWORD, 0)
        app.warten(0.1)
        app.neu()
        app.tippen("geheimwortgeheim ")
        pruefe("keine Leiste im Passwortfeld", app.leiste_sichtbar, False)
        app.ic.set_content_type(IBus.InputPurpose.FREE_FORM, 0)
        app.warten(0.1)
        app.neu()
        app.tippen("geheimw")
        pruefe("Passwort wurde nicht gelernt", "geheimwortgeheim" in [w.lower() for w in app.leiste], False)

        app.ic.focus_out()
        app.warten(0.2)
    finally:
        daemon.terminate()
        daemon.wait()

    log = TMP / "cache/wortvorhersage.log"
    if log.exists() and "Traceback" in log.read_text():
        print(log.read_text())
        FEHLER.append("Ausnahme im Log")
    if FEHLER:
        print(f"\n{len(FEHLER)} Fehler, Dateien liegen in {TMP}")
    else:
        shutil.rmtree(TMP)
        print("\nalles ok")
    sys.exit(1 if FEHLER else 0)


if __name__ == "__main__":
    main()
