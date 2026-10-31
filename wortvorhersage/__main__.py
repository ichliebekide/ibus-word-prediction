import argparse

from .dienst import komponente_xml, starten


def main():
    parser = argparse.ArgumentParser(prog="wortvorhersage", description="IBus-Engine für Textvorschläge")
    parser.add_argument("--ibus", action="store_true",
                        help="wird von ibus-daemon gesetzt, wenn er die Engine startet")
    parser.add_argument("--komponente", metavar="BEFEHL",
                        help="gibt die IBus-Komponenten-Datei aus, deren Engine mit BEFEHL startet")
    args = parser.parse_args()
    if args.komponente:
        print(komponente_xml(args.komponente))
    else:
        starten()


if __name__ == "__main__":
    main()
