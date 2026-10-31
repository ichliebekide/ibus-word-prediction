#!/bin/bash
# Lädt die Leipzig-Korpora (Nachrichten 2023, je 300.000 Sätze, zusammen ~160 MB) und baut daten/ neu.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."
DOWNLOAD=$(mktemp -d)
trap 'rm -rf "$DOWNLOAD"' EXIT

for sprache in deu eng; do
    name=${sprache}_news_2023_300K
    echo "lade $name …"
    curl -sSfL "https://downloads.wortschatz-leipzig.de/corpora/$name.tar.gz" \
        | tar xz -C "$DOWNLOAD" "$name/$name-sentences.txt"
done

/usr/bin/python3 werkzeuge/woerterbuch_bauen.py \
    --korpus de="$DOWNLOAD/deu_news_2023_300K/deu_news_2023_300K-sentences.txt" \
    --korpus en="$DOWNLOAD/eng_news_2023_300K/eng_news_2023_300K-sentences.txt"
