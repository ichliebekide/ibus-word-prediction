"""Startet den IBus-Dienst: Fabrik für Engines, gemeinsame Vorhersage, Anmeldung am Bus."""

import logging
import os
from pathlib import Path

import gi

gi.require_version("IBus", "1.0")
from gi.repository import GLib, GObject, IBus  # noqa: E402

from .einstellungen import LERNSPEICHER_DATEI, EigeneWoerter, Einstellungen  # noqa: E402
from .engine import Engine  # noqa: E402
from .lernspeicher import Lernspeicher  # noqa: E402
from .texte import text  # noqa: E402
from .vorhersage import Vorhersage  # noqa: E402

KOMPONENTE = "org.freedesktop.IBus.Wortvorhersage"
ENGINE_NAME = "wortvorhersage"
VERSION = "0.1"

log = logging.getLogger(__name__)


class Dienste:
    """Was alle Engines (eine pro Eingabefeld-Kontext) gemeinsam nutzen."""

    def __init__(self):
        self.einstellungen = Einstellungen()
        self.eigene_woerter = EigeneWoerter()
        self.lernspeicher = Lernspeicher(LERNSPEICHER_DATEI)
        self._sprachen = None
        self.vorhersage = None
        self.neu_laden()

    def neu_laden(self):
        self.einstellungen.neu_laden()
        if self.einstellungen.sprachen != self._sprachen:
            self._sprachen = self.einstellungen.sprachen
            self.vorhersage = Vorhersage(self._sprachen, self.lernspeicher, self.eigene_woerter.woerter)
            log.info("Wörterbücher geladen: %s", ", ".join(self._sprachen))
        elif self.eigene_woerter.neu_laden():
            self.vorhersage.eigene_setzen(self.eigene_woerter.woerter)

    def sichern(self):
        self.lernspeicher.sichern()


class Fabrik(IBus.Factory):
    __gtype_name__ = "WortvorhersageFabrik"

    def __init__(self, bus, dienste):
        super().__init__(connection=bus.get_connection(), object_path=IBus.PATH_FACTORY)
        self.bus = bus
        self.dienste = dienste
        self.zaehler = 0

    def do_create_engine(self, name):
        self.zaehler += 1
        return Engine(self.bus, f"/org/freedesktop/IBus/Engine/Wortvorhersage/{self.zaehler}", self.dienste)


def komponente_xml(befehl):
    """Komponenten-Datei für /usr/share/ibus/component; `befehl` startet die Engine."""
    beschreibung = IBus.EngineDesc(
        name=ENGINE_NAME,
        longname=text("name"),
        description=text("beschreibung"),
        language="de",
        license="MIT",
        author="emi",
        icon="input-keyboard",
        layout="default",
        rank=0,
        symbol="W",
        textdomain="",
    )
    komponente = IBus.Component(
        name=KOMPONENTE, description=text("name"), version=VERSION, license="MIT",
        author="emi", homepage="", command_line=f"{befehl} --ibus", textdomain="")
    komponente.add_engine(beschreibung)
    xml = GLib.String.new("")
    komponente.output(xml, 0)
    return '<?xml version="1.0" encoding="utf-8"?>\n' + xml.str


def starten():
    log_datei = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "wortvorhersage.log"
    log_datei.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=log_datei, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    IBus.init()
    bus = IBus.Bus()
    if not bus.is_connected():
        raise SystemExit("Keine Verbindung zu ibus-daemon. Läuft IBus?")
    schleife = GLib.MainLoop()
    bus.connect("disconnected", lambda *_: schleife.quit())

    dienste = Dienste()
    fabrik = Fabrik(bus, dienste)
    fabrik.add_engine(ENGINE_NAME, GObject.type_from_name("WortvorhersageEngine"))
    bus.request_name(KOMPONENTE, 0)
    log.info("Wortvorhersage läuft")

    try:
        schleife.run()
    finally:
        dienste.lernspeicher.schliessen()
