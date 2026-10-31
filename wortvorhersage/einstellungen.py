"""Einstellungen (INI-Datei) und die Liste eigener Wörter."""

import configparser
import os
from pathlib import Path

from .texte import SPRACHE, text

KONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "wortvorhersage"
DATEN = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "wortvorhersage"

EINSTELLUNGEN_DATEI = KONFIG / "einstellungen.ini"
EIGENE_WOERTER_DATEI = KONFIG / "eigene_woerter.txt"
LERNSPEICHER_DATEI = DATEN / "gelernt.sqlite"

# Bedienung: "windows" (Pfeil hoch, links/rechts, Enter), "tab" (Tab oder Alt+Zahl) oder "aus".
MODI = ("windows", "tab", "aus")

STANDARD = {
    "modus": "windows",
    "sprachen": "de, en" if SPRACHE == "de" else "en",
    "anzahl": "3",
    "emojis": "ja",
    "emoji_ersetzt_wort": "ja",
    "naechstes_wort": "ja",
    "leerzeichen_danach": "ja",
    "satzzeichen_korrigieren": "ja",
    "lernen": "ja",
    "ab_zeichen": "1",
}

# Englische Namen in der Datei; intern gelten immer die deutschen.
ENGLISCH = {
    "modus": "mode",
    "sprachen": "languages",
    "anzahl": "count",
    "emojis": "emojis",
    "emoji_ersetzt_wort": "emoji_replaces_word",
    "naechstes_wort": "next_word",
    "leerzeichen_danach": "space_after",
    "satzzeichen_korrigieren": "fix_punctuation",
    "lernen": "learn",
    "ab_zeichen": "min_letters",
}
AUS_ENGLISCH = {englisch: deutsch for deutsch, englisch in ENGLISCH.items()}
WERTE_ENGLISCH = {"ja": "yes", "nein": "no", "aus": "off"}
WERTE_AUS_ENGLISCH = {englisch: deutsch for deutsch, englisch in WERTE_ENGLISCH.items()}
ABSCHNITT = "wortvorhersage"


class Einstellungen:
    def __init__(self, pfad=EINSTELLUNGEN_DATEI):
        self.pfad = pfad
        self.werte = dict(STANDARD)
        self._stand = None
        if not pfad.exists():
            self.speichern()
        self.neu_laden()

    def neu_laden(self):
        """Liest die Datei neu ein, wenn sie sich geändert hat. Gibt True zurück, wenn ja."""
        try:
            stand = self.pfad.stat().st_mtime_ns
        except FileNotFoundError:
            return False
        if stand == self._stand:
            return False
        self._stand = stand
        parser = configparser.ConfigParser()
        parser.read(self.pfad, encoding="utf-8")
        self.werte = dict(STANDARD)
        if parser.has_section(ABSCHNITT):
            for name, wert in parser[ABSCHNITT].items():
                wert = wert.strip()
                self.werte[AUS_ENGLISCH.get(name, name)] = WERTE_AUS_ENGLISCH.get(wert.lower(), wert)
        return True

    def speichern(self):
        """Schreibt die Datei in der Systemsprache (Namen und ja/nein bzw. yes/no)."""
        parser = configparser.ConfigParser()
        if SPRACHE == "de":
            parser[ABSCHNITT] = self.werte
        else:
            parser[ABSCHNITT] = {ENGLISCH.get(name, name): WERTE_ENGLISCH.get(wert, wert)
                                 for name, wert in self.werte.items()}
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        with open(self.pfad, "w", encoding="utf-8") as datei:
            datei.write(text("einstellungen_kopf"))
            parser.write(datei)
        self._stand = self.pfad.stat().st_mtime_ns

    @property
    def modus(self):
        modus = self.werte.get("modus", "windows").lower()
        return modus if modus in MODI else "windows"

    @modus.setter
    def modus(self, wert):
        self.werte["modus"] = wert
        self.speichern()

    @property
    def lernen(self):
        return self.schalter("lernen")

    @lernen.setter
    def lernen(self, wert):
        self.werte["lernen"] = "ja" if wert else "nein"
        self.speichern()

    @property
    def sprachen(self):
        return tuple(s.strip() for s in self.werte.get("sprachen", "de").split(",") if s.strip())

    def zahl(self, name):
        try:
            return max(1, int(self.werte.get(name, STANDARD[name])))
        except ValueError:
            return int(STANDARD[name])

    def schalter(self, name):
        wert = self.werte.get(name, STANDARD[name]).lower()
        return wert in ("ja", "an", "true", "1", "yes", "on")


class EigeneWoerter:
    def __init__(self, pfad=EIGENE_WOERTER_DATEI):
        self.pfad = pfad
        self.woerter = []
        self._stand = None
        if not pfad.exists():
            pfad.parent.mkdir(parents=True, exist_ok=True)
            pfad.write_text(text("eigene_kopf"), encoding="utf-8")
        self.neu_laden()

    def neu_laden(self):
        try:
            stand = self.pfad.stat().st_mtime_ns
        except FileNotFoundError:
            return False
        if stand == self._stand:
            return False
        self._stand = stand
        zeilen = self.pfad.read_text(encoding="utf-8").splitlines()
        self.woerter = [z.strip() for z in zeilen if z.strip() and not z.lstrip().startswith("#")]
        return True

    def hinzufuegen(self, wort):
        if wort.lower() in (w.lower() for w in self.woerter):
            return
        with open(self.pfad, "a", encoding="utf-8") as datei:
            datei.write(wort + "\n")
        self.neu_laden()
