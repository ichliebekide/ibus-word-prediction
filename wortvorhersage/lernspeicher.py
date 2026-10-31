"""Merkt sich getippte Wörter und Wortpaare in einer SQLite-Datenbank."""

import sqlite3
import time

MIN_LAENGE = 2
MAX_LAENGE = 40


class Lernspeicher:
    def __init__(self, pfad):
        pfad.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(pfad, isolation_level=None)
        self.db.executescript("""
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS woerter (
                klein TEXT PRIMARY KEY, form TEXT NOT NULL,
                anzahl INTEGER NOT NULL, zuletzt REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS paare (
                vorher TEXT NOT NULL, danach TEXT NOT NULL, anzahl INTEGER NOT NULL,
                PRIMARY KEY (vorher, danach));
        """)
        self._offen = 0
        self._seit = time.monotonic()
        self.db.execute("BEGIN")

    def lernen(self, wort, vorher=None, satzanfang=False):
        """Zählt `wort`. Am Satzanfang sagt die Großschreibung nichts, dort bleibt die alte Form."""
        if not MIN_LAENGE <= len(wort) <= MAX_LAENGE:
            return
        klein = wort.lower()
        jetzt = time.time()
        self.db.execute("""
            INSERT INTO woerter (klein, form, anzahl, zuletzt) VALUES (?, ?, 1, ?)
            ON CONFLICT (klein) DO UPDATE SET anzahl = anzahl + 1, zuletzt = excluded.zuletzt,
                form = CASE WHEN ? THEN form ELSE excluded.form END
        """, (klein, wort, jetzt, satzanfang))
        if vorher:
            self.db.execute("""
                INSERT INTO paare (vorher, danach, anzahl) VALUES (?, ?, 1)
                ON CONFLICT (vorher, danach) DO UPDATE SET anzahl = anzahl + 1
            """, (vorher.lower(), klein))
        self._offen += 1
        if self._offen >= 20 or time.monotonic() - self._seit > 30:
            self.sichern()

    def sichern(self):
        self.db.execute("COMMIT")
        self.db.execute("BEGIN")
        self._offen = 0
        self._seit = time.monotonic()

    def mit_anfang(self, anfang, anzahl):
        ende = anfang + "\U0010ffff"
        return self.db.execute(
            "SELECT form, anzahl FROM woerter WHERE klein >= ? AND klein < ? ORDER BY anzahl DESC LIMIT ?",
            (anfang, ende, anzahl)).fetchall()

    def form(self, klein):
        zeile = self.db.execute("SELECT form FROM woerter WHERE klein = ?", (klein,)).fetchone()
        return zeile[0] if zeile else None

    def paar_anzahl(self, vorher, danach):
        zeile = self.db.execute("SELECT anzahl FROM paare WHERE vorher = ? AND danach = ?",
                                (vorher, danach)).fetchone()
        return zeile[0] if zeile else 0

    def danach(self, vorher, anzahl):
        return self.db.execute("""
            SELECT COALESCE(w.form, p.danach), p.anzahl FROM paare p
            LEFT JOIN woerter w ON w.klein = p.danach
            WHERE p.vorher = ? ORDER BY p.anzahl DESC LIMIT ?
        """, (vorher, anzahl)).fetchall()

    def vergessen(self):
        self.db.execute("DELETE FROM woerter")
        self.db.execute("DELETE FROM paare")
        self.sichern()

    def schliessen(self):
        self.db.execute("COMMIT")
        self.db.close()
