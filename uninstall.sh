#!/bin/bash
# Nimmt die Wortvorhersage wieder aus IBus heraus. Gelerntes und Einstellungen bleiben liegen.
# Removes word prediction from IBus. Learned words and settings are kept.
set -euo pipefail

sprache="${LANGUAGE:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}"

sudo rm -f /usr/share/ibus/component/wortvorhersage.xml
xkb=$(gsettings get org.freedesktop.ibus.general preload-engines | grep -o "'xkb:[^']*'" | head -1 || true)
gsettings set org.freedesktop.ibus.general preload-engines "[${xkb}]"
gsettings set org.freedesktop.ibus.general engines-order "[${xkb}]"
ibus restart >/dev/null 2>&1 || true
kwriteconfig6 --file kwinrc --group Plugins --key wortvorhersage-obenEnabled false
qdbus6 org.kde.KWin /KWin reconfigure 2>/dev/null || true
kpackagetool6 --type=KWin/Script -r wortvorhersage-oben >/dev/null 2>&1 || true

if [[ "$sprache" == de* ]]; then
cat <<EOF
Wortvorhersage entfernt.
IBus ist weiterhin als virtuelle Tastatur in KWin gesetzt; abschalten unter
Systemeinstellungen → Tastatur → Virtuelle Tastatur → „Keine“.
Gelerntes löschen:  rm ~/.local/share/wortvorhersage/gelernt.sqlite
EOF
else
cat <<EOF
Word prediction removed.
IBus is still set as KWin's virtual keyboard; turn it off under
System Settings → Keyboard → Virtual Keyboard → "None".
Delete learned words:  rm ~/.local/share/wortvorhersage/gelernt.sqlite
EOF
fi
