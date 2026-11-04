"""Vorhersage: Wortvervollständigung, nächstes Wort und Emojis.

Grundlage sind die Wörterbücher in daten/ (aus den Leipzig-Korpora gebaut),
die eigenen Wörter des Nutzers und das, was der Lernspeicher mitgeschrieben hat.
"""

import bisect
import heapq
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Buchstabenfolgen, auch mit Binde- oder Apostroph in der Mitte („E-Mail“, „geht's“).
WORT_MUSTER = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*")

DATEN = Path(__file__).resolve().parent.parent / "daten"

# Sprachcodes aus der Einstellungsdatei landen im Dateinamen; nur „de“, „en“ usw. zulassen.
SPRACHCODE = re.compile(r"[a-z]{2,3}")

# Gewichte für die Bewertung. Ein gelerntes oder eigenes Wort schlägt fast jedes Wörterbuchwort.
GEWICHT_GELERNT = 400.0
GEWICHT_EIGEN = 20000.0
GEWICHT_PAAR = 50.0
KANDIDATEN_JE_QUELLE = 40


@dataclass(frozen=True)
class Vorschlag:
    text: str            # was angezeigt und eingefügt wird
    ist_emoji: bool = False


class Woerterbuch:
    """Ein Wörterbuch einer Sprache, sortiert nach klein geschriebenem Schlüssel."""

    def __init__(self, sprache, daten=DATEN):
        self.sprache = sprache
        self.schluessel = []   # klein geschrieben, sortiert
        self.formen = []       # Schreibweise passend zu schluessel
        self.anteil = []       # Häufigkeit pro Million Wörter
        self.paare = {}        # vorher (klein) -> [(danach klein, anteil)]
        if not SPRACHCODE.fullmatch(sprache):
            return
        self._laden(daten / f"{sprache}_woerter.tsv", daten / f"{sprache}_paare.tsv")

    def _laden(self, woerter_pfad, paare_pfad):
        eintraege = []
        gesamt = 0
        if woerter_pfad.exists():
            with open(woerter_pfad, encoding="utf-8") as datei:
                for zeile in datei:
                    form, _, anzahl = zeile.rstrip("\n").partition("\t")
                    anzahl = int(anzahl)
                    gesamt += anzahl
                    eintraege.append((form.lower(), form, anzahl))
        eintraege.sort()
        faktor = 1e6 / max(gesamt, 1)
        self.schluessel = [e[0] for e in eintraege]
        self.formen = [e[1] for e in eintraege]
        self.anteil = [e[2] * faktor for e in eintraege]

        if paare_pfad.exists():
            with open(paare_pfad, encoding="utf-8") as datei:
                for zeile in datei:
                    vorher, danach, anzahl = zeile.rstrip("\n").split("\t")
                    self.paare.setdefault(vorher, []).append((danach, int(anzahl) * faktor))

    def __contains__(self, klein):
        i = bisect.bisect_left(self.schluessel, klein)
        return i < len(self.schluessel) and self.schluessel[i] == klein

    def form(self, klein):
        i = bisect.bisect_left(self.schluessel, klein)
        if i < len(self.schluessel) and self.schluessel[i] == klein:
            return self.formen[i]
        return None

    def haeufigkeit(self, klein):
        i = bisect.bisect_left(self.schluessel, klein)
        if i < len(self.schluessel) and self.schluessel[i] == klein:
            return self.anteil[i]
        return 0.0

    @lru_cache(maxsize=4096)
    def mit_anfang(self, anfang):
        """Die häufigsten Wörter, die mit `anfang` (klein) beginnen: [(form, anteil)]."""
        start = bisect.bisect_left(self.schluessel, anfang)
        ende = bisect.bisect_left(self.schluessel, anfang + "\U0010ffff", lo=start)
        beste = heapq.nlargest(KANDIDATEN_JE_QUELLE, range(start, ende), key=self.anteil.__getitem__)
        return tuple((self.formen[i], self.anteil[i]) for i in beste)


class Emojis:
    def __init__(self, pfad=DATEN / "emoji.tsv"):
        self.schluessel = []
        self.emojis = []
        if pfad.exists():
            with open(pfad, encoding="utf-8") as datei:
                for zeile in datei:
                    wort, *emojis = zeile.rstrip("\n").split("\t")
                    self.schluessel.append(wort)
                    self.emojis.append(emojis)

    def passend(self, klein, mindestlaenge=3):
        """Emojis, deren Stichwort `klein` ist oder (ab 4 Zeichen) damit anfängt."""
        if len(klein) < mindestlaenge:
            return []
        i = bisect.bisect_left(self.schluessel, klein)
        gefunden = []
        if i < len(self.schluessel) and self.schluessel[i] == klein:
            gefunden.extend(self.emojis[i])
            i += 1
        if len(klein) >= 4:
            while i < len(self.schluessel) and self.schluessel[i].startswith(klein) and len(gefunden) < 6:
                gefunden.extend(e for e in self.emojis[i] if e not in gefunden)
                i += 1
        return gefunden


def schreibweise_anpassen(vorschlag, getippt):
    """Übernimmt Großschreibung aus dem Getippten: „Hal“ → „Hallo“, „HAL“ → „HALLO“."""
    if not getippt:
        return vorschlag
    if len(getippt) >= 2 and getippt.isupper():
        return vorschlag.upper()
    if getippt[0].isupper():
        return vorschlag[0].upper() + vorschlag[1:]
    return vorschlag


class Vorhersage:
    def __init__(self, sprachen=("de", "en"), lernspeicher=None, eigene_woerter=(), daten=DATEN):
        sprachen = [s.lower() for s in sprachen if SPRACHCODE.fullmatch(s.lower())]
        self.woerterbuecher = [Woerterbuch(s, daten) for s in sprachen]
        self.emojis = Emojis(daten / "emoji.tsv")
        self.lernspeicher = lernspeicher
        self.eigene = {}
        self.eigene_setzen(eigene_woerter)
        # Welche Sprache gerade getippt wird; passt sich an die letzten Wörter an.
        # Am Anfang liegt die zuerst genannte Sprache vorn.
        self.sprachgewicht = {w.sprache: (1.5 if i == 0 else 0.7) for i, w in enumerate(self.woerterbuecher)}

    def eigene_setzen(self, woerter):
        self.eigene = {w.lower(): w for w in woerter if w}
        self._eigene_sortiert = sorted(self.eigene)

    def wort_getippt(self, wort, vorher=None, satzanfang=False, lernen=True):
        """Merkt sich ein fertig getipptes Wort: für die Spracherkennung und, wenn `lernen`, dauerhaft."""
        klein = wort.lower()
        treffer = [w for w in self.woerterbuecher if klein in w]
        if len(treffer) == 1:
            for w in self.woerterbuecher:
                ziel = 2.0 if w is treffer[0] else 0.5
                self.sprachgewicht[w.sprache] = self.sprachgewicht[w.sprache] * 0.8 + ziel * 0.2
        if lernen and self.lernspeicher is not None:
            self.lernspeicher.lernen(wort, vorher, satzanfang)

    def _paar_bonus(self, vorher, klein):
        if not vorher:
            return 0.0
        bonus = 0.0
        for w in self.woerterbuecher:
            for danach, anteil in w.paare.get(vorher, ()):
                if danach == klein:
                    bonus += anteil * self.sprachgewicht[w.sprache]
        if self.lernspeicher is not None:
            bonus += self.lernspeicher.paar_anzahl(vorher, klein) * GEWICHT_GELERNT
        return bonus * GEWICHT_PAAR

    def vorschlaege(self, getippt, vorher=None, anzahl=3, emojis=True):
        """Vorschläge für das angefangene Wort `getippt` (ohne das Wort selbst)."""
        klein = getippt.lower()
        vorher = vorher.lower() if vorher else None
        punkte = {}   # klein -> [punkte, form]

        def hinzu(form, wert):
            k = form.lower()
            if k == klein or not k.startswith(klein):
                return
            if k in punkte:
                punkte[k][0] += wert
            else:
                punkte[k] = [wert, form]

        for w in self.woerterbuecher:
            gewicht = self.sprachgewicht[w.sprache]
            for form, anteil in w.mit_anfang(klein):
                hinzu(form, anteil * gewicht)

        i = bisect.bisect_left(self._eigene_sortiert, klein)
        while i < len(self._eigene_sortiert) and self._eigene_sortiert[i].startswith(klein):
            hinzu(self.eigene[self._eigene_sortiert[i]], GEWICHT_EIGEN)
            i += 1

        if self.lernspeicher is not None:
            for form, zahl in self.lernspeicher.mit_anfang(klein, KANDIDATEN_JE_QUELLE):
                hinzu(form, zahl * GEWICHT_GELERNT)

        for k, eintrag in punkte.items():
            eintrag[0] += self._paar_bonus(vorher, k)

        beste = heapq.nlargest(anzahl, punkte.values(), key=lambda e: e[0])
        ergebnis = [Vorschlag(schreibweise_anpassen(form, getippt)) for _, form in beste]

        if emojis:
            passende = self.emojis.passend(klein)
            if passende:
                emoji = Vorschlag(passende[0], ist_emoji=True)
                ergebnis = ergebnis[: anzahl - 1] + [emoji]
        return ergebnis

    def naechstes_wort(self, vorher, anzahl=3):
        """Vorschläge direkt nach einem Leerzeichen, nur aus Wortpaaren."""
        vorher = vorher.lower()
        punkte = {}
        for w in self.woerterbuecher:
            gewicht = self.sprachgewicht[w.sprache]
            for danach, anteil in w.paare.get(vorher, ()):
                form = self._form(danach)
                punkte[danach] = punkte.get(danach, (0.0, form))
                punkte[danach] = (punkte[danach][0] + anteil * gewicht, form)
        if self.lernspeicher is not None:
            for danach, zahl in self.lernspeicher.danach(vorher, KANDIDATEN_JE_QUELLE):
                k = danach.lower()
                alt = punkte.get(k, (0.0, danach))
                punkte[k] = (alt[0] + zahl * GEWICHT_GELERNT, alt[1])
        beste = heapq.nlargest(anzahl, punkte.values(), key=lambda e: e[0])
        return [Vorschlag(form) for _, form in beste]

    def _form(self, klein):
        if klein in self.eigene:
            return self.eigene[klein]
        if self.lernspeicher is not None:
            form = self.lernspeicher.form(klein)
            if form:
                return form
        beste = max(self.woerterbuecher, key=lambda w: w.haeufigkeit(klein) * self.sprachgewicht[w.sprache])
        return beste.form(klein) or klein
