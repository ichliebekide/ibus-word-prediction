#!/usr/bin/env python3
"""Baut die Wörterbücher in daten/ aus den Leipzig-Korpora und den CLDR-Emoji-Namen.

Aufruf:
    python3 werkzeuge/woerterbuch_bauen.py --korpus de=/pfad/deu_news_2023_300K-sentences.txt \
        --korpus en=/pfad/eng_news_2023_300K-sentences.txt

Erzeugt pro Sprache:
    daten/<sprache>_woerter.tsv   Wort<TAB>Häufigkeit (häufigste Schreibweise, absteigend)
    daten/<sprache>_paare.tsv     vorher<TAB>danach<TAB>Häufigkeit (beides klein geschrieben)
und daten/emoji.tsv            Stichwort<TAB>Emoji<TAB>Emoji…
"""

import argparse
import gzip
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from wortvorhersage.vorhersage import WORT_MUSTER  # noqa: E402

DATEN = Path(__file__).resolve().parent.parent / "daten"
CLDR = Path("/usr/share/ibus-typing-booster/data/annotations")

MAX_WOERTER = 120_000
MIN_ANZAHL_WORT = 3
MIN_ANZAHL_PAAR = 3
PAARE_PRO_WORT = 8

# Zwei Wörter gelten nur als Paar, wenn zwischen ihnen nichts als Leerraum steht.
NUR_LEERRAUM = re.compile(r"\s+")


def korpus_auswerten(pfad):
    schreibweisen = defaultdict(Counter)
    paare = Counter()
    with open(pfad, encoding="utf-8") as datei:
        for zeile in datei:
            satz = zeile.split("\t", 1)[-1]
            vorher = None
            ende_vorher = 0
            for treffer in WORT_MUSTER.finditer(satz):
                wort = treffer.group()
                klein = wort.lower()
                schreibweisen[klein][wort] += 1
                zwischen = satz[ende_vorher:treffer.start()]
                if vorher is not None and NUR_LEERRAUM.fullmatch(zwischen):
                    paare[(vorher, klein)] += 1
                vorher = klein
                ende_vorher = treffer.end()
    return schreibweisen, paare


def woerter_schreiben(schreibweisen, ziel):
    eintraege = []
    for varianten in schreibweisen.values():
        anzahl = sum(varianten.values())
        if anzahl < MIN_ANZAHL_WORT:
            continue
        form, _ = varianten.most_common(1)[0]
        # Großschreibung nur durch Satzanfang („Das“ statt „das“) zählt nicht.
        if form[0].isupper() and form.lower() in varianten and varianten[form.lower()] * 3 >= varianten[form]:
            form = form.lower()
        if len(form) > 1 and form.isupper() and len(varianten) > 1:
            form = next((v for v, _ in varianten.most_common() if not v.isupper()), form)
        eintraege.append((anzahl, form))
    eintraege.sort(key=lambda e: (-e[0], e[1]))
    with open(ziel, "w", encoding="utf-8") as datei:
        for anzahl, form in eintraege[:MAX_WOERTER]:
            datei.write(f"{form}\t{anzahl}\n")
    return min(len(eintraege), MAX_WOERTER)


def paare_schreiben(paare, ziel):
    nach_vorher = defaultdict(list)
    for (vorher, danach), anzahl in paare.items():
        if anzahl >= MIN_ANZAHL_PAAR:
            nach_vorher[vorher].append((anzahl, danach))
    zeilen = 0
    with open(ziel, "w", encoding="utf-8") as datei:
        for vorher in sorted(nach_vorher):
            for anzahl, danach in sorted(nach_vorher[vorher], reverse=True)[:PAARE_PRO_WORT]:
                datei.write(f"{vorher}\t{danach}\t{anzahl}\n")
                zeilen += 1
    return zeilen


def emoji_stil_zeichen():
    """Zeichen, die ohne U+FE0F als schwarzweißes Textsymbol erscheinen würden."""
    zeichen = set()
    pfad = Path("/usr/share/unicode/emoji/emoji-variation-sequences.txt")
    if pfad.exists():
        for zeile in pfad.read_text(encoding="utf-8").splitlines():
            if "emoji style" in zeile and not zeile.startswith("#"):
                zeichen.add(chr(int(zeile.split()[0], 16)))
    return zeichen


def echte_emojis():
    """Alle vollständigen Emojis laut Unicode (ohne bloße Symbole wie „≒“ aus den CLDR-Namen)."""
    emojis = set()
    pfad = Path("/usr/share/unicode/emoji/emoji-test.txt")
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        code, _, rest = zeile.partition(";")
        if "fully-qualified" in rest or "minimally-qualified" in rest:
            emoji = "".join(chr(int(c, 16)) for c in code.split())
            emojis.add(emoji)
            emojis.add(emoji.replace("\ufe0f", ""))
    return emojis


def fuellwoerter(sprachen, anzahl=500):
    """Die häufigsten Wörter jeder Sprache; „the“ oder „und“ sollen kein Emoji auslösen."""
    woerter = set()
    for sprache in sprachen:
        pfad = DATEN / f"{sprache}_woerter.tsv"
        if pfad.exists():
            with open(pfad, encoding="utf-8") as datei:
                for _, zeile in zip(range(anzahl), datei):
                    woerter.add(zeile.split("\t")[0].lower())
    return woerter


def emoji_schreiben(sprachen, ziel):
    emoji_stil = emoji_stil_zeichen()
    erlaubt = echte_emojis()
    haeufig = fuellwoerter(sprachen)
    # Stichwort -> {emoji: rang}; kleiner Rang = passender (eigener Name vor bloßem Stichwort).
    stichwoerter = defaultdict(dict)
    for sprache in sprachen:
        pfad = CLDR / f"{sprache}.xml.gz"
        if not pfad.exists():
            print(f"  keine Emoji-Namen für {sprache} unter {pfad}", file=sys.stderr)
            continue
        with gzip.open(pfad) as datei:
            baum = ET.parse(datei)
        namen = {e.get("cp"): (e.text or "").strip() for e in baum.iter("annotation") if e.get("type") == "tts"}
        for eintrag in baum.iter("annotation"):
            emoji = eintrag.get("cp")
            text = (eintrag.text or "").strip()
            if not emoji or not text or emoji not in erlaubt:
                continue
            name = namen.get(emoji, "")
            namenswoerter = [w.lower() for w in WORT_MUSTER.findall(name)]
            if len(emoji) == 1 and emoji in emoji_stil:
                emoji += "\ufe0f"
            for wort in WORT_MUSTER.findall(text):
                klein = wort.lower()
                if len(klein) < 3:
                    continue
                if namenswoerter == [klein]:
                    rang = 0
                elif klein in haeufig:
                    continue
                elif klein in namenswoerter:
                    rang = 1 + len(namenswoerter)
                else:
                    rang = 10 + len(namenswoerter)
                bisher = stichwoerter[klein].get(emoji, 99)
                stichwoerter[klein][emoji] = min(bisher, rang)
    with open(ziel, "w", encoding="utf-8") as datei:
        for wort in sorted(stichwoerter):
            emojis = sorted(stichwoerter[wort], key=stichwoerter[wort].get)
            datei.write(wort + "\t" + "\t".join(emojis[:4]) + "\n")
    return len(stichwoerter)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--korpus", action="append", default=[], metavar="SPRACHE=DATEI",
                        help="Leipzig-*-sentences.txt für eine Sprache, z. B. de=…")
    args = parser.parse_args()
    DATEN.mkdir(exist_ok=True)

    sprachen = []
    for angabe in args.korpus:
        sprache, _, pfad = angabe.partition("=")
        sprachen.append(sprache)
        print(f"{sprache}: werte {pfad} aus …")
        schreibweisen, paare = korpus_auswerten(pfad)
        n_woerter = woerter_schreiben(schreibweisen, DATEN / f"{sprache}_woerter.tsv")
        n_paare = paare_schreiben(paare, DATEN / f"{sprache}_paare.tsv")
        print(f"  {n_woerter} Wörter, {n_paare} Wortpaare")

    n_emoji = emoji_schreiben(sprachen or ["de", "en"], DATEN / "emoji.tsv")
    print(f"emoji: {n_emoji} Stichwörter")


if __name__ == "__main__":
    main()
