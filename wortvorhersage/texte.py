"""Alle sichtbaren Texte auf Deutsch und Englisch; die Sprache richtet sich nach der Systemsprache."""

import os


def _systemsprache():
    for variable in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        wert = os.environ.get(variable, "")
        if wert and wert not in ("C", "POSIX"):
            return "de" if wert.split(":")[0].lower().startswith("de") else "en"
    return "en"


SPRACHE = _systemsprache()

TEXTE = {
    "de": {
        "name": "Wortvorhersage",
        "beschreibung": "Textvorschläge beim Tippen (Deutsch, Englisch, Emojis)",
        "modus.windows": "Bedienung wie Windows (↑, dann ←/→ und Enter)",
        "modus.tab": "Bedienung mit Tab (Alt+Zahl für weitere)",
        "modus.aus": "Keine Vorschläge",
        "lernen": "Getippte Wörter lernen",
        "wort_merken": "Letztes Wort merken",
        "wort_merken_mit": "„{wort}“ zu eigenen Wörtern",
        "eigene_woerter": "Eigene Wörter bearbeiten …",
        "einstellungen": "Einstellungen öffnen …",
        "einstellungen_kopf": """\
# Einstellungen der Wortvorhersage. Änderungen gelten, sobald du in ein anderes Fenster oder Feld wechselst.
# Die Namen gehen auch auf Englisch (mode, languages, …).
#
# modus                    windows = Leiste per Pfeil-hoch betreten, links/rechts wählen, Enter/Leertaste übernehmen
#                          tab     = Tab übernimmt den ersten Vorschlag, Alt+1 … Alt+9 einen bestimmten
#                          aus     = keine Vorschläge
# sprachen                 Wörterbücher aus daten/, z. B. "de, en"; die erste Sprache liegt anfangs vorn
# anzahl                   wie viele Vorschläge in der Leiste stehen
# emojis                   passendes Emoji als letzten Vorschlag zeigen
# emoji_ersetzt_wort       ja = „Herz“ wird durch das Emoji ersetzt, nein = Emoji wird angehängt
# naechstes_wort           nach einem Leerzeichen schon das nächste Wort vorschlagen
# leerzeichen_danach       nach einem übernommenen Wort ein Leerzeichen setzen
# satzzeichen_korrigieren  „Hallo ,“ → „Hallo,“ wenn direkt nach dem automatischen Leerzeichen ein Satzzeichen kommt
# lernen                   getippte Wörter merken (nie in Passwortfeldern)
# ab_zeichen               Vorschläge erst ab so vielen getippten Buchstaben

""",
        "eigene_kopf": """\
# Eigene Wörter für die Wortvorhersage, eins pro Zeile.
# Sie werden bevorzugt vorgeschlagen, genau in der Schreibweise wie hier.
# Zeilen mit # werden ignoriert.

""",
    },
    "en": {
        "name": "Word Prediction",
        "beschreibung": "Text suggestions while typing (German, English, emoji)",
        "modus.windows": "Windows style (↑, then ←/→ and Enter)",
        "modus.tab": "Tab accepts (Alt+number for others)",
        "modus.aus": "No suggestions",
        "lernen": "Learn typed words",
        "wort_merken": "Remember last word",
        "wort_merken_mit": "Add “{wort}” to my words",
        "eigene_woerter": "Edit my words …",
        "einstellungen": "Open settings …",
        "einstellungen_kopf": """\
# Word prediction settings. Changes apply as soon as you switch to another window or field.
# German key names (modus, sprachen, …) work as well.
#
# mode                 windows = press Up to enter the bar, Left/Right to choose, Enter/Space to accept
#                      tab     = Tab accepts the first suggestion, Alt+1 … Alt+9 a specific one
#                      off     = no suggestions
# languages            dictionaries from daten/, e.g. "en, de"; the first one is preferred at the start
# count                how many suggestions the bar shows
# emojis               show a matching emoji as the last suggestion
# emoji_replaces_word  yes = "heart" is replaced by the emoji, no = the emoji is appended
# next_word            suggest the next word right after a space
# space_after          add a space after an accepted word
# fix_punctuation      "Hello ," → "Hello," when punctuation follows the automatic space
# learn                remember typed words (never in password fields)
# min_letters          only suggest after this many typed letters

""",
        "eigene_kopf": """\
# Your own words for word prediction, one per line.
# They are preferred and suggested exactly as written here.
# Lines starting with # are ignored.

""",
    },
}


def text(schluessel, **werte):
    return TEXTE[SPRACHE][schluessel].format(**werte) if werte else TEXTE[SPRACHE][schluessel]
