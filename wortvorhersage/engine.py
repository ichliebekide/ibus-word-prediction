"""IBus-Engine: lässt jede Taste zur App durch und zeigt darüber eine Vorschlagsleiste.

Wie bei den Textvorschlägen von Windows landet das Getippte sofort in der App.
Beim Übernehmen eines Vorschlags wird nur der fehlende Rest eingefügt; nur wenn
sich die Schreibweise ändert („ha“ → „Haus“) oder ein Emoji das Wort ersetzt,
wird vorher zurückgelöscht.
"""

import logging
import subprocess

import gi

gi.require_version("IBus", "1.0")
from gi.repository import GLib, IBus  # noqa: E402

from .einstellungen import EIGENE_WOERTER_DATEI, EINSTELLUNGEN_DATEI  # noqa: E402
from . import texte  # noqa: E402

log = logging.getLogger(__name__)

M = IBus.ModifierType
KUERZEL_MASKE = M.CONTROL_MASK | M.MOD1_MASK | M.SUPER_MASK | M.MOD4_MASK | M.HYPER_MASK | M.META_MASK
WORT_ZEICHEN_INNEN = "-'’"
SATZENDE = ".!?"
KORRIGIERBARE_SATZZEICHEN = ".,;:!?)"
NUR_MODIFIKATOR = {
    IBus.KEY_Shift_L, IBus.KEY_Shift_R, IBus.KEY_Control_L, IBus.KEY_Control_R,
    IBus.KEY_Alt_L, IBus.KEY_Alt_R, IBus.KEY_Super_L, IBus.KEY_Super_R, IBus.KEY_Meta_L,
    IBus.KEY_Meta_R, IBus.KEY_Caps_Lock, IBus.KEY_Num_Lock, IBus.KEY_ISO_Level3_Shift,
    IBus.KEY_ISO_Level5_Shift, IBus.KEY_Hyper_L, IBus.KEY_Hyper_R,
}
ENTER = {IBus.KEY_Return, IBus.KEY_KP_Enter}
MODI = ("windows", "tab", "aus")
# evdev-Code der Rücktaste; IBus erwartet hier Keycode ohne den X11-Versatz von 8.
KEYCODE_RUECKTASTE = 14
# Zurückgeschickte Rücktasten kommen bei manchen Apps erst nach dem eingefügten Text an.
VERZOEGERUNG_NACH_RUECKTASTE_MS = 30


class Engine(IBus.EngineSimple):
    __gtype_name__ = "WortvorhersageEngine"

    def __init__(self, bus, pfad, dienste):
        super().__init__(connection=bus.get_connection(), object_path=pfad)
        self.dienste = dienste
        self.faehigkeiten = 0
        self.aktiv = True        # aus in Passwortfeldern
        self.privat = False      # Vorschläge ja, aber nichts lernen
        self.verschluckt = set() # Tasten, deren Drücken wir abgefangen haben
        self.letztes_wort = None   # bleibt über Fokuswechsel erhalten, fürs Menü
        self._eigenschaften_bauen()
        self._kontext_leeren()

    # ---------------------------------------------------------------- Zustand

    def _kontext_leeren(self):
        self.wort = ""
        self.vorher = None
        self.satzanfang = True
        self.auto_leerzeichen = False
        self._leiste_leeren()

    def _leiste_leeren(self):
        self.vorschlaege = []
        self.auswahl = None
        self.hide_lookup_table()

    @property
    def einstellungen(self):
        return self.dienste.einstellungen

    @property
    def modus(self):
        return self.einstellungen.modus if self.aktiv else "aus"

    # ---------------------------------------------------------- IBus-Methoden

    def do_process_key_event(self, keyval, keycode, state):
        try:
            return self._taste(keyval, keycode, state)
        except Exception:
            log.exception("Fehler bei Taste %s", IBus.keyval_name(keyval))
            self._kontext_leeren()
            return False

    def do_focus_in(self):
        self.dienste.neu_laden()
        self._eigenschaften_anmelden()
        self._kontext_leeren()

    def do_focus_out(self):
        self._kontext_leeren()
        self.dienste.sichern()

    def do_reset(self):
        self._kontext_leeren()

    def do_enable(self):
        # Fordert beim Client den umgebenden Text an, damit wir ihn später lesen können.
        self.get_surrounding_text()

    def do_set_capabilities(self, faehigkeiten):
        self.faehigkeiten = faehigkeiten

    def do_set_content_type(self, zweck, hinweise):
        self.aktiv = zweck not in (IBus.InputPurpose.PASSWORD, IBus.InputPurpose.PIN)
        self.privat = bool(hinweise & IBus.InputHints.PRIVATE)
        if not self.aktiv:
            self._kontext_leeren()

    def do_candidate_clicked(self, index, knopf, state):
        if 0 <= index < len(self.vorschlaege):
            self._uebernehmen(index)

    def do_property_activate(self, name, zustand):
        if name.startswith("modus.") and zustand == IBus.PropState.CHECKED:
            self.einstellungen.modus = name.removeprefix("modus.")
            self._leiste_leeren()
            for modus in MODI:
                key = f"modus.{modus}"
                self.eigenschaften[key].set_state(
                    IBus.PropState.CHECKED if key == name else IBus.PropState.UNCHECKED)
                self._eigenschaft_aktualisieren(key)
        elif name == "lernen":
            self.einstellungen.lernen = zustand == IBus.PropState.CHECKED
            self.eigenschaften["lernen"].set_state(zustand)
            self._eigenschaft_aktualisieren("lernen")
        elif name == "wort_merken" and self.letztes_wort:
            self.dienste.eigene_woerter.hinzufuegen(self.letztes_wort)
            self.dienste.neu_laden()
        elif name == "eigene_woerter":
            subprocess.Popen(["xdg-open", str(EIGENE_WOERTER_DATEI)])
        elif name == "einstellungen":
            subprocess.Popen(["xdg-open", str(EINSTELLUNGEN_DATEI)])

    # ------------------------------------------------------------ Tastatur

    def _weiter(self, keyval, keycode, state):
        """Taste wie ohne Wortvorhersage behandeln (inklusive Tottasten/Compose)."""
        return IBus.EngineSimple.do_process_key_event(self, keyval, keycode, state)

    def _schlucken(self, keyval):
        self.verschluckt.add(keyval)
        return True

    def _taste(self, keyval, keycode, state):
        if state & M.RELEASE_MASK:
            if keyval in self.verschluckt:
                self.verschluckt.discard(keyval)
                return True
            return self._weiter(keyval, keycode, state)

        if keyval in NUR_MODIFIKATOR:
            return self._weiter(keyval, keycode, state)

        modus = self.modus
        if modus == "aus":
            self._kontext_leeren()
            return self._weiter(keyval, keycode, state)

        kuerzel = bool(state & KUERZEL_MASKE)
        ohne_zusatz = not (state & (KUERZEL_MASKE | M.SHIFT_MASK))

        if self.vorschlaege:
            if modus == "windows":
                if self.auswahl is not None:
                    erledigt = self._taste_in_leiste(keyval)
                    if erledigt:
                        return self._schlucken(keyval)
                elif keyval == IBus.KEY_Up and ohne_zusatz:
                    self.auswahl = 0
                    self._leiste_zeigen()
                    return self._schlucken(keyval)
            elif modus == "tab":
                if keyval == IBus.KEY_Tab and ohne_zusatz:
                    self._uebernehmen(0)
                    return self._schlucken(keyval)
                if state & M.MOD1_MASK and IBus.KEY_1 <= keyval <= IBus.KEY_9:
                    index = keyval - IBus.KEY_1
                    if index < len(self.vorschlaege):
                        self._uebernehmen(index)
                        return self._schlucken(keyval)
            if keyval == IBus.KEY_Escape:
                self._leiste_leeren()
                return self._weiter(keyval, keycode, state)

        if kuerzel:
            self._kontext_leeren()
            return self._weiter(keyval, keycode, state)

        zeichen = IBus.keyval_to_unicode(keyval) or "\0"

        if keyval == IBus.KEY_BackSpace:
            self.auto_leerzeichen = False
            if self.wort:
                self.wort = self.wort[:-1]
                self._aktualisieren()
            else:
                self._kontext_leeren()
            return self._weiter(keyval, keycode, state)

        if zeichen.isalpha() or (zeichen in WORT_ZEICHEN_INNEN and self.wort):
            self.wort += zeichen
            self.auto_leerzeichen = False
            self._aktualisieren()
            return self._weiter(keyval, keycode, state)

        if zeichen == " ":
            self._wort_beenden()
            self.auto_leerzeichen = False
            self._aktualisieren()
            return self._weiter(keyval, keycode, state)

        if zeichen in KORRIGIERBARE_SATZZEICHEN and self.auto_leerzeichen \
                and self.einstellungen.schalter("satzzeichen_korrigieren"):
            # „Hallo |“ + „,“ → „Hallo,|“
            self.auto_leerzeichen = False
            self._satzzeichen_folgt(zeichen)
            self._leiste_leeren()
            self._ersetzen(1, zeichen)
            return self._schlucken(keyval)

        if keyval in ENTER or (zeichen.isprintable() and zeichen != "\0"):
            self._wort_beenden()
            self._satzzeichen_folgt("." if keyval in ENTER else zeichen)
            self._leiste_leeren()
            return self._weiter(keyval, keycode, state)

        # Pfeile, Pos1, Tab, Funktionstasten, Tottasten …: Wir wissen nicht mehr, wo der Cursor steht.
        self._kontext_leeren()
        return self._weiter(keyval, keycode, state)

    def _taste_in_leiste(self, keyval):
        """Windows-Modus, Leiste ist betreten. Gibt True zurück, wenn die Taste verbraucht ist."""
        if keyval in (IBus.KEY_Left, IBus.KEY_KP_Left):
            self.auswahl = max(0, self.auswahl - 1)
        elif keyval in (IBus.KEY_Right, IBus.KEY_KP_Right):
            self.auswahl = min(len(self.vorschlaege) - 1, self.auswahl + 1)
        elif keyval in ENTER or keyval == IBus.KEY_space:
            self._uebernehmen(self.auswahl)
            return True
        elif keyval in (IBus.KEY_Escape, IBus.KEY_Down, IBus.KEY_KP_Down):
            self.auswahl = None
            if keyval == IBus.KEY_Escape:
                self._leiste_leeren()
                return True
        elif keyval in (IBus.KEY_Up, IBus.KEY_KP_Up):
            pass
        else:
            self.auswahl = None
            self._leiste_zeigen()
            return False
        self._leiste_zeigen()
        return True

    # ------------------------------------------------------------ Wörter

    def _wort_beenden(self, wort=None):
        wort = (self.wort if wort is None else wort).strip(WORT_ZEICHEN_INNEN)
        if wort:
            lernen = self.einstellungen.lernen and not self.privat
            self.dienste.vorhersage.wort_getippt(wort, self.vorher, self.satzanfang, lernen)
            self.letztes_wort = wort
            if self._merken_beschriften():
                self._eigenschaft_aktualisieren("wort_merken")
            self.vorher = wort.lower()
            self.satzanfang = False
        self.wort = ""

    def _satzzeichen_folgt(self, zeichen):
        self.vorher = None
        if zeichen in SATZENDE:
            self.satzanfang = True

    def _aktualisieren(self):
        vorhersage = self.dienste.vorhersage
        anzahl = self.einstellungen.zahl("anzahl")
        self.auswahl = None
        if self.wort:
            if len(self.wort) >= self.einstellungen.zahl("ab_zeichen"):
                self.vorschlaege = vorhersage.vorschlaege(
                    self.wort, self.vorher, anzahl, self.einstellungen.schalter("emojis"))
            else:
                self.vorschlaege = []
        elif self.vorher and self.einstellungen.schalter("naechstes_wort"):
            self.vorschlaege = vorhersage.naechstes_wort(self.vorher, anzahl)
        else:
            self.vorschlaege = []
        self._leiste_zeigen()

    def _leiste_zeigen(self):
        if not self.vorschlaege:
            self.hide_lookup_table()
            return
        tabelle = IBus.LookupTable.new(len(self.vorschlaege), 0, self.auswahl is not None, False)
        tabelle.set_orientation(IBus.Orientation.HORIZONTAL)
        for i, vorschlag in enumerate(self.vorschlaege):
            tabelle.append_candidate(IBus.Text.new_from_string(vorschlag.text))
            if self.modus == "tab":
                beschriftung = "Tab" if i == 0 else f"Alt+{i + 1}"
            else:
                beschriftung = ""
            tabelle.set_label(i, IBus.Text.new_from_string(beschriftung))
        if self.auswahl is not None:
            tabelle.set_cursor_pos(self.auswahl)
        self.update_lookup_table(tabelle, True)

    def _uebernehmen(self, index):
        vorschlag = self.vorschlaege[index]
        einstellungen = self.einstellungen
        leerzeichen = " " if einstellungen.schalter("leerzeichen_danach") else ""
        getippt = self.wort

        if vorschlag.ist_emoji:
            if einstellungen.schalter("emoji_ersetzt_wort") and getippt:
                self._ersetzen(len(getippt), vorschlag.text + leerzeichen)
                self.wort = ""
            else:
                self._wort_beenden()
                vorne = " " if getippt else ""
                self._einfuegen(vorne + vorschlag.text + leerzeichen)
            self.vorher = None
            self.auto_leerzeichen = False
            self._leiste_leeren()
            return

        if vorschlag.text.startswith(getippt):
            self._einfuegen(vorschlag.text[len(getippt):] + leerzeichen)
        else:
            self._ersetzen(len(getippt), vorschlag.text + leerzeichen)
        self.wort = vorschlag.text
        self._wort_beenden()
        self.auto_leerzeichen = bool(leerzeichen)
        if leerzeichen:
            self._aktualisieren()
        else:
            self._leiste_leeren()

    # ---------------------------------------------------- Text in der App ändern

    def _einfuegen(self, text):
        if text:
            self.commit_text(IBus.Text.new_from_string(text))

    def _ersetzen(self, anzahl, text):
        """Löscht `anzahl` Zeichen vor dem Cursor und fügt `text` ein."""
        if anzahl <= 0:
            self._einfuegen(text)
        elif self._umgebung_zuverlaessig(anzahl):
            self.delete_surrounding_text(-anzahl, anzahl)
            self._einfuegen(text)
        else:
            for _ in range(anzahl):
                self.forward_key_event(IBus.KEY_BackSpace, KEYCODE_RUECKTASTE, 0)
                self.forward_key_event(IBus.KEY_BackSpace, KEYCODE_RUECKTASTE, M.RELEASE_MASK)
            GLib.timeout_add(VERZOEGERUNG_NACH_RUECKTASTE_MS, lambda: self._einfuegen(text) and False)

    def _umgebung_zuverlaessig(self, anzahl):
        """Nur wenn die App den Text vor dem Cursor wirklich meldet, löschen wir darüber."""
        if not self.faehigkeiten & IBus.Capabilite.SURROUNDING_TEXT:
            return False
        try:
            text, cursor, _ = self.get_surrounding_text()
        except TypeError:
            return False
        vorher = text.get_text()[:cursor] if text else ""
        return len(vorher) >= anzahl and vorher.strip() != ""

    # ------------------------------------------------------------ Menü

    def _eigenschaften_bauen(self):
        """Baut das Menü einmal. Kein Untermenü: KDEs Systemleiste klappt IBus-Untermenüs nicht sauber auf."""
        self.eigenschaften = {}
        liste = IBus.PropList()

        def eintrag(key, typ, titel, zustand=IBus.PropState.UNCHECKED, aktiv=True):
            eigenschaft = IBus.Property(
                key=key, prop_type=typ, label=IBus.Text.new_from_string(titel),
                state=zustand, visible=True, sensitive=aktiv)
            self.eigenschaften[key] = eigenschaft
            liste.append(eigenschaft)

        for name in MODI:
            eintrag(f"modus.{name}", IBus.PropType.RADIO, texte.text(f"modus.{name}"))
        eintrag("trenner", IBus.PropType.SEPARATOR, "")
        eintrag("lernen", IBus.PropType.TOGGLE, texte.text("lernen"))
        eintrag("wort_merken", IBus.PropType.NORMAL, texte.text("wort_merken"), aktiv=False)
        eintrag("eigene_woerter", IBus.PropType.NORMAL, texte.text("eigene_woerter"))
        eintrag("einstellungen", IBus.PropType.NORMAL, texte.text("einstellungen"))
        self.eigenschaften_liste = liste

    def _eigenschaften_anmelden(self):
        """Bei jedem Fokus nötig: Die Leiste zeigt immer das Menü der Engine mit Fokus."""
        modus = self.einstellungen.modus
        for name in MODI:
            self.eigenschaften[f"modus.{name}"].set_state(
                IBus.PropState.CHECKED if modus == name else IBus.PropState.UNCHECKED)
        self.eigenschaften["lernen"].set_state(
            IBus.PropState.CHECKED if self.einstellungen.lernen else IBus.PropState.UNCHECKED)
        self._merken_beschriften()
        self.register_properties(self.eigenschaften_liste)

    def _merken_beschriften(self):
        eigenschaft = self.eigenschaften["wort_merken"]
        titel = texte.text("wort_merken_mit", wort=self.letztes_wort) if self.letztes_wort else texte.text("wort_merken")
        if eigenschaft.get_label().get_text() == titel:
            return False
        eigenschaft.set_label(IBus.Text.new_from_string(titel))
        eigenschaft.set_sensitive(bool(self.letztes_wort))
        return True

    def _eigenschaft_aktualisieren(self, key):
        self.update_property(self.eigenschaften[key])
