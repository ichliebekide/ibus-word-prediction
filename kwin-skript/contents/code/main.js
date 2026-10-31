// Schiebt die Vorschlagsleiste der Eingabemethode (IBus) über den Textcursor.
//
// KWin setzt die Leiste direkt unter das Cursor-Rechteck und nur dann darüber, wenn unten
// kein Platz ist. Das Rechteck selbst bekommen Skripte nicht zu sehen, deshalb schätzen
// wir die Höhe der Textzeile (kwinrc, Gruppe [Script-wortvorhersage-oben], Zeilenhoehe).
//
// Ob KWin schon selbst hochgeklappt hat, lässt sich ohne das Rechteck nicht sicher erkennen.
// Das passiert nur, wenn der Cursor in den letzten paar Pixeln über dem unteren Rand steht;
// dann landet die Leiste etwas zu hoch, aber weiterhin über dem Text.

const ZEILENHOEHE = readConfig("Zeilenhoehe", 22);
const ABSTAND = readConfig("Abstand", 2);
const DEBUG = readConfig("Debug", false);

// Fenster-ID -> y, auf das wir die Leiste selbst gesetzt haben.
const verschoben = new Map();

function debug(text) {
    if (DEBUG) {
        print("wortvorhersage-oben: " + text);
    }
}

function anpassen(fenster) {
    const g = fenster.frameGeometry;
    debug(`Leiste bei ${g.x},${g.y} ${g.width}x${g.height}`);
    // Unsere eigene Verschiebung (KWin rundet dabei auf ganze Bildschirmpixel).
    const eigenesY = verschoben.get(fenster.internalId);
    if (eigenesY !== undefined && Math.abs(eigenesY - g.y) < 1) {
        return;
    }
    verschoben.delete(fenster.internalId);

    const bereich = workspace.clientArea(KWin.PlacementArea, fenster);
    const y = g.y - ZEILENHOEHE - g.height - ABSTAND;
    if (y < bereich.y) {
        debug(`oben kein Platz (Bereich ${JSON.stringify(bereich)})`);
        return;
    }
    debug(`verschiebe nach y=${y}`);
    verschoben.set(fenster.internalId, y);
    // Kein Qt.rect in KWin-Skripten: die Geometrie kopieren und nur y ändern.
    const neu = fenster.frameGeometry;
    neu.y = y;
    fenster.frameGeometry = neu;
    debug(`danach bei y=${fenster.frameGeometry.y}`);
}

function beobachten(fenster) {
    if (!fenster.inputMethod) {
        return;
    }
    fenster.frameGeometryChanged.connect(() => anpassen(fenster));
    fenster.closed.connect(() => verschoben.delete(fenster.internalId));
    anpassen(fenster);
}

workspace.windowList().forEach(beobachten);
workspace.windowAdded.connect(beobachten);
print("wortvorhersage-oben geladen");
