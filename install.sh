#!/bin/bash
# Meldet die Wortvorhersage bei IBus an und macht sie zur Standard-Eingabemethode.
# Braucht einmal sudo, weil IBus Komponenten nur aus /usr/share/ibus/component lädt.
# Registers the word prediction engine with IBus and makes it the default input method.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
PROJEKT="$PWD"
STARTER="$PROJEKT/ibus-engine-wortvorhersage"
ZIEL=/usr/share/ibus/component/wortvorhersage.xml

# Ausgabe auf Deutsch, wenn die Systemsprache Deutsch ist, sonst Englisch.
sprache="${LANGUAGE:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}"
meldung() { if [[ "$sprache" == de* ]]; then echo "$1"; else echo "$2"; fi; }

if [ ! -f daten/de_woerter.tsv ] && [ ! -f daten/en_woerter.tsv ]; then
    meldung "daten/ fehlt. Erst werkzeuge/daten_holen.sh ausführen." \
            "daten/ is missing. Run werkzeuge/daten_holen.sh first." >&2
    exit 1
fi

meldung "1/4  Komponente nach $ZIEL schreiben (sudo)" \
        "1/4  Writing component to $ZIEL (sudo)"
TMP=$(mktemp)
"$STARTER" --komponente "$STARTER" > "$TMP"
sudo install -m 644 "$TMP" "$ZIEL"
rm -f "$TMP"

meldung "2/4  Wortvorhersage als erste IBus-Eingabemethode eintragen" \
        "2/4  Making word prediction the first IBus input method"
xkb=$(gsettings get org.freedesktop.ibus.general preload-engines | grep -o "'xkb:[^']*'" | head -1 || true)
liste="['wortvorhersage'${xkb:+, $xkb}]"
gsettings set org.freedesktop.ibus.general preload-engines "$liste"
gsettings set org.freedesktop.ibus.general engines-order "$liste"

meldung "3/4  IBus in KWin als Eingabemethode setzen" \
        "3/4  Setting IBus as KWin's input method"
kwriteconfig6 --file kwinrc --group Wayland --key InputMethod \
    /usr/share/applications/org.freedesktop.IBus.Panel.Wayland.Gtk3.desktop
qdbus6 org.kde.KWin /KWin reconfigure 2>/dev/null || qdbus org.kde.KWin /KWin reconfigure 2>/dev/null || true

meldung "4/4  KWin-Skript installieren, das die Leiste über den Text schiebt" \
        "4/4  Installing the KWin script that moves the bar above the text"
kpackagetool6 --type=KWin/Script -i kwin-skript >/dev/null 2>&1 || kpackagetool6 --type=KWin/Script -u kwin-skript >/dev/null
kwriteconfig6 --file kwinrc --group Plugins --key wortvorhersage-obenEnabled true
kwriteconfig6 --file kwinrc --group Script-wortvorhersage-oben --key Debug --delete
qdbus6 org.kde.KWin /Scripting org.kde.kwin.Scripting.unloadScript wortvorhersage-oben >/dev/null 2>&1 || true
qdbus6 org.kde.KWin /KWin reconfigure 2>/dev/null || true

# Läuft IBus schon, sofort neu laden und umschalten.
if ibus address >/dev/null 2>&1 && ibus list-engine >/dev/null 2>&1; then
    ibus restart >/dev/null 2>&1 || true
    sleep 2
    ibus engine wortvorhersage 2>/dev/null || true
fi

if [[ "$sprache" == de* ]]; then
cat <<EOF

Fertig. Falls noch keine Vorschläge erscheinen: einmal ab- und wieder anmelden.
In den Systemeinstellungen unter Tastatur → Virtuelle Tastatur sollte jetzt „IBus Wayland“ ausgewählt sein.

Einstellungen:  ~/.config/wortvorhersage/einstellungen.ini
Eigene Wörter:  ~/.config/wortvorhersage/eigene_woerter.txt
Log:            ~/.cache/wortvorhersage.log
Leiste unten:   Systemeinstellungen → Fensterverwaltung → KWin-Skripte → „Wortvorhersage oben“ abschalten
Entfernen:      ./uninstall.sh
EOF
else
cat <<EOF

Done. If no suggestions appear yet, log out and back in once.
System Settings → Keyboard → Virtual Keyboard should now show "IBus Wayland".

Settings:       ~/.config/wortvorhersage/einstellungen.ini
Your words:     ~/.config/wortvorhersage/eigene_woerter.txt
Log:            ~/.cache/wortvorhersage.log
Bar below text: System Settings → Window Management → KWin Scripts → disable "Wortvorhersage oben"
Remove:         ./uninstall.sh
EOF
fi
