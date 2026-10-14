# encoding: utf-8
"""
Kinomat as a plugin: a Window menu item that opens the panel.

Nothing here runs at launch but the line that registers the menu item. A
plugin is loaded every time Glyphs starts, so anything heavier waits until the
item is actually picked.
"""
from __future__ import division, print_function, unicode_literals

import os
import math
import random
import time
import struct
import base64
import tempfile

import objc
from AppKit import (NSColor, NSImage, NSTimer, NSColorSpace,
    NSFont, NSView, NSButton, NSPopUpButton,
    NSBezierPath, NSViewWidthSizable, NSViewHeightSizable, NSAttributedString,
    NSFontAttributeName, NSParagraphStyleAttributeName, NSMutableParagraphStyle, NSCenterTextAlignment,
    NSNaturalTextAlignment, NSBezelBorder, NSFontWeightMedium, NSFontWeightRegular,
    NSWorkspace, NSImageOnly, NSTextAlignmentLeft, NSTextAlignmentRight,
    NSTextAlignmentCenter, NSTextField, NSAppearance, NSKernAttributeName,
    NSForegroundColorAttributeName, NSFontWeightSemibold, NSFontWeightBold,
    NSFocusRingTypeNone, NSBaselineOffsetAttributeName,
    NSEvent, NSEventMaskKeyDown, NSTextView, NSScreen,
    NSEventModifierFlagShift, NSEventModifierFlagOption)
from Foundation import (NSData, NSURL, NSAttributedString, NSRunLoop, NSDate,
    NSMutableAttributedString)
# vanilla, Quartz and CoreText cost about a fifth of a second to import
# between them, and Glyphs imports every plugin at launch — whether or not
# anyone opens this window. Nothing outside the panel needs them, so they are
# fetched the first time it is asked for. See loadUI().
vanilla = None
Quartz = None
CoreText = None
putFile = None
getFolder = None
getFile = None


def loadUI():
    """Bring in the heavy three. Cheap after the first call: an import that
    has already happened is a dictionary lookup."""
    global vanilla, Quartz, CoreText, putFile, getFolder, getFile
    if vanilla is not None:
        return
    import vanilla as _vanilla
    import Quartz as _quartz
    import CoreText as _coretext
    from vanilla.dialogs import (putFile as _putFile, getFolder as _getFolder,
                                 getFile as _getFile)
    vanilla, Quartz, CoreText = _vanilla, _quartz, _coretext
    putFile, getFolder, getFile = _putFile, _getFolder, _getFile

import GlyphsApp
from GlyphsApp import Glyphs, GSInstance, Message, WINDOW_MENU


# ----------------------------------------------------------------------------
# easing
# ----------------------------------------------------------------------------

def _bounceOut(t):
    n, d = 7.5625, 2.75
    if t < 1 / d:
        return n * t * t
    if t < 2 / d:
        t -= 1.5 / d
        return n * t * t + 0.75
    if t < 2.5 / d:
        t -= 2.25 / d
        return n * t * t + 0.9375
    t -= 2.625 / d
    return n * t * t + 0.984375


EASINGS = [
    ("Linear", lambda t: t),
    ("Ease In", lambda t: t * t * t),
    ("Ease Out", lambda t: 1 - pow(1 - t, 3)),
    ("Ease In-Out", lambda t: 4 * t * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 3) / 2),
    ("Sine In-Out", lambda t: -(math.cos(math.pi * t) - 1) / 2),
    ("Expo In-Out", lambda t: t if t in (0, 1) else (
        pow(2, 20 * t - 10) / 2 if t < 0.5 else (2 - pow(2, -20 * t + 10)) / 2)),
    ("Back In-Out", lambda t: (pow(2 * t, 2) * ((2.5949095 + 1) * 2 * t - 2.5949095)) / 2 if t < 0.5
        else (pow(2 * t - 2, 2) * ((2.5949095 + 1) * (t * 2 - 2) + 2.5949095) + 2) / 2),
    ("Elastic Out", lambda t: t if t in (0, 1) else
        pow(2, -10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1),
    ("Bounce Out", _bounceOut),
]

EASE_NAMES = [e[0] for e in EASINGS]
LINEAR = EASE_NAMES.index("Linear")
MODES = ["Ping-pong", "Restart", "Play once"]
ALIGNMENTS = ["Left", "Center", "Right"]

# canvas presets: name, width, height
PRESETS = [
    ("Reel / Story 9:16", 1080, 1920),
    ("Post 1:1", 1080, 1080),
    ("Post 4:5", 1080, 1350),
    ("Post 5:4", 1350, 1080),
    ("Landscape 16:9", 1920, 1080),
    ("Square 2000", 2000, 2000),
    ("Custom", None, None),
]
PRESET_NAMES = [p[0] for p in PRESETS]

# the canvas opens square; every other format is one menu away
DEFAULT_PRESET = PRESET_NAMES.index("Post 1:1")


UNITS = ["Whole", "Words", "Letters"]

# One key unlocks every Resistenza tool, and the site already answers for it:
# GET verify.php?key=… -> {"ok": true, "name": "…"}. Nothing else is sent, and
# nothing about the font ever leaves the machine.
VERIFY_URL = "https://resistenza.es/tools/verify.php?key=%s"
BUY_URL = "https://buy.stripe.com/5kQ5kD5SX38m19New9eQM05"
TOOLS_URL = "https://resistenza.es/tools"


def bundleVersion():
    """
    The version out of the bundle's own Info.plist.

    Read rather than written here, so the number in the title bar cannot drift
    from the one the bundle declares — there is only ever one to change.
    """
    try:
        import plistlib
        contents = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(contents, "Info.plist"), "rb") as handle:
            return str(plistlib.load(handle).get(
                "CFBundleShortVersionString", "") or "")
    except Exception:
        return ""


VERSION = bundleVersion()
# what the one key already covers, named in the sheet: the argument for buying
# it, and the reason there is no licence per tool
TOOLS = ("Kinomat", "Cassetto", "Grado")

# A project is a .rsztools file, as in the tools on the web: plain JSON that
# says which app it is for. The web Kinomat's say "cinema" and hold settings
# this panel does not have, so the panel's have a name of their own.
PROJECT_APP = "kinomat-glyphs"
# the old names, kept through the rename: a new key would look like a fresh
# install to everyone who has already activated, and ask them for the serial
# again for no reason
KEY_DEFAULT = "com.rsztype.CinemaVF.key"
NAME_DEFAULT = "com.rsztype.CinemaVF.name"


def verifyKey(key):
    """
    (ok, name) from the site, or (None, reason) when it could not be asked.

    Through macOS rather than urllib. The Python that ships with the system
    has no certificate store of its own, so urlopen on an https address dies
    with CERTIFICATE_VERIFY_FAILED — and a real key then looks like a wrong
    one, which is worse than saying nothing. NSData uses the system's trust,
    the same one Safari uses.
    """
    key = (key or "").strip()
    if not key:
        return False, ""
    try:
        import json
        import urllib.parse
        url = NSURL.URLWithString_(VERIFY_URL % urllib.parse.quote(key))
        data = NSData.dataWithContentsOfURL_(url)
        if data is None:
            return None, "could not reach resistenza.es"
        answer = json.loads(bytes(data).decode("utf-8"))
        return bool(answer.get("ok")), str(answer.get("name") or "")
    except Exception as error:
        return None, str(error)


def splitUnits(text, unit):
    """The pieces the animation moves through, spaces kept with their word."""
    if unit == "Letters":
        return list(text)
    if unit == "Words":
        out, current = [], ""
        for character in text:
            current += character
            if character == " ":
                out.append(current)
                current = ""
        if current:
            out.append(current)
        return out or [text]
    return [text]


def unitProgress(progress, index, count, spread=0.6):
    """
    Where one piece is in the cycle.

    The pieces do not move together: each starts a little later than the one
    before, so the change travels along the line instead of the whole thing
    breathing at once. Wrapped, so the tail is already coming round again as
    the head finishes.
    """
    if count <= 1 or spread <= 0:
        return progress
    return (progress - spread * (index / float(count))) % 1.0


def phaseToProgress(phase, mode, easeIndex):
    """phase 0..1 over the cycle -> 0..1 value used to interpolate the axes."""
    if mode == "Ping-pong":
        p = phase * 2.0 if phase < 0.5 else 2.0 - phase * 2.0
    else:
        p = phase
    p = min(1.0, max(0.0, p))
    return EASINGS[easeIndex][1](p)


# ----------------------------------------------------------------------------
# rendering (CoreText + variations)
# ----------------------------------------------------------------------------

def makeBaseFont(path):
    data = NSData.dataWithContentsOfFile_(path)
    if data is None:
        raise Exception("Can't read the exported font.")
    provider = Quartz.CGDataProviderCreateWithCFData(data)
    cgFont = Quartz.CGFontCreateWithDataProvider(provider)
    if cgFont is None:
        raise Exception("The exported file is not a valid font.")
    return CoreText.CTFontCreateWithGraphicsFont(cgFont, 100.0, None, None)


def fontAxes(baseFont):
    """[{id, tag, name, min, max, default}] from the compiled font."""
    out = []
    axes = CoreText.CTFontCopyVariationAxes(baseFont) or []
    for a in axes:
        a = dict(a)
        ident = int(a.get(CoreText.kCTFontVariationAxisIdentifierKey, 0))
        out.append({
            "id": ident,
            "tag": struct.pack(">I", ident).decode("mac_roman"),
            "name": str(a.get(CoreText.kCTFontVariationAxisNameKey, "")),
            "min": float(a.get(CoreText.kCTFontVariationAxisMinimumValueKey, 0)),
            "max": float(a.get(CoreText.kCTFontVariationAxisMaximumValueKey, 1000)),
            "default": float(a.get(CoreText.kCTFontVariationAxisDefaultValueKey, 0)),
        })
    return out


# A static font has no axes, so its lanes are the two settings it can still
# move: the size, as a share of the size that is set, and the tracking, on top
# of the tracking that is set. Keyed by name rather than by number, so neither
# can ever be taken for an axis on its way to CoreText.
SIZE_LANE = "size"
TRACK_LANE = "track"


def staticLanes():
    """
    The lanes of a font with no axes, laid out the way the axes are.

    Tracking breathes from the start, as a variable font's axes do, so the
    panel opens moving; Size waits for its box to be ticked.
    """
    return [
        {"id": SIZE_LANE, "tag": "SIZE", "name": "Size", "unit": "%",
         "min": 10.0, "max": 300.0, "default": 100.0,
         "from": 100.0, "to": 140.0, "animate": False},
        {"id": TRACK_LANE, "tag": "TRAK", "name": "Tracking", "unit": "",
         "min": -300.0, "max": 1000.0, "default": 0.0,
         "from": 0.0, "to": 200.0, "animate": True},
    ]


def laneKey(ax):
    """What a lane is known by in a project: an axis by its tag, a lane of a
    static font by its own name — "size" is not the SIZE axis a font can have."""
    return ax["id"] if isinstance(ax["id"], str) else ax["tag"]


def shortNumber(value, whole=False):
    """A number the way a field shows it: 62.5 and 200, never 200.0."""
    value = float(value)
    if whole or value.is_integer():
        return "%d" % round(value)
    return repr(value)


def laneShares(values, track):
    """(scale, tracking, axes) out of one frame's lane values: what a static
    font's lanes do to the size and the tracking, and the real axes left."""
    values = dict(values)
    scale = values.pop(SIZE_LANE, 100.0) / 100.0
    return scale, track + values.pop(TRACK_LANE, 0.0), values


def variedFont(baseFont, size, variations):
    # only real axes reach CoreText: the lanes of a static font travel in the
    # same dict, and a name where an axis number belongs is not for it
    axes = dict((k, v) for k, v in dict(variations).items()
                if not isinstance(k, str))
    desc = CoreText.CTFontDescriptorCreateWithAttributes(
        {CoreText.kCTFontVariationAttribute: axes})
    return CoreText.CTFontCreateCopyWithAttributes(baseFont, size, None, desc)


def hexFromNSColor(color):
    c = color.colorUsingColorSpace_(NSColorSpace.sRGBColorSpace())
    return "#%02X%02X%02X" % (round(c.redComponent() * 255),
                              round(c.greenComponent() * 255),
                              round(c.blueComponent() * 255))


def nsColorFromHex(text):
    t = str(text or "").strip().lstrip("#")
    if len(t) == 3:
        t = "".join(ch * 2 for ch in t)
    if len(t) != 6:
        return None
    try:
        r, g, b = (int(t[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return None
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, 1.0)


def cgColorFromNSColor(color):
    """The colour for CoreGraphics, in sRGB: the space its hex is written in.
    It used to be made in Generic RGB, which is another space, and every frame
    came out off the colour picked — #FF4D00 drawn as #FF6500, in the preview
    and in every export."""
    c = color.colorUsingColorSpace_(NSColorSpace.sRGBColorSpace())
    parts = (c.redComponent(), c.greenComponent(), c.blueComponent(),
             c.alphaComponent())
    try:
        return Quartz.CGColorCreateSRGB(*parts)
    except AttributeError:              # before macOS 10.15
        return Quartz.CGColorCreate(
            Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceSRGB), parts)


def _line(txt, ctfont, color, kern=0.0):
    attrs = {CoreText.kCTFontAttributeName: ctfont,
             CoreText.kCTForegroundColorAttributeName: color}
    if kern:
        attrs[CoreText.kCTKernAttributeName] = kern
    astr = NSAttributedString.alloc().initWithString_attributes_(txt, attrs)
    return CoreText.CTLineCreateWithAttributedString(astr)


_BLACK = []          # made on first use: Quartz is not here yet at import


def black():
    if not _BLACK:
        _BLACK.append(cgColorFromNSColor(NSColor.blackColor()))
    return _BLACK[0]


def measureLines(baseFont, lines, variations, track=0.0):
    """Widest line and cap height at 1000 upm, tracking included — and grown
    by a static font's Size lane, so that a fit holds at its largest."""
    scale, track, variations = laneShares(variations, track)
    f = variedFont(baseFont, 1000.0, variations)
    kern = track                    # at 1000 upm a unit per mille is a point
    widest = 0.0
    for txt in lines:
        w = CoreText.CTLineGetTypographicBounds(
            _line(txt, f, black(), kern), None, None, None)[0]
        # CoreText spaces after the last glyph too, and that gap is not part
        # of the line: left in, it would push a fitted line off centre
        widest = max(widest, w - kern)
    return widest * scale, CoreText.CTFontGetCapHeight(f) * scale


# Quanto l'inchiostro puo uscire dal blocco misurato sulle maiuscole senza che
# gli si faccia posto: le rotondita di una O o di un 5 escono di un paio di
# punti per cento dell'altezza delle maiuscole, ed e voluto, cosi sembrano alte
# quanto una H. Discendenti e accenti escono di un quarto o di un terzo: quelli
# si contano, o il fotogramma li taglia.
OVERSHOOT = 0.05


def measureInk(baseFont, lines, variations, track=0.0):
    """How far the ink reaches above the first line's baseline and below the
    last one's, at 1000 upm: accents and ascenders over the caps, descenders
    under the line — what the cap height alone leaves out, and what a frame
    would cut. With the Size lane's growth beside it, for the fit."""
    scale, track, variations = laneShares(variations, track)
    f = variedFont(baseFont, 1000.0, variations)

    def reach(txt):
        box = CoreText.CTLineGetBoundsWithOptions(
            _line(txt, f, black(), track), CoreText.kCTLineBoundsUseGlyphPathBounds)
        top, bottom = box.origin.y + box.size.height, box.origin.y
        if not (math.isfinite(top) and math.isfinite(bottom)):
            return 0.0, 0.0             # a line of spaces has no ink at all
        return max(0.0, top), max(0.0, -bottom)
    if not lines:
        return 0.0, 0.0, scale
    return reach(lines[0])[0], reach(lines[-1])[1], scale


SLIDER_ROW = 0.052       # altezza di una riga di cursore, sul lato corto
SLIDER_WIDTH = 0.50      # quanto del fotogramma occupa il binario
# margine sotto, sul lato corto del fotogramma. Dieci punti piu in alto di
# come stava: la misura e in frazione e non in pixel perche i cursori devono
# cadere allo stesso posto su un export grande come su uno piccolo, e i dieci
# punti sono contati sul lato corto standard da 1080 (0.055 + 10/1080).
SLIDER_BOTTOM = 0.0643
SLIDER_FACE = "Monologo"
SLIDER_FALLBACK = "HelveticaNeue"


def labelFont(size):
    """Monologo per le etichette, e un ripiego dichiarato se non c e.

    Chiedere un carattere che manca non fallisce: CoreText ne mette un altro
    senza dirlo, e il filmato esce con Helvetica dove doveva esserci il
    carattere di casa. Si controlla il nome di quello che e arrivato, invece di
    dare per scontato quello che si e chiesto.
    """
    f = CoreText.CTFontCreateWithName(SLIDER_FACE, size, None)
    try:
        arrivato = str(CoreText.CTFontCopyPostScriptName(f) or "")
    except Exception:
        arrivato = ""
    if SLIDER_FACE.lower() in arrivato.lower():
        return f
    return CoreText.CTFontCreateWithName(SLIDER_FALLBACK, size, None)


def drawSliders(ctx, w, h, sliders, fgColor):
    """The axes as sliders along the foot of the frame, knobs where the frame is.

    Each track spans the axis's own range, so the knob's place says where in
    the axis this frame sits — not merely where in the animation.

    No number beside the knob. A figure changing sixty times a second cannot be
    read, and trying to read it is what pulls the eye off the letterform the
    film is about. The axis is named; where it stands is shown, not spelled.

    Everything is a fraction of the frame, so the same sliders come out right
    on a square for Instagram and on a wide banner.
    """
    if not sliders:
        return
    lato = min(w, h)
    rowH = lato * SLIDER_ROW
    # meta della larghezza, centrato: cosi i cursori restano sotto al testo
    # invece di correre da un bordo all altro
    trackW = w * SLIDER_WIDTH
    edge = (w - trackW) / 2.0
    # Un pixel, sempre: una linea sottile e sottile a qualunque dimensione, e
    # spessarla in proporzione al fotogramma la trasformerebbe in una barra su
    # un export grande. Il pomello resta proporzionale, ed e lui a dire dove sta
    # l asse; il binario e solo la strada.
    thick = 1.0
    knob = rowH * 0.22
    # In frazione e non in pixel: quindici punti sono un margine giusto su un
    # fotogramma piccolo e una linea sottile su uno da millecento, e il filmato
    # si guarda alla sua dimensione, non alla loro. Qui il distacco dal bordo
    # vale poco piu di una riga di cursore, cosi lo spazio sotto ha lo stesso
    # respiro di quello fra una riga e l altra.
    bottom = lato * SLIDER_BOTTOM + knob
    labelSize = rowH * 0.34
    etichetta = labelFont(labelSize)      # una volta, non una per asse

    for i, s in enumerate(reversed(sliders)):
        y = bottom + i * rowH

        # Il binario, in pieno colore. Il tratto percorso dall animazione non
        # si disegna piu: a distinguerlo era una trasparenza, e senza
        # trasparenze sarebbe lo stesso rettangolo disegnato due volte.
        Quartz.CGContextSetFillColorWithColor(ctx, fgColor)
        Quartz.CGContextFillRect(ctx, ((edge, y - thick / 2), (trackW, thick)))

        # il cursore, dove sta questo fotogramma
        span = max(1e-9, s["max"] - s["min"])
        t = (s["value"] - s["min"]) / span
        t = max(0.0, min(1.0, t))
        cx = edge + trackW * t
        Quartz.CGContextFillEllipseInRect(ctx,
            ((cx - knob, y - knob), (knob * 2, knob * 2)))

        # tutto maiuscolo, e un po piu spaziato: una parola corta in capitali
        # senza aria fra le lettere si legge come un blocco
        line = _line(s["name"].upper(), etichetta, fgColor, labelSize * 0.08)
        Quartz.CGContextSetTextPosition(ctx, edge, y + knob * 1.6)
        CoreText.CTLineDraw(line, ctx)


def shrunk(image, w, h):
    """A frame drawn larger, brought back to the canvas. The letters' edges come
    out smooth instead of stepped: on screen the stage already shows the canvas
    smaller than it is, which is why a film could look rougher than its preview.
    Four times the pixels to draw, and nothing to the file's size."""
    ctx = Quartz.CGBitmapContextCreate(
        None, w, h, 8, w * 4, Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceSRGB),
        Quartz.kCGImageAlphaPremultipliedFirst | Quartz.kCGBitmapByteOrder32Little)
    if ctx is None:
        return image
    Quartz.CGContextSetInterpolationQuality(ctx, Quartz.kCGInterpolationHigh)
    Quartz.CGContextDrawImage(ctx, ((0, 0), (w, h)), image)
    return Quartz.CGBitmapContextCreateImage(ctx)


def renderFrame(baseFont, w, h, lines, size, leadPct, variationsAt, progress,
                bgColor, fgColor, align, unit="Whole", track=0.0, sliders=None,
                backdrop=None, zoom=1.0, turn=0.0, bright=0.0, contrast=0.0,
                ink=None):
    cs = Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceSRGB)
    ctx = Quartz.CGBitmapContextCreate(None, int(w), int(h), 8, 0, cs,
                                       Quartz.kCGImageAlphaPremultipliedLast)
    Quartz.CGContextSetShouldAntialias(ctx, True)
    Quartz.CGContextSetShouldSmoothFonts(ctx, False)  # no subpixel: colour fringes
    Quartz.CGContextSetAllowsFontSubpixelPositioning(ctx, True)
    Quartz.CGContextSetFillColorWithColor(ctx, bgColor)
    Quartz.CGContextFillRect(ctx, ((0, 0), (w, h)))
    if backdrop is not None:
        drawCover(ctx, w, h, backdrop, zoom, turn, bright, contrast)
    # A static font's Size lane grows a whole line from its middle, so the
    # block is measured at the size it has now. Pieces grow from the line they
    # stand on instead, and the block keeps its place while they do.
    grown, _, whole = laneShares(variationsAt(progress), track)
    body = size * (grown if unit == "Whole" else 1.0)
    capH = CoreText.CTFontGetCapHeight(variedFont(baseFont, body, whole))
    lead = body * leadPct / 100.0
    # The block is centred on what shows of it: from the caps — or the accents
    # and ascenders, where they stand higher — of the first line down to the
    # descenders of the last. Counted on the caps alone, the descenders hung
    # below the middle and a square frame cut them off. `ink` is how far the
    # ink reaches, per em, the most it does over the whole cycle, so the block
    # doesn't bob as the axes move. An overshoot's worth of it is let out, as
    # it always was: a round letter stays as big as a flat one.
    rise, fall = capH, 0.0
    if ink:
        spill = capH * OVERSHOOT
        rise = max(capH, ink[0] * body - spill)
        fall = max(0.0, ink[1] * body - spill)
    blockH = rise + lead * (len(lines) - 1) + fall
    top = (h + blockH) / 2.0
    margin = w * 0.05

    for i, txt in enumerate(lines):
        pieces = splitUnits(txt, unit)
        # each piece gets its own font at its own point in the cycle, and is
        # laid out after the one before. Whole is a single piece, so it draws
        # exactly as it always did.
        drawn = []
        total = 0.0
        kern = 0.0
        for k, piece in enumerate(pieces):
            scale, tracked, variations = laneShares(
                variationsAt(unitProgress(progress, k, len(pieces))), track)
            # tracking is written per thousand of the em, the way a type
            # designer says it; CoreText wants points
            kern = size * scale * tracked / 1000.0
            line = _line(piece, variedFont(baseFont, size * scale, variations),
                         fgColor, kern)
            wid = CoreText.CTLineGetTypographicBounds(line, None, None, None)[0]
            drawn.append((line, wid))
            total += wid
        total -= kern           # the space after the last glyph of the line

        y = top - rise - i * lead
        if align == "Left":
            x = margin
        elif align == "Right":
            x = w - margin - total
        else:
            x = (w - total) / 2.0
        for line, wid in drawn:
            Quartz.CGContextSetTextPosition(ctx, x, y)
            CoreText.CTLineDraw(line, ctx)
            x += wid

    drawSliders(ctx, w, h, sliders, fgColor)
    return Quartz.CGBitmapContextCreateImage(ctx)


def coverScale(w, h, iw, ih, zoom=1.0, turn=0.0):
    """
    How much to scale a picture of iw x ih to leave no paper showing in a frame
    of w x h, turned by that many degrees, at that zoom.

    Turned, a frame needs more picture: seen from the picture, the frame's
    corners swing out to w·|cos| + h·|sin| across and w·|sin| + h·|cos| down.
    """
    if not iw or not ih:
        return 1.0
    angle = math.radians(turn or 0.0)
    across, down = abs(math.cos(angle)), abs(math.sin(angle))
    need = max((w * across + h * down) / float(iw),
               (w * down + h * across) / float(ih))
    return need * max(0.05, float(zoom or 1.0))


def drawCover(ctx, w, h, image, zoom=1.0, turn=0.0, bright=0.0, contrast=0.0):
    """An image over the whole frame, as large as it takes to leave no paper
    showing and centred: what does not fit is cut off, evenly, at the edges.

    zoom is how much of that size to take: 1 covers the frame and no more,
    above it the picture grows and is cut into, below it the picture shrinks
    and the paper shows round it. turn is degrees, clockwise. bright, from -1
    to 1, lays black or white over the picture — over the picture alone, so
    the paper round it keeps its own colour. contrast, from -1 to 1, drives the
    light and the dark apart or brings them together towards a flat grey."""
    iw, ih = Quartz.CGImageGetWidth(image), Quartz.CGImageGetHeight(image)
    if not iw or not ih:
        return
    scale = coverScale(w, h, iw, ih, zoom, turn)
    dw, dh = iw * scale, ih * scale
    Quartz.CGContextSaveGState(ctx)
    Quartz.CGContextSetInterpolationQuality(ctx, Quartz.kCGInterpolationHigh)
    Quartz.CGContextTranslateCTM(ctx, w / 2.0, h / 2.0)
    if turn:
        # the frame is drawn the way a page is read, so a growing number turns
        # the picture clockwise
        Quartz.CGContextRotateCTM(ctx, -math.radians(turn))
    rect = ((-dw / 2.0, -dh / 2.0), (dw, dh))
    Quartz.CGContextDrawImage(ctx, rect, image)
    hard = max(-1.0, min(1.0, float(contrast or 0.0)))
    if hard > 0:
        # the picture laid over itself: the lights go lighter and the darks
        # darker, by as much as the bar says
        Quartz.CGContextSaveGState(ctx)
        Quartz.CGContextSetBlendMode(ctx, Quartz.kCGBlendModeOverlay)
        Quartz.CGContextSetAlpha(ctx, hard)
        Quartz.CGContextDrawImage(ctx, rect, image)
        Quartz.CGContextRestoreGState(ctx)
    elif hard < 0:
        # towards the middle grey, which at the end of the bar is all there is
        Quartz.CGContextSetRGBFillColor(ctx, 0.5, 0.5, 0.5, -hard)
        Quartz.CGContextFillRect(ctx, rect)
    level = max(-1.0, min(1.0, float(bright or 0.0)))
    if level:
        tone = 1.0 if level > 0 else 0.0
        Quartz.CGContextSetRGBFillColor(ctx, tone, tone, tone, abs(level))
        Quartz.CGContextFillRect(ctx, rect)
    Quartz.CGContextRestoreGState(ctx)


def duotone(image, w, h, dark, light, zoom=1.0, turn=0.0):
    """
    The picture in two colours: its darks in the first, its lights in the
    second, everything between on the way from one to the other — drawn as it
    covers a frame w x h, which is the size it comes back at.

    Quartz does it in two steps: the picture drawn into grey, and the grey read
    through an indexed colour space whose 256 entries run from one colour to
    the other, in sRGB. About 20 ms for a frame of 1920 x 1080.
    """
    w, h = int(w), int(h)
    grey = Quartz.CGBitmapContextCreate(
        None, w, h, 8, w,
        Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceGenericGrayGamma2_2),
        Quartz.kCGImageAlphaNone)
    drawCover(grey, w, h, image, zoom, turn)
    plain = Quartz.CGBitmapContextCreateImage(grey)
    table = bytes(int(round(dark[c] + (light[c] - dark[c]) * i / 255.0))
                  for i in range(256) for c in range(3))
    space = Quartz.CGColorSpaceCreateIndexed(
        Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceSRGB), 255, table)
    return Quartz.CGImageCreate(
        w, h, 8, 8, Quartz.CGImageGetBytesPerRow(plain), space,
        Quartz.kCGImageAlphaNone, Quartz.CGImageGetDataProvider(plain), None,
        False, Quartz.kCGRenderingIntentDefault)


# The backdrop's size, from the bar under it: half way along is 100%, the size
# that just covers the frame. To the left it shrinks to a quarter of that, to
# the right it grows to three times; a hair either side of the middle counts as
# exactly 100%, so the bar has somewhere to rest.
def zoomFromBar(value):
    value = max(0.0, min(1.0, float(value)))
    zoom = 0.25 + 1.5 * value if value <= 0.5 else 1.0 + 4.0 * (value - 0.5)
    return 1.0 if abs(zoom - 1.0) < 0.03 else round(zoom, 2)


def zoomToBar(zoom):
    zoom = max(0.25, min(3.0, float(zoom or 1.0)))
    return (zoom - 0.25) / 1.5 if zoom <= 1.0 else 0.5 + (zoom - 1.0) / 4.0


# The angle, from the bar under it: the middle is upright, each end half a turn
# the other way, and a rest at every quarter so the bar has somewhere to stop.
def turnFromBar(value):
    degrees = round(-180.0 + 360.0 * max(0.0, min(1.0, float(value))), 1)
    for stop in (-180.0, -90.0, 0.0, 90.0, 180.0):
        if abs(degrees - stop) <= 3.0:
            return stop
    return degrees


def turnToBar(turn):
    return (max(-180.0, min(180.0, float(turn or 0.0))) + 180.0) / 360.0


# How fast the video runs, from the bar under it: the middle is its own speed,
# left down to a quarter of it, right up to four times, with a rest at 1x.
def speedFromBar(value):
    value = max(0.0, min(1.0, float(value)))
    if abs(value - 0.5) <= 0.02:            # the rest at its own speed
        return 1.0
    speed = 0.25 + 1.5 * value if value <= 0.5 else 1.0 + 6.0 * (value - 0.5)
    return round(speed, 2)


# Brighter or darker, from the bar under it: the middle leaves the media as it
# is, one end lays white over it, the other black.
def brightFromBar(value):
    value = max(0.0, min(1.0, float(value)))
    if abs(value - 0.5) <= 0.02:
        return 0.0
    return round(-1.0 + 2.0 * value, 2)


def brightToBar(bright):
    return (max(-1.0, min(1.0, float(bright or 0.0))) + 1.0) / 2.0


# How hard the light and the dark of the media stand apart, from the bar under
# it: the middle is the picture as it is, left towards a flat grey, right towards
# black and white.
def contrastFromBar(value):
    value = max(0.0, min(1.0, float(value)))
    if abs(value - 0.5) <= 0.02:
        return 0.0
    return round(-1.0 + 2.0 * value, 2)


def contrastToBar(contrast):
    return (max(-1.0, min(1.0, float(contrast or 0.0))) + 1.0) / 2.0


def speedToBar(speed):
    speed = max(0.25, min(4.0, float(speed or 1.0)))
    return (speed - 0.25) / 1.5 if speed <= 1.0 else 0.5 + (speed - 1.0) / 6.0


def rgbOf(color):
    """An NSColor as three 0-255 numbers, in sRGB."""
    text = hexFromNSColor(color)
    return tuple(int(text[i:i + 2], 16) for i in (1, 3, 5))


# the two colours Colorize starts from: a grey for the darks, a green for the
# lights, as in the tools on the web
TINT_DARK = "#555555"
TINT_LIGHT = "#7CFC4C"

IMAGE_TYPES = ["png", "jpg", "jpeg", "heic", "heif", "tif", "tiff", "gif", "bmp",
               "webp"]
VIDEO_TYPES = ["mov", "mp4", "m4v"]


class Backdrop(object):
    """
    What stands behind the text: a still image, or a video whose frames are
    read one at a time as the film asks for them — about 20 ms a frame, at the
    size of the preview as at the size of the export — so nothing is held but
    the frame in hand.

    A video runs at its own speed from the start of the film and starts over
    when it ends, as in the Kinomat on the web; an MP4 that repeats the cycle
    carries on through the video instead of starting it again.

    Its frames are read in order, by an asset reader: a film asks for them one
    after another, which is what a reader is for. Asked one at a time instead,
    by time, the image generator has to find its way back to a key frame for
    every one of them — 27 ms on a 1080p clip, 47 on a 4K HEVC, 180 on a 4K at
    60 a second, against 6 to 8 ms in order. The generator is still here for
    what a reader cannot do: going back, and clips it will not open.
    """

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.still = None
        self.generator = None
        self.duration = 0.0
        self.rate = 0.0             # the video's own frames a second
        self.natural = None         # the video's picture, upright
        self.raw = None             # and as it is stored, before any turning
        self.spin = 0.0             # the quarter turn it was filmed with, in degrees
        self.size = None            # the last size asked for
        self.last = None            # the last frame read, should one fail
        self.space = None           # the colours the clip says it was filmed in
        self.reader = None          # reading in order, from a moment on
        self.output = None
        self.hold = None            # the frame that stands at the time asked
        self.holdAt = None
        self.ahead = None           # the one after it, already read
        url = NSURL.fileURLWithPath_(path)
        if os.path.splitext(path)[1].lower().lstrip(".") in VIDEO_TYPES:
            self.openVideo(url)
        else:
            self.openImage(url)

    def openImage(self, url):
        source = Quartz.CGImageSourceCreateWithURL(url, None)
        image = None
        if source is not None and Quartz.CGImageSourceGetCount(source):
            # turned the way the camera meant it, and no bigger than an export
            image = Quartz.CGImageSourceCreateThumbnailAtIndex(source, 0, {
                Quartz.kCGImageSourceCreateThumbnailFromImageAlways: True,
                Quartz.kCGImageSourceCreateThumbnailWithTransform: True,
                Quartz.kCGImageSourceThumbnailMaxPixelSize: 4096})
        if image is None:
            raise Exception("%s is not an image Kinomat can read." % self.name)
        self.still = image

    def openVideo(self, url):
        import AVFoundation
        import CoreMedia
        asset = AVFoundation.AVURLAsset.URLAssetWithURL_options_(url, None)
        tracks = asset.tracksWithMediaType_(AVFoundation.AVMediaTypeVideo)
        if not tracks:
            raise Exception("%s is not a video Kinomat can read." % self.name)
        self.duration = float(CoreMedia.CMTimeGetSeconds(asset.duration()) or 0.0)
        self.rate = float(tracks[0].nominalFrameRate() or 0.0)
        self.track = tracks[0]
        natural = tracks[0].naturalSize()
        turn = tracks[0].preferredTransform()
        # a phone held upright films on its side and says so: a quarter turn
        # swaps the sides
        sideways = abs(turn.b) > abs(turn.a)
        self.raw = (float(natural.width), float(natural.height))
        self.natural = (float(natural.height if sideways else natural.width),
                        float(natural.width if sideways else natural.height))
        # the same turn, in degrees: the reader hands the frames over as they
        # are stored, and the turn is added to the angle they are drawn at
        if sideways:
            self.spin = 90.0 if turn.b > 0 else 270.0
        elif turn.a < 0:
            self.spin = 180.0
        else:
            self.spin = 0.0
        generator = AVFoundation.AVAssetImageGenerator.assetImageGeneratorWithAsset_(asset)
        generator.setAppliesPreferredTrackTransform_(True)
        generator.setRequestedTimeToleranceBefore_(CoreMedia.kCMTimeZero)
        generator.setRequestedTimeToleranceAfter_(CoreMedia.kCMTimeZero)
        self.asset, self.generator = asset, generator

    @property
    def moving(self):
        return self.generator is not None

    def frameSize(self, w, h, zoom=1.0, turn=0.0):
        """How large the frames need to come: enough to cover w x h at that
        zoom and that angle, and never more than the video has. Asked of the
        picture as it is stored, since that is what the reader hands over; turn
        is the angle it will be drawn at, the phone's quarter turn included."""
        vw, vh = self.raw or self.natural
        scale = min(1.0, coverScale(w, h, vw, vh, zoom, turn)) if vw and vh else 1.0
        return (int(math.ceil(self.raw[0] * scale)),
                int(math.ceil(self.raw[1] * scale)))

    def startReading(self, at, size):
        """A reader over the video from that moment on, its frames at that size.
        Whether there is one."""
        import AVFoundation
        import CoreMedia
        self.stopReading()
        try:
            reader, error = AVFoundation.AVAssetReader.alloc().initWithAsset_error_(
                self.asset, None)
            if reader is None:
                return False
            output = AVFoundation.AVAssetReaderTrackOutput.alloc().initWithTrack_outputSettings_(
                self.track, {
                    Quartz.kCVPixelBufferPixelFormatTypeKey: Quartz.kCVPixelFormatType_32BGRA,
                    Quartz.kCVPixelBufferWidthKey: size[0],
                    Quartz.kCVPixelBufferHeightKey: size[1]})
            output.setAlwaysCopiesSampleData_(False)
            if not reader.canAddOutput_(output):
                return False
            reader.addOutput_(output)
            reader.setTimeRange_(CoreMedia.CMTimeRangeMake(
                CoreMedia.CMTimeMakeWithSeconds(max(0.0, at - 0.002), 600),
                CoreMedia.kCMTimePositiveInfinity))
            if not reader.startReading():
                return False
        except Exception:
            return False
        self.reader, self.output, self.size = reader, output, size
        self.hold = self.holdAt = self.ahead = None
        return True

    def stopReading(self):
        self.last = None
        if self.reader is not None:
            try:
                self.reader.cancelReading()
            except Exception:
                pass
        self.reader = self.output = None
        self.hold = self.holdAt = self.ahead = None

    def nextFrame(self):
        """The reader's next frame, as (its time, the picture), or (None, None)
        at the end of the clip."""
        import CoreMedia
        try:
            sample = self.output.copyNextSampleBuffer()
        except Exception:
            sample = None
        if sample is None:
            return None, None
        at = float(CoreMedia.CMTimeGetSeconds(
            CoreMedia.CMSampleBufferGetPresentationTimeStamp(sample)))
        buffer = CoreMedia.CMSampleBufferGetImageBuffer(sample)
        if buffer is None:
            return at, None
        # straight from the buffer's own bytes. Core Image did this before, and
        # every image it made stayed in memory for good — 2 MB a frame in the
        # preview, 10 in an export — until Glyphs ran out. A copy of the bytes
        # and CGImageCreate cost a millisecond and are let go of properly.
        Quartz.CVPixelBufferLockBaseAddress(buffer, 1)     # read only
        try:
            width = int(Quartz.CVPixelBufferGetWidth(buffer))
            height = int(Quartz.CVPixelBufferGetHeight(buffer))
            bpr = int(Quartz.CVPixelBufferGetBytesPerRow(buffer))
            data = NSData.dataWithBytes_length_(
                Quartz.CVPixelBufferGetBaseAddress(buffer).as_buffer(bpr * height),
                bpr * height)
            if self.space is None:
                self.space = self.clipColours(buffer)
        finally:
            Quartz.CVPixelBufferUnlockBaseAddress(buffer, 1)
        image = Quartz.CGImageCreate(
            width, height, 8, 32, bpr, self.space,
            Quartz.kCGImageAlphaNoneSkipFirst | Quartz.kCGBitmapByteOrder32Little,
            Quartz.CGDataProviderCreateWithCFData(data), None, False,
            Quartz.kCGRenderingIntentDefault)
        return at, image

    def clipColours(self, buffer):
        """The colours the clip was filmed in, as the decoder hands them over:
        a video is usually BT.709, whose curve is not sRGB's, so taking its
        bytes for sRGB drains the colour a little. Said this way, drawing the
        frame on the canvas converts them — which is what Core Image used to do
        before its images started staying in memory. Asked once for a clip."""
        try:
            attached = Quartz.CVBufferGetAttachments(
                buffer, Quartz.kCVAttachmentMode_ShouldPropagate)
            space = Quartz.CVImageBufferCreateColorSpaceFromAttachments(attached)
            if space is not None:
                return space
        except Exception:
            pass
        return Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceSRGB)

    def byGenerator(self, t, size):
        """One frame by its time, the slow way: for a clip no reader will open."""
        import CoreMedia
        if size != self.size:
            self.generator.setMaximumSize_((float(size[0]), float(size[1])))
            self.size = size
        try:
            got = self.generator.copyCGImageAtTime_actualTime_error_(
                CoreMedia.CMTimeMakeWithSeconds(t, 600), None, None)
            image = got[0] if isinstance(got, tuple) else got
        except Exception:
            image = None
        if image is not None:
            self.last = image
        return image if image is not None else self.last

    def imageAt(self, seconds, w, h, zoom=1.0, turn=0.0):
        """
        The picture for a frame w x h at that zoom, that many seconds into the
        film.

        The reader stands at the frame the film is on; the film asks for the
        next ones, and it hands them over. Going back — the video starting
        over, or the bar dragged — starts a reader at the new moment, which is
        the one thing it costs.
        """
        if self.still is not None:
            return self.still
        t = (seconds or 0.0) % self.duration if self.duration > 0 else 0.0
        size = self.frameSize(w, h, zoom, turn)
        back = self.holdAt is not None and t < self.holdAt - 0.001
        if self.reader is None or size != self.size or back:
            if not self.startReading(t, size):
                return self.byGenerator(t, size)
        while True:
            if self.ahead is not None:
                if self.ahead[0] > t and self.hold is not None:
                    break                     # the next one is still to come
                self.holdAt, self.hold = self.ahead
                self.ahead = None
                continue
            at, picture = self.nextFrame()
            if at is None:                    # the end of the clip
                break
            if picture is None:
                continue
            if self.hold is None or at <= t:
                self.holdAt, self.hold = at, picture
            else:
                self.ahead = (at, picture)
                break
        if self.hold is not None:
            self.last = self.hold
            return self.hold
        return self.byGenerator(t, size)


# ----------------------------------------------------------------------------
# export
# ----------------------------------------------------------------------------

def writeGIF(path, images, fps, count=None):
    """The images can come one at a time, as they are made: then count says how
    many there will be, which the file has to be told before the first."""
    url = NSURL.fileURLWithPath_(path)
    dest = Quartz.CGImageDestinationCreateWithURL(
        url, "com.compuserve.gif", len(images) if count is None else count, None)
    if dest is None:
        raise Exception("Can't create the GIF.")
    Quartz.CGImageDestinationSetProperties(dest, {
        Quartz.kCGImagePropertyGIFDictionary: {Quartz.kCGImagePropertyGIFLoopCount: 0}})
    delay = max(0.02, 1.0 / float(fps))
    props = {Quartz.kCGImagePropertyGIFDictionary: {
        Quartz.kCGImagePropertyGIFDelayTime: delay,
        Quartz.kCGImagePropertyGIFUnclampedDelayTime: delay}}
    for img in images:
        with objc.autorelease_pool():
            Quartz.CGImageDestinationAddImage(dest, img, props)
    return Quartz.CGImageDestinationFinalize(dest)


def writePNG(path, image):
    url = NSURL.fileURLWithPath_(path)
    dest = Quartz.CGImageDestinationCreateWithURL(url, "public.png", 1, None)
    if dest is None:
        raise Exception("Can't write %s." % os.path.basename(path))
    Quartz.CGImageDestinationAddImage(dest, image, None)
    return Quartz.CGImageDestinationFinalize(dest)


def writeMP4(path, images, fps, w, h, wantHEVC=False):
    import AVFoundation
    import CoreMedia
    if os.path.exists(path):
        os.remove(path)
    url = NSURL.fileURLWithPath_(path)
    writer, err = AVFoundation.AVAssetWriter.alloc().initWithURL_fileType_error_(
        url, AVFoundation.AVFileTypeMPEG4, None)
    if writer is None:
        raise Exception("AVAssetWriter: %s" % err)
    codec = getattr(AVFoundation, "AVVideoCodecTypeH264", "avc1")
    hevc = getattr(AVFoundation, "AVVideoCodecTypeHEVC", "hvc1")
    # AVFoundation's default bitrate is far too low: derive it from the pixels
    bitrate = int(min(80e6, max(8e6, w * h * fps * 0.4)))
    # and a finer one for HEVC, which carries the colour at full width
    fine = int(min(160e6, max(16e6, w * h * fps * 1.0)))
    compression = {
        AVFoundation.AVVideoAverageBitRateKey: bitrate,
        AVFoundation.AVVideoMaxKeyFrameIntervalKey: int(fps),
        AVFoundation.AVVideoAllowFrameReorderingKey: True,
    }
    profile = getattr(AVFoundation, "AVVideoProfileLevelH264HighAutoLevel", None)
    if profile:
        compression[AVFoundation.AVVideoProfileLevelKey] = profile
    # What the colours are, said in the file: BT.709 primaries and matrix, which
    # are sRGB's, and sRGB's own curve, the one the frames are drawn with. Left
    # unsaid, a player guesses: QuickTime took the curve for BT.709's and showed
    # every colour a shade lighter than the one picked.
    colours = {
        AVFoundation.AVVideoColorPrimariesKey:
            AVFoundation.AVVideoColorPrimaries_ITU_R_709_2,
        AVFoundation.AVVideoTransferFunctionKey: getattr(
            AVFoundation, "AVVideoTransferFunction_IEC_sRGB",
            AVFoundation.AVVideoTransferFunction_ITU_R_709_2),
        AVFoundation.AVVideoYCbCrMatrixKey:
            AVFoundation.AVVideoYCbCrMatrix_ITU_R_709_2,
    }
    tagged = {
        AVFoundation.AVVideoCodecKey: codec,
        AVFoundation.AVVideoWidthKey: w,
        AVFoundation.AVVideoHeightKey: h,
        AVFoundation.AVVideoCompressionPropertiesKey: compression,
        AVFoundation.AVVideoColorPropertiesKey: colours,
    }
    # the bitrate alone is only a ceiling: on flat colour the encoder settled
    # far below it. Its own top quality, where it takes the setting
    finest = dict(compression)
    finest[AVFoundation.AVVideoQualityKey] = 1.0
    sharp = dict(tagged)
    sharp[AVFoundation.AVVideoCompressionPropertiesKey] = finest
    plain = dict(tagged)
    del plain[AVFoundation.AVVideoColorPropertiesKey]

    # H.264 keeps the colour at half width, which softens the edge of coloured
    # letters — a wider bitrate does nothing for it, a finer codec does: HEVC
    # 4:2:2 at 10 bits carries the colour at full width (the letters' edge
    # measured 1.43 px against 1.32). Taken where the Mac will encode it, and
    # the file plays on Macs, iPhones and Safari; where it will not, or where
    # the film must play anywhere, H.264 is still there underneath.
    def hevcSettings(profile, rate):
        squeeze = dict(compression)
        squeeze[AVFoundation.AVVideoAverageBitRateKey] = rate
        squeeze[AVFoundation.AVVideoQualityKey] = 1.0
        if profile:
            squeeze[AVFoundation.AVVideoProfileLevelKey] = profile
        else:
            squeeze.pop(AVFoundation.AVVideoProfileLevelKey, None)
        out = dict(tagged)
        out[AVFoundation.AVVideoCodecKey] = hevc
        out[AVFoundation.AVVideoCompressionPropertiesKey] = squeeze
        return out

    # H.264 first, and HEVC only when it is asked for. The Mac will encode
    # HEVC whenever it is offered, so putting it first meant every film came
    # out in it \u2014 and a film in HEVC 4:2:2 plays on Macs, iPhones and
    # Safari and nowhere else: not Chrome, not Firefox, not Android, not the
    # places these films are made for. A tenth of a pixel on the edge of a
    # letter is not worth a film that will not open.
    settings, used = plain, "H.264"
    order = ((sharp, "H.264"), (tagged, "H.264"))
    if wantHEVC:
        order = ((hevcSettings("HEVC_Main42210_AutoLevel", fine), "HEVC 4:2:2"),
                 (hevcSettings(None, int(fine * 0.6)), "HEVC")) + order
    for candidate, name in order:
        if writer.canApplyOutputSettings_forMediaType_(
                candidate, AVFoundation.AVMediaTypeVideo):
            settings, used = candidate, name
            break
    winput = AVFoundation.AVAssetWriterInput.assetWriterInputWithMediaType_outputSettings_(
        AVFoundation.AVMediaTypeVideo, settings)
    winput.setExpectsMediaDataInRealTime_(False)
    adaptor = AVFoundation.AVAssetWriterInputPixelBufferAdaptor.\
        assetWriterInputPixelBufferAdaptorWithAssetWriterInput_sourcePixelBufferAttributes_(
            winput, {
                # BGRA is the encoder's own: no conversion on the way in
                Quartz.kCVPixelBufferPixelFormatTypeKey: Quartz.kCVPixelFormatType_32BGRA,
                Quartz.kCVPixelBufferWidthKey: w,
                Quartz.kCVPixelBufferHeightKey: h,
            })
    writer.addInput_(winput)
    writer.startWriting()
    writer.startSessionAtSourceTime_(CoreMedia.CMTimeMake(0, fps))
    cs = Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceSRGB)
    pool = adaptor.pixelBufferPool()
    for i, img in enumerate(images):
        while not winput.isReadyForMoreMediaData():
            time.sleep(0.01)
        # a pool for each frame: the picture, the buffer and everything they
        # brought with them go as soon as the frame is written
        with objc.autorelease_pool():
            res, buf = Quartz.CVPixelBufferPoolCreatePixelBuffer(None, pool, None)
            Quartz.CVPixelBufferLockBaseAddress(buf, 0)
            bpr = Quartz.CVPixelBufferGetBytesPerRow(buf)
            base = Quartz.CVPixelBufferGetBaseAddress(buf).as_buffer(bpr * h)
            ctx = Quartz.CGBitmapContextCreate(
                base, w, h, 8, bpr, cs,
                Quartz.kCGImageAlphaNoneSkipFirst | Quartz.kCGBitmapByteOrder32Little)
            Quartz.CGContextDrawImage(ctx, ((0, 0), (w, h)), img)
            del ctx
            Quartz.CVPixelBufferUnlockBaseAddress(buf, 0)
            adaptor.appendPixelBuffer_withPresentationTime_(buf, CoreMedia.CMTimeMake(i, fps))
            del buf, img
    winput.markAsFinished()
    done = []
    writer.finishWritingWithCompletionHandler_(lambda: done.append(True))
    t0 = time.time()
    while not done and time.time() - t0 < 120:
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))
    return used if writer.status() == 2 else ""  # 2: AVAssetWriterStatusCompleted


# ----------------------------------------------------------------------------
# variable font export from the open document
# ----------------------------------------------------------------------------

TTF_FORMAT = getattr(GlyphsApp, "TTF", "TTF")
INSTANCE_VARIABLE = getattr(GlyphsApp, "INSTANCETYPEVARIABLE", 1)


def isVariable(instance):
    """
    Whether an instance in Font Info is a variable setting.

    Asked of its type, and of the older spelling — a style name for the
    variable font — only where there is no type to ask. In Glyphs 4 every
    static instance carries that name as well, so reading it as the mark of a
    variable setting makes the whole Exports list look variable, and the first
    weight that happens to be ticked gets filmed in place of the setting.
    """
    kind = getattr(instance, "type", None)
    if kind is not None:
        return kind == INSTANCE_VARIABLE
    return bool(getattr(instance, "variableStyleName", None))


def variableSettings(font):
    """Every variable setting in Font Info, in its own order."""
    try:
        return [i for i in font.instances if isVariable(i)]
    except Exception:
        return []


def variableInstance(font, setting=None):
    """
    The document's variable setting, or None.

    A font can hold more than one, and they are not two names for the same
    thing: a family with a stencil axis keeps a Roman setting and a Stencil
    one, each cancelling the other's masters with Disable Masters, because
    the two halves do not interpolate into each other. Taking whichever came
    first meant filming a setting the document does not even export, and the
    lanes the panel offered were that setting's axes rather than the ones the
    font is being made with.

    setting says which one, as its place in variableSettings() or by name.
    The panel asks for it, because a document with several settings is a
    document with several fonts in it, each with its own axes, and only the
    one making them knows which is being worked on. With none asked for, the
    settings that export come first — that tick is how the document says
    which one is being worked on — and among them the order of Font Info
    decides, as it does everywhere else.
    """
    found = variableSettings(font)
    if setting is not None and found:
        if isinstance(setting, int):
            if 0 <= setting < len(found):
                return found[setting]
        else:
            for i in found:
                if str(getattr(i, "name", "") or "") == str(setting):
                    return i
    for i in found:
        if exportsAtAll(i):
            return i
    return found[0] if found else None


def defaultSetting(font):
    """Which setting the panel opens on, as its place in variableSettings():
    the same rule variableInstance() goes by, as a number the panel can hold
    on to. None when the document holds no variable setting at all."""
    found = variableSettings(font)
    for n, i in enumerate(found):
        if exportsAtAll(i):
            return n
    return 0 if found else None


def familyOf(font, instance):
    """The family name the instance's font goes out under: its own override,
    what it prefers to be called, or the document's family."""
    for attr in ("familyName", "preferredFamily"):
        try:
            value = getattr(instance, attr, None)
            if callable(value):
                value = value()
        except Exception:
            value = None
        if value:
            return str(value)
    try:
        for pr in instance.properties:
            if str(pr.key) in ("familyNames", "preferredFamilyNames"):
                values = list(getattr(pr, "values", None) or [])
                if values:
                    return str(values[0].value)
    except Exception:
        pass
    return str(getattr(font, "familyName", "") or "")


def settingLabels(font, plain=False):
    """
    A name for each variable setting, for the panel to offer.

    The name Font Info gives it, and the family in front of it where the
    settings do not all make the same one: a document can hold a Serif and a
    Sans over the same masters, and then two of its four settings are both
    called Italic, which says nothing about which is which.

    No two of them may read the same. AppKit throws out a popup item whose
    title is already in the menu, and a setting missing from the list cannot
    be chosen at all — four settings, two of them Italic, offered three.

    A setting left unticked in Font Info is named as such and still films:
    the panel shows the font being made, and that includes one being tried
    out. plain leaves that mark off, for the title bar.
    """
    found = variableSettings(font)
    families = [familyOf(font, i) for i in found]
    together = len(set(families)) < 2          # one family: it goes unsaid
    out = []
    for n, i in enumerate(found):
        name = str(getattr(i, "name", "") or "")
        family = "" if together else families[n]
        if not family:
            label = name or "Setting %d" % (n + 1)
        elif not name or name.lower() == "regular":
            label = family                     # the family's own upright
        elif name.lower().startswith(family.lower()):
            label = name                       # the name says the family
        else:
            label = "%s %s" % (family, name)
        if not plain and not exportsAtAll(i):
            label = "%s (not exported)" % label
        out.append(label)
    seen = {}
    for n, label in enumerate(out):
        while label in seen:
            seen[label] += 1
            label = "%s (%d)" % (out[n], seen[out[n]])
        seen[label] = 1
        out[n] = label
    return out


def settingName(font, setting=None):
    """The name of the variable setting being filmed, worth saying only when
    the document holds more than one to choose between."""
    labels = settingLabels(font, plain=True)
    if len(labels) < 2:
        return ""
    if isinstance(setting, int) and 0 <= setting < len(labels):
        return labels[setting]
    chosen = variableInstance(font, setting)
    return str(getattr(chosen, "name", "") or "") if chosen else ""


def lookedAt(font):
    """(id, name) of the master in front — the one the edit view shows — or of
    the first master when there is no view to ask."""
    master = None
    try:
        master = font.selectedFontMaster
    except Exception:
        master = None
    if master is None:
        try:
            master = font.masters[0]
        except Exception:
            return None, ""
    return str(master.id), str(getattr(master, "name", "") or "")


def variableDesign(font):
    """
    Whether the masters make a space a variable font can be built from: two
    at least, each on a place of its own.

    Not every document with masters is one. Masters kept as separate styles —
    a Caps and a Cyrillic beside the Regular, all near 400 — share a place,
    and there is no varying between two masters on the same spot: waiting
    seconds for an export to fail and say so helps no one. When the places
    cannot be read, the export is tried and its failure caught.
    """
    try:
        masters = list(font.masters)
    except Exception:
        return True
    if len(masters) < 2:
        return False
    places = []
    for master in masters:
        try:
            proxy = getattr(master, "internalAxesValues", None)
            if proxy is None:
                proxy = master.axes
            values = proxy.values() if hasattr(proxy, "values") else list(proxy)
            places.append(tuple(round(float(v), 3) for v in values))
        except Exception:
            return True
    return len(set(places)) == len(places)


def exportsAtAll(instance):
    value = getattr(instance, "exports", None)
    if value is None:
        value = getattr(instance, "active", True)
    return bool(value)


def onlyMaster(instance, master):
    """Whether the instance is that master and nothing else: all of its weight
    on it, none on any other."""
    try:
        weights = dict(instance.instanceInterpolations or {})
    except Exception:
        return False
    found = False
    for key, value in weights.items():
        value = float(value)
        if str(key) == master:
            if abs(value - 1.0) > 1e-6:
                return False
            found = True
        elif abs(value) > 1e-6:
            return False
    return found


def staticInstance(font, master):
    """
    The static instance to export for a master: the first that exports and is
    that master and nothing else, or None.

    Such an instance carries what Font Info gives it — filters, parameters,
    features brought up to date — so the film shows the font as it goes out,
    not the bare master. With none, a temporary instance is pinned to it.
    """
    for i in font.instances:
        if isVariable(i):
            continue
        if exportsAtAll(i) and onlyMaster(i, master):
            return i
    return None


def pinToMaster(instance, master):
    """Make a temporary instance exactly one master — by its interpolation,
    not by its place on the axes: masters kept as separate styles can share a
    place, and a shared place does not say which of them is meant."""
    try:
        instance.manualInterpolation = True
        instance.instanceInterpolations = {master: 1.0}
    except Exception:
        pass


# ----------------------------------------------------------------------------
# only the glyphs the film needs
# ----------------------------------------------------------------------------

def openingText(font):
    """What the box says when the panel opens: the font's own name, which is
    what you want to look at first."""
    return font.familyName or "Kinomat"


def codesOf(glyph):
    """The characters a glyph is for, as numbers."""
    try:
        values = glyph.unicodes
    except Exception:
        values = None
    if not values:
        try:
            values = [glyph.unicode] if glyph.unicode else []
        except Exception:
            values = []
    codes = []
    for value in values:
        try:
            codes.append(int(str(value), 16))
        except ValueError:
            pass
    return codes


def glyphParts(glyph):
    """(names, bracketed): the glyphs its components point to, on any of its
    layers, and whether it has an alternate layer for a part of the design
    space — which goes out as a glyph of its own, named at the export."""
    names, bracketed = set(), False
    try:
        layers = list(glyph.layers)
    except Exception:
        return names, bracketed
    for layer in layers:
        try:
            alternate = layer.isBracketLayer
            if callable(alternate):
                alternate = alternate()
            bracketed = bracketed or bool(alternate)
        except Exception:
            pass
        try:
            components = list(layer.components)
        except Exception:
            continue
        for component in components:
            try:
                name = component.componentName
            except Exception:
                name = None
            if name:
                names.add(str(name))
    return names, bracketed


def neededGlyphs(font, letters):
    """
    What a film of those letters needs from the document, as (names, codes,
    total): the glyphs to export, the characters the compiled font must then
    have, and how many glyphs the whole font exports. None when the document
    cannot be read that way — and the whole font goes out, as it always has.

    The names: the glyphs the letters are drawn with, what those are built
    from, and the glyphs with no unicode — ligatures, alternates, the ones only
    the features reach — so the features the preview runs work as they do in
    the whole font. Of those, only the ones that plainly belong to other
    letters stay out: no a.ss01 and no f_f_i in a film without an a or an f.
    An alternate layer for a part of the design space takes the whole font:
    it goes out as a glyph of its own, named at the export, and a list written
    beforehand cannot be sure to name it.
    """
    try:
        glyphs = list(font.glyphs)
    except Exception:
        return None
    cmap, unencoded, exporting = {}, [], {}
    for glyph in glyphs:
        try:
            if not glyph.export:
                continue
            name = str(glyph.name)
        except Exception:
            continue
        exporting[name] = glyph
        codes = codesOf(glyph)
        for code in codes:
            cmap.setdefault(code, name)
        if not codes:
            unencoded.append(name)
    if not exporting:
        return None
    codes, drawn = set(), set()
    for letter in set(letters) | set(" "):
        code = ord(letter)
        if code in cmap:
            codes.add(code)
            drawn.add(cmap[code])
    names = set(drawn)
    encoded = set(cmap.values())
    for name in unencoded:
        parts = [part for part in name.split(".")[0].split("_") if part]
        if parts and all(part in encoded for part in parts) \
                and not any(part in drawn for part in parts):
            continue
        names.add(name)
    # what they are built from, and what that is built from in turn; a
    # component of a glyph that does not export is drawn into the glyph anyway
    waiting, closed = list(names), set()
    while waiting:
        name = waiting.pop()
        if name in closed or name not in exporting:
            continue
        closed.add(name)
        parts, bracketed = glyphParts(exporting[name])
        if bracketed:
            return None
        waiting.extend(parts)
    return frozenset(closed), frozenset(codes), len(exporting)


def keepOnly(instance, font, names):
    """
    A copy of the instance that exports only the glyphs named, or None.

    The copy carries all Font Info gives the instance — its place, its
    parameters, the features brought up to date — and the list is the copy's
    alone: it never joins the document, so nothing there changes. An instance
    that keeps a list of its own already is left to go out as it is.
    """
    try:
        if instance.customParameters["Keep Glyphs"] is not None:
            return None
        twin = instance.copy()
        if twin is None or getattr(twin, "type", None) != getattr(instance, "type", None):
            return None
        twin.font = font
        twin.customParameters["Keep Glyphs"] = sorted(names)
        return twin
    except Exception:
        return None


def covers(path, codes):
    """Whether the font exported to path has a glyph for every one of those
    characters."""
    try:
        have = CoreText.CTFontCopyCharacterSet(makeBaseFont(path))
        return all(have.longCharacterIsMember_(code) for code in codes)
    except Exception:
        return False


CACHE_FOLDER = os.path.join(tempfile.gettempdir(), "Kinomat")
CACHE_KEY_FILE = os.path.join(CACHE_FOLDER, "cache.key")
def cacheKey(font):
    """
    Identifies the current state of the document, or None if it can't.

    An unsaved edit used to void the cache outright, so the panel exported the
    variable font again every single time it opened — which is most of the
    time, because you are usually mid-edit. An NSDocument counts its own
    changes: same file, same modification date, same count, same outlines,
    saved or not. Both are in the key, so whichever moves first invalidates it.
    """
    try:
        path = font.filepath
        if not path or not os.path.exists(path):
            return None            # untitled: nothing stable to key on
        parent = font.parent
        try:
            changes = int(parent.changeCount())
        except Exception:
            # no counter to read: back to the old rule, which is only ever
            # right when the document is saved
            if parent.isDocumentEdited():
                return None
            changes = "saved"
        return "%s|%s|%s|%s" % (path, os.path.getmtime(path), changes,
                                font.familyName)
    except Exception:
        return None


def fontKey(font, master=None, setting=None):
    """The cache key, marked for a static font with the master it is of and
    for a variable font with the setting it is of: a document that becomes a
    design space, turns to another master, or is filmed from another of its
    variable settings must not be handed an export made for something else."""
    key = cacheKey(font)
    if not key:
        return key
    if master:
        return "%s|static|%s" % (key, master)
    if setting is not None:
        return "%s|vf|%s" % (key, setting)
    return key


def cachedFont(font, master=None, needed=None, setting=None):
    """
    A font already exported for this exact document state, as (path, kept):
    the variable font, or with a master the static font of that master. kept
    names the glyphs in it, None when it is the whole font. (None, None) when
    there is none, or when it is a part of the font without all that is
    needed — as neededGlyphs() gives it, None for the whole font.
    """
    key = fontKey(font, master, setting)
    if not key or not os.path.exists(CACHE_KEY_FILE):
        return None, None
    try:
        lines = open(CACHE_KEY_FILE).read().split("\n")
        stored, path = lines[0], lines[1]
    except (IndexError, OSError):
        return None, None
    if stored != key or not os.path.exists(path):
        return None, None
    # a third line names what went out; with none — an export from before
    # there were parts — it is the whole font
    kept = None
    if len(lines) > 2 and lines[2].strip() not in ("", "*"):
        kept = frozenset(lines[2].split())
    if kept is not None and (needed is None or not needed[0] <= kept):
        return None, None
    return path, kept


def _generate(font, folder, master=None, keep=None, setting=None):
    """One export attempt. Returns (path, error). Nothing about the document is
    touched: an earlier version lent private-use codepoints to the glyphs that
    have none, so the cycle could show components too, and that both slowed the
    export down and wrote — briefly — into the user's own font.

    master: the static font of that master instead of the variable font — for
    a document with nothing to vary, or that cannot be varied.
    keep: only the glyphs named go out. The instance in Font Info never carries
    the list: a copy of it does, or the temporary instance when there is none.
    When neither can, nothing is exported and the error says why."""
    static = master is not None
    instance = (staticInstance(font, master) if static
                else variableInstance(font, setting))
    temporary = False
    if instance is not None and keep is not None:
        instance = keepOnly(instance, font, keep)
        if instance is None:
            return None, "The instance cannot export a part of the font."
    elif instance is None:
        instance = GSInstance()
        instance.name = "Kinomat"
        if not static:
            # Glyphs 4 refuses `instance.type = \u2026`: the property has no
            # setter, it raises, and the older spelling underneath leaves the
            # instance single \u2014 which exports a static font. The panel
            # then offered Size and Tracking where the font's own axes should
            # have been, to anyone whose document has no variable setting of
            # its own in Exports. setType_ is the one that takes.
            try:
                instance.setType_(INSTANCE_VARIABLE)
            except Exception:
                try:
                    instance.type = INSTANCE_VARIABLE
                except (AttributeError, TypeError):
                    instance.variableStyleName = "Regular"
        if keep is not None:
            try:
                instance.customParameters["Keep Glyphs"] = sorted(keep)
            except Exception as trouble:
                return None, "No part of the font: %s" % trouble
        font.instances.append(instance)
        temporary = True
        if static:
            pinToMaster(instance, master)

    # Glyphs 3 and 4: generate(format, fontPath=FOLDER, autoHint).
    # On a variable instance the format is forced to variable TrueType.
    error = None
    try:
        try:
            error = instance.generate(format=TTF_FORMAT, fontPath=folder, autoHint=False)
        except TypeError:
            error = instance.generate(TTF_FORMAT, folder, False)
    except Exception as trouble:
        error = str(trouble)
    finally:
        if temporary:
            del font.instances[len(font.instances) - 1]

    path = getattr(instance, "lastExportedFilePath", None)
    if not path or not os.path.exists(path):
        try:
            fonts = [os.path.join(folder, f) for f in os.listdir(folder)
                     if f.lower().endswith((".ttf", ".otf"))]
            path = max(fonts, key=os.path.getmtime) if fonts else None
        except OSError:
            path = None
    return (path if path and os.path.exists(path) else None), error


def clearFolder(folder):
    """An empty folder to export into, made when it is not there."""
    if not os.path.exists(folder):
        os.makedirs(folder)
        return
    for f in os.listdir(folder):
        try:
            os.remove(os.path.join(folder, f))
        except OSError:
            pass


def emptyCache():
    """
    The temporary folder gone, and the fonts exported into it with it: when a
    panel closes, and when Glyphs quits. An export is a copy of a font in the
    making, with no business lying about once nothing shows it; the next panel
    exports again, a part of the font, which is quick.
    """
    import shutil
    shutil.rmtree(CACHE_FOLDER, ignore_errors=True)


def exportFont(font, master=None, needed=None, setting=None):
    """
    Export the font to a temporary folder, as (path, kept): the variable font,
    or with a master the static font of that master.

    needed, as neededGlyphs() gives it: only those glyphs go out, and a part of
    the font takes a part of the time. When that cannot be done — the instance
    cannot be copied, the export fails, the font that comes out lacks a
    character it was asked for — the whole font goes out instead, as it always
    has. kept names the glyphs that went out, None for the whole font.
    """
    folder = CACHE_FOLDER
    clearFolder(folder)

    path, error, kept = None, None, None
    if needed is not None:
        path, error = _generate(font, folder, master, needed[0], setting)
        if path and not covers(path, needed[1]):
            path, error = None, "Characters it was asked for are not in it."
        if path:
            kept = frozenset(needed[0])
        else:
            print("Kinomat \u2014 the whole font, not a part of it:\n%s"
                  % (error or "Nothing came out."))
            clearFolder(folder)
    if not path:
        path, error = _generate(font, folder, master, None, setting)

    if not path:
        if master is not None:
            raise Exception("Font export failed.\n%s"
                            % (error or "Check that the document exports "
                                        "in Font Info ▸ Exports."))
        raise Exception("Variable font export failed.\n%s"
                        % (error or "Check that the document has a variable "
                                    "instance in Font Info ▸ Exports."))

    key = fontKey(font, master, setting)
    if key:
        try:
            with open(CACHE_KEY_FILE, "w") as f:
                f.write("%s\n%s\n%s" % (key, path, "*" if kept is None
                                         else " ".join(sorted(kept))))
        except OSError:
            pass
    return path, kept


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# design tokens
# ----------------------------------------------------------------------------

def tone(text, alpha=1.0):
    """A token colour from its hex, in sRGB so it lands on the design's value."""
    v = text.lstrip("#")
    r, g, b = (int(v[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, alpha)


ACCENT = tone("#FF4D00")
ACCENT_DOWN = tone("#E64500")
ACCENT_TEXT = tone("#D63F00")
ACCENT_TINT = tone("#FF4D00", 0.10)
ACCENT_RANGE = tone("#FF4D00", 0.35)
# the traffic light's green, held down just enough to read at 12pt on the
# light sidebar — and its tint, the way the accent has one
GREEN_TEXT = tone("#23B843")
GREEN_TINT = tone("#23B843", 0.12)

SURF_SIDE = tone("#F7F7F9")
SURF_STAGE = tone("#EFEFF2")
SURF_FIELD = tone("#FFFFFF")
SURF_BAR_TOP = tone("#FDFDFE")
SURF_BAR_BOTTOM = tone("#F2F2F4")
SURF_WINDOW = tone("#FBFBFC")
SURF_SEGMENT = tone("#EAEAEE")
DOT = tone("#DCDCE2")

LINE_FIELD = tone("#D6D6DC")
LINE_ZONE = tone("#E2E2E6")
LINE_DIVIDER = tone("#E4E4E8")

INK = tone("#1A1A1C")
INK_BUTTON = tone("#2A2A30")
INK_NAME = tone("#3A3A40")
INK_CHIP = tone("#4A4A50")
INK_LABEL = tone("#5A5A60")
INK_TIME = tone("#6A6A70")
INK_STATUS = tone("#8A8A90")
INK_MUTED = tone("#96969C")
INK_FAINT = tone("#B0B0B6")

TRACK = tone("#DEDEE3")
TRACK_OFF = tone("#D2D2D8")
HANDLE_OFF = tone("#B8B8BE")

UI_ACCENT = ACCENT

# The panel: two columns of settings, the stage beside them, and under both
# the transport, the lanes and the export bar, the whole width.
#
# It is a rectangle, 16:9, the shape of what it makes. It used to be one tall
# column of settings and stood 969 points high, which is more than a MacBook
# Air has: the export bar fell off the bottom of the screen. The settings are
# in two columns now, so the panel is as wide as a film and never taller than
# the screen it opens on.
COL_W = 296                          # one column of settings
SIDE_W = COL_W * 2                   # the two of them, side by side
GUTTER = 16                          # a column's own padding
LABEL_W = 56                         # the right-aligned label column
FIELD_X = GUTTER + LABEL_W + 10
FIELD_W = COL_W - GUTTER - FIELD_X
ZONE_PAD = 18                        # left and right of the lanes and the bar
FIELD_H = 24
POPUP_H = 22
LANE_H = 34
EXPORT_H = 52
SIDE_H = 437                         # the taller column, CANVAS, with its
                                     # margin: the settings never have less
                                     # room than this
MOTION_H = 199                       # MOTION, in the left column beside the
                                     # lanes: the band is never shorter
WIN_RATIO = 16.0 / 9.0
WIN_MAX_W = 1440                     # on a large screen it stops growing here
WIN_MIN_W = SIDE_W + 520             # and the stage is never narrower than this
CANVAS_MAX_W, CANVAS_MAX_H = 620, 470
UI_SCALE = 0.8                       # the whole panel is laid out at full size
                                     # and drawn four fifths of it: it came out
                                     # too large on the screen, and one
                                     # transform is truer than nine hundred
                                     # smaller numbers in the layout


def drawSmaller(window, design):
    """
    The window taken in to UI_SCALE, with everything in it still laid out at
    full size.

    The content view's own unit is made smaller, so a point of the layout is
    four fifths of a point on the screen: type, fields, sliders, lanes and the
    picture all come out the same amount smaller, and every number in the
    layout stays the round one it was. AppKit carries the scale into the
    drawing and into where the mouse lands, the way a scroll view's
    magnification does.

    It happens last, once everything is built and never before: vanilla places
    a control by flipping it against the height the window has at that moment,
    so the window has to stand at its full size while the pieces are made. The
    subviews are held still while the frame comes in — their own frames are
    right already, and it is the view under them that changes scale.
    """
    try:
        view = window.contentView()
        frame = window.frame()
        corner = (frame.origin.x, frame.origin.y + frame.size.height)
        view.setAutoresizesSubviews_(False)
        view.scaleUnitSquareToSize_((UI_SCALE, UI_SCALE))
        window.setContentSize_((int(round(design[0] * UI_SCALE)),
                                int(round(design[1] * UI_SCALE))))
        view.setAutoresizesSubviews_(True)
        # a window keeps its bottom left corner when it is resized: it would
        # come in from the top, and open lower than it was put
        window.setFrameTopLeftPoint_(corner)
        # and it is still a window that cannot be resized, at its new size
        window.setMinSize_(window.frame().size)
        window.setMaxSize_(window.frame().size)
    except Exception:
        pass


def windowSize(laneH):
    """
    How large the panel opens: 16:9, inside the screen it is opening on.

    In the layout's own points, which are UI_SCALE of the screen's: the shape
    is asked for first — the rectangle of a film — and then cut down to what
    the screen has room for, the menu bar and the Dock already taken off by
    visibleFrame. What stands in the panel sets the floor: the taller column of
    settings, and the lanes and the bar under it.
    """
    availW, availH = 1440.0, 800.0
    try:
        visible = NSScreen.mainScreen().visibleFrame()
        availW = float(visible.size.width) - 24
        availH = float(visible.size.height) - 52      # the title bar, and air
    except Exception:
        pass
    availW, availH = availW / UI_SCALE, availH / UI_SCALE
    w = min(float(WIN_MAX_W), availW)
    h = w / WIN_RATIO
    if h > availH:                                    # too tall: take the width
        h, w = availH, availH * WIN_RATIO
    w = max(float(WIN_MIN_W), min(w, availW))
    h = max(h, SIDE_H + laneH + EXPORT_H)
    return int(round(w)), int(round(h))


def uiFont(size, weight=None):
    if weight is None:
        return NSFont.systemFontOfSize_(size)
    return NSFont.systemFontOfSize_weight_(size, weight)


def attributed(text, font, colour, kern=None, align=None, baseline=None):
    attrs = {NSFontAttributeName: font, NSForegroundColorAttributeName: colour}
    if kern:
        attrs[NSKernAttributeName] = kern
    if baseline:
        attrs[NSBaselineOffsetAttributeName] = baseline
    if align is not None:
        style = NSMutableParagraphStyle.alloc().init()
        style.setAlignment_(align)
        attrs[NSParagraphStyleAttributeName] = style
    return NSAttributedString.alloc().initWithString_attributes_(text, attrs)


def textWidth(text, font):
    return NSAttributedString.alloc().initWithString_attributes_(
        text, {NSFontAttributeName: font}).size().width


def symbol(name):
    """SF Symbol image for the alignment and transport controls."""
    try:
        return NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
    except Exception:
        return None


# ----------------------------------------------------------------------------
# the three views AppKit has no control for
# ----------------------------------------------------------------------------

try:  # re-running the script reuses the class already registered with ObjC
    RSZCinemaStageV1 = objc.lookUpClass("RSZCinemaStageV1")
except Exception:
    class RSZCinemaStageV1(NSView):
        """The ground the canvas floats on: flat grey, a dot every 14 points."""

        def drawRect_(self, rect):
            SURF_STAGE.set()
            NSBezierPath.fillRect_(rect)
            DOT.set()
            bounds = self.bounds()
            y = 6.0
            while y < bounds.size.height:
                x = 6.0
                while x < bounds.size.width:
                    NSBezierPath.bezierPathWithOvalInRect_(
                        ((x, y), (1.6, 1.6))).fill()
                    x += 14.0
                y += 14.0

StageBack = RSZCinemaStageV1


try:
    RSZCinemaCheckV1 = objc.lookUpClass("RSZCinemaCheckV1")
except Exception:
    class RSZCinemaCheckV1(NSView):
        """
        A checkbox in the accent colour.

        AppKit will not tint one: a checkbox follows the accent colour set in
        System Settings and takes no colour of its own, so a panel that wants
        its own accent has to draw the box itself.
        """

        def initWithFrame_(self, frame):
            self = objc.super(RSZCinemaCheckV1, self).initWithFrame_(frame)
            if self is None:
                return None
            self.on = True
            self.label = ""
            self.callback = None
            return self

        def drawRect_(self, rect):
            mid = self.frame().size.height / 2.0
            box = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                ((0.5, mid - 6.5), (13, 13)), 3.5, 3.5)
            if self.on:
                ACCENT.set()
                box.fill()
                tick = NSBezierPath.bezierPath()
                tick.moveToPoint_((4.0, mid - 0.1))
                tick.lineToPoint_((6.2, mid - 2.6))
                tick.lineToPoint_((10.3, mid + 2.9))
                tick.setLineWidth_(1.7)
                tick.setLineCapStyle_(1)
                tick.setLineJoinStyle_(1)
                NSColor.whiteColor().set()
                tick.stroke()
            else:
                SURF_FIELD.set()
                box.fill()
                LINE_FIELD.set()
                box.setLineWidth_(1.0)
                box.stroke()
            if self.label:
                attributed(self.label, uiFont(12), INK_NAME).drawAtPoint_(
                    (19, mid - 7.5))

        def mouseDown_(self, event):
            self.on = not self.on
            self.setNeedsDisplay_(True)
            if self.callback:
                self.callback(self)

Check = RSZCinemaCheckV1


try:
    RSZCinemaFieldBoxV1 = objc.lookUpClass("RSZCinemaFieldBoxV1")
except Exception:
    class RSZCinemaFieldBoxV1(NSView):
        """
        The white box behind a field.

        The field inside it is one line tall and inset seven points, because
        AppKit cannot centre text in a taller field. That leaves a margin that
        looks like the field and is not: clicking it did nothing at all. This
        catches those clicks and hands them to the field, selecting what is
        there — which is what you want in a box holding one number.
        """

        def initWithFrame_(self, frame):
            self = objc.super(RSZCinemaFieldBoxV1, self).initWithFrame_(frame)
            if self is None:
                return None
            self.field = None
            return self

        def mouseDown_(self, event):
            if self.field is None or self.window() is None:
                return
            self.window().makeFirstResponder_(self.field)
            editor = self.field.currentEditor()
            if editor is not None:
                editor.selectAll_(None)

FieldBox = RSZCinemaFieldBoxV1


# ----------------------------------------------------------------------------
# the axis lane: one track, two diamonds and the live value
# ----------------------------------------------------------------------------

HANDLE = 11.0          # the width across the corners, not the side
INSET = HANDLE / 2.0


def diamondPath(x, y, size):
    path = NSBezierPath.bezierPath()
    half = size / 2.0
    path.moveToPoint_((x, y - half))
    path.lineToPoint_((x + half, y))
    path.lineToPoint_((x, y + half))
    path.lineToPoint_((x - half, y))
    path.closePath()
    return path


try:
    RSZCinemaRangeSliderV5 = objc.lookUpClass("RSZCinemaRangeSliderV5")
except Exception:
    class RSZCinemaRangeSliderV5(NSView):

        def initWithFrame_(self, frame):
            self = objc.super(RSZCinemaRangeSliderV5, self).initWithFrame_(frame)
            if self is None:
                return None
            self.mn, self.mx = 0.0, 1.0
            self.lo, self.hi = 0.0, 1.0
            self.animating = True
            self.playhead = None
            self.callback = None
            self.dragging = None
            return self

        @objc.python_method
        def width(self):
            return self.frame().size.width

        @objc.python_method
        def xFor(self, value):
            span = (self.mx - self.mn) or 1.0
            t = (value - self.mn) / span
            return INSET + t * (self.width() - INSET * 2)

        @objc.python_method
        def valueFor(self, x):
            span = self.width() - INSET * 2
            t = 0.0 if span <= 0 else (x - INSET) / span
            t = min(1.0, max(0.0, t))
            return self.mn + t * (self.mx - self.mn)

        def drawRect_(self, rect):
            mid = self.frame().size.height / 2.0
            xLo, xHi = self.xFor(self.lo), self.xFor(self.hi)

            TRACK.set()
            NSBezierPath.fillRect_(((0, mid - 0.5), (self.width(), 1)))

            (ACCENT_RANGE if self.animating else TRACK_OFF).set()
            NSBezierPath.fillRect_(
                ((min(xLo, xHi), mid - 0.5), (abs(xHi - xLo), 1)))

            if self.animating and self.playhead is not None:
                x = self.xFor(self.playhead)
                ACCENT.set()
                NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                    ((x - 1, mid - 9), (2, 18)), 1, 1).fill()

            edge = ACCENT if self.animating else HANDLE_OFF
            for which, x in (("lo", xLo), ("hi", xHi)):
                path = diamondPath(x, mid, HANDLE)
                # the one under the hand fills, so it is plain which of the two
                # is moving
                (ACCENT if self.dragging == which else SURF_FIELD).set()
                path.fill()
                edge.set()
                path.setLineWidth_(1.5)
                path.stroke()

        def mouseDown_(self, event):
            x = self.convertPoint_fromView_(event.locationInWindow(), None).x
            # whichever handle is nearer is the one being dragged
            self.dragging = "lo"
            if abs(x - self.xFor(self.hi)) < abs(x - self.xFor(self.lo)):
                self.dragging = "hi"
            self.mouseDragged_(event)

        def mouseDragged_(self, event):
            if not self.dragging:
                return
            x = self.convertPoint_fromView_(event.locationInWindow(), None).x
            value = self.valueFor(x)
            if self.dragging == "lo":
                self.lo = value
            else:
                self.hi = value
            self.setNeedsDisplay_(True)
            if self.callback:
                self.callback(self)

        def mouseUp_(self, event):
            self.dragging = None
            self.setNeedsDisplay_(True)

RangeSlider = RSZCinemaRangeSliderV5


try:
    RSZCinemaScrubberV4 = objc.lookUpClass("RSZCinemaScrubberV4")
except Exception:
    class RSZCinemaScrubberV4(NSView):
        """The playhead: a 4pt track, filled to where the animation has got to."""

        def initWithFrame_(self, frame):
            self = objc.super(RSZCinemaScrubberV4, self).initWithFrame_(frame)
            if self is None:
                return None
            self.value = 0.0
            self.grabbed = False
            self.callback = None
            return self

        @objc.python_method
        def width(self):
            return self.frame().size.width - 10.0

        @objc.python_method
        def xFor(self, value):
            return 5.0 + self.width() * max(0.0, min(1.0, value))

        @objc.python_method
        def valueFor(self, x):
            return max(0.0, min(1.0, (x - 5.0) / max(1.0, self.width())))

        def drawRect_(self, rect):
            mid = self.frame().size.height / 2.0
            full = self.frame().size.width
            TRACK.set()
            NSBezierPath.fillRect_(((0, mid - 0.5), (full, 1)))
            x = self.xFor(self.value)
            ACCENT.set()
            NSBezierPath.fillRect_(((0, mid - 0.5), (x, 1)))
            head = NSBezierPath.bezierPathWithOvalInRect_(
                ((x - 5, mid - 5), (10, 10)))
            (ACCENT if self.grabbed else SURF_FIELD).set()
            head.fill()
            ACCENT.set()
            head.setLineWidth_(2.0)
            head.stroke()

        def mouseDown_(self, event):
            self.grabbed = True
            self.dragTo_(event)

        def mouseDragged_(self, event):
            self.dragTo_(event)

        def mouseUp_(self, event):
            self.grabbed = False
            self.setNeedsDisplay_(True)

        def dragTo_(self, event):
            point = self.convertPoint_fromView_(event.locationInWindow(), None)
            self.value = self.valueFor(point.x)
            self.setNeedsDisplay_(True)
            if self.callback:
                self.callback(self)


Scrubber = RSZCinemaScrubberV4



class KINOMAT(object):

    # The compiled font can be a part of the document: the glyphs a film of
    # the box needs (see neededGlyphs). kept names them, None for the whole
    # font; letters are the ones exported for so far. Letters typed that it
    # lacks are exported once the typing stops; Cycle asks for the whole font.
    kept = None
    colOff = 0                  # the settings column being built: 0, or COL_W
    letters = frozenset()
    absent = frozenset()        # typed, and in no glyph of the document
    charset = None              # the characters of the compiled font
    staticOf = None             # the master a static font is of
    widenTimer = None
    switchTimer = None          # the change of variable setting about to run
    openAt = None               # the corner a window built again opens at
    stuck = False               # an export for new letters failed: no more
    projectName = None          # the .rsztools file saved or opened last
    backdrop = None             # a Backdrop: the image or video behind the text
    clock = 0.0                 # the preview's time in the film, in seconds
    lastTick = None             # when the last frame of the preview was drawn
    lostBackdrop = None         # a project's backdrop that was not found
    zoom = 1.0                  # how large the media behind is drawn
    turn = 0.0                  # and which way round, in degrees, clockwise
    speed = 1.0                 # and how fast a video behind it runs
    bright = 0.0                # and how much white or black lies over it
    contrast = 0.0              # and how far its light and dark stand apart
    filmStep = 1.0              # how large the film comes out beside the canvas
    wantHEVC = False            # the MP4's codec: H.264 unless asked otherwise
    offsets = ()                # where each lane starts, with Random on
    realTime = True             # the film takes its time from the video behind
    ownTime = None              # the Duration and fps typed before it did
    tintOn = False              # Colorize
    tintCache = None            # a still's two-colour version, and what it was of
    vfName = ""                 # the variable setting being filmed, when there are several

    def __init__(self):
        loadUI()
        self.font = Glyphs.font
        if self.font is None:
            Message("Kinomat", "Open a Glyphs file.")
            return

        self.baseFont = None
        self.axes = []
        self.static = False
        self.playing = False
        self.phase = 0.0
        self.sheet = None
        self.pending = None
        self.timer = None
        self.vfPath = None
        # which of the document's variable settings is being filmed, as its
        # place in variableSettings(); None when it holds none
        self.setting = defaultSetting(self.font)
        self.rebuilding = False

        started = time.time()
        # Not every document is a design space. One master has nothing to vary,
        # and masters kept as separate styles cannot be varied between; either
        # way the panel used to stop at the variable export. Such a document
        # goes out as the static font of the master in front, and moves through
        # what a static font still has.
        master, self.masterName = lookedAt(self.font)
        varied = variableDesign(self.font)
        # A design space with nothing in Exports to build from: the panel used
        # to make a variable font up on the spot, over every master with
        # nothing switched off. It came out right and was not the font the
        # document exports, which is worse than not opening \u2014 what is on
        # the screen is taken for the font. So it says what is missing, and
        # stops.
        if varied and not variableSettings(self.font):
            Message("Kinomat",
                    "This document has no variable font export.\n\n"
                    "Add one in Font Info \u25b8 Exports, then open Kinomat "
                    "again.")
            return
        staticOf = None                 # the master a static font is of
        # only what a film of the box needs goes out, and the box opens on the
        # font's name: a few dozen glyphs instead of the whole font
        self.letters = frozenset(openingText(self.font))
        needed = neededGlyphs(self.font, self.letters)
        try:
            # an export still there — another panel open on the same document,
            # since one that closes empties the cache — is reused for as long
            # as the document has not moved under it
            how = "cached"
            self.vfPath, self.kept = (
                cachedFont(self.font, None, needed, self.setting)
                if varied else (None, None))
            if not self.vfPath and master is not None:
                self.vfPath, self.kept = cachedFont(self.font, master, needed)
                if self.vfPath:
                    staticOf = master
            if not self.vfPath:
                how = "exported"
                failed = None
                if varied:
                    try:
                        self.vfPath, self.kept = exportFont(
                            self.font, None, needed, self.setting)
                    except Exception as trouble:
                        # masters that looked like a design space and were
                        # not: why goes to the Macro output, and on we go
                        failed = trouble
                        print("Kinomat \u2014 no variable font, so the static "
                              "one of %s:\n%s" % (self.masterName, trouble))
                if not self.vfPath:
                    if master is None:
                        raise failed or Exception("No master to show.")
                    self.vfPath, self.kept = exportFont(self.font, master,
                                                        needed)
                    staticOf = master
            self.staticOf = staticOf
            # which of them it is: a document with a Roman setting and a
            # Stencil one gives two different fonts, and the panel showing
            # only the family name leaves no way to tell them apart
            self.vfName = "" if staticOf else settingName(self.font,
                                                          self.setting)
            ready = time.time()
            self.baseFont = makeBaseFont(self.vfPath)
            self.axes = fontAxes(self.baseFont)
        except Exception as e:
            Message("Kinomat", str(e))
            return

        # no axes — one master, or a variable export that came out plain: the
        # lanes are Size and Tracking instead, and all the rest works as ever
        self.static = not self.axes
        if self.static:
            self.axes = staticLanes()

        self.buildUI()
        # where the wait went. In the panel and not only in the Macro output:
        # a plugin's print does not always reach it, and this is the one number
        # worth reading. It stands until the first control is touched.
        # of a part of the font, how much of it: that is what the wait was for.
        # The panel's own share is the rest, and only the Macro output spells it
        # out: the status line has room for one sentence
        what = (("static font of %s" % self.masterName) if staticOf
                else "variable font")
        shown = what if self.kept is None or needed is None else (
            "%d of %d glyphs" % (len(self.kept), needed[2]))
        note = "Opened in %.1f s \u00b7 %s %s in %.1f s" % (
            time.time() - started, shown, how, ready - started)
        print("Kinomat %s \u2014 %s \u00b7 panel in %.1f s%s" % (
            VERSION or "?", note, time.time() - ready,
            "" if shown == what else " (%s)" % what))
        self.w.status.set(note)

    # -- window --------------------------------------------------------------

    # -- the pieces the panel is made of --------------------------------------

    def zone(self, name, rect, fill=None, gradient=None, into=None):
        """
        A band of the panel, with nothing on it yet.

        Every zone is made before any control, because vanilla stacks its
        subviews in the order they are created: a zone built later would cover
        the controls that belong to it.
        """
        group = vanilla.Group(rect)
        setattr(into or self.w, name, group)
        view = group.getNSView()
        view.setWantsLayer_(True)
        if fill is not None:
            view.layer().setBackgroundColor_(fill.CGColor())
        if gradient is not None:
            try:
                layer = Quartz.CAGradientLayer.layer()
                layer.setColors_([c.CGColor() for c in gradient])
                layer.setStartPoint_((0.5, 1.0))
                layer.setEndPoint_((0.5, 0.0))
                layer.setFrame_(((0, 0), (rect[2], rect[3])))
                view.layer().addSublayer_(layer)
            except Exception:
                view.layer().setBackgroundColor_(gradient[-1].CGColor())
        return group

    def divider(self, name, y):
        """The hairline between two sections of a column, and where the title
        of the next one starts: one point of rule, then the gap."""
        self.zone(name, (self.colOff + GUTTER, y, COL_W - GUTTER * 2, 1),
                  LINE_DIVIDER)
        return y + 8

    def sectionTitle(self, name, x, y, text, width=200):
        x += self.colOff
        box = vanilla.TextBox((x, y, width, 14), text, sizeStyle="small")
        box.getNSTextField().setAttributedStringValue_(
            attributed(text, uiFont(10, NSFontWeightBold), INK_MUTED, kern=0.9))
        setattr(self.w, name, box)
        return y + 23

    def caption(self, name, x, y, width, text, colour=INK_LABEL, size=12,
                align=NSTextAlignmentLeft, weight=None, height=16, into=None,
                kern=None, wraps=False):
        if into is None:
            x += self.colOff
        box = vanilla.TextBox((x, y, width, height), text, sizeStyle="small")
        field = box.getNSTextField()
        field.setFont_(uiFont(size, weight))
        field.setTextColor_(colour)
        field.setAlignment_(align)
        if kern:
            field.setAttributedStringValue_(
                attributed(text, uiFont(size, weight), colour, kern=kern,
                           align=align))
        if wraps:
            field.setUsesSingleLineMode_(False)
            field.cell().setWraps_(True)
        setattr(into or self.w, name, box)
        return box

    def rowLabel(self, name, y, text):
        """The right-aligned label column the sidebar grids hang from."""
        return self.caption(name, GUTTER, y + 4, LABEL_W, text,
                            align=NSTextAlignmentRight)

    def field(self, name, x, y, width, text, callback=None, size=12,
              align=NSTextAlignmentRight, height=FIELD_H, into=None,
              font=None, radius=6.0, inset=7, border=LINE_FIELD,
              rightInset=None):
        """
        A white rounded field.

        Two views, not one: AppKit draws a text field taller than its line with
        the text against the top edge, and there is no public way to centre it.
        So the box is a layer behind, and the field is exactly one line tall,
        set in the middle of it. The 7pt inset is the design's padding.
        """
        if into is None:
            x += self.colOff
        box = self.zone(name + "Box", (x, y, width, height), SURF_FIELD,
                        into=into)
        layer = box.getNSView().layer()
        layer.setCornerRadius_(radius)
        layer.setBorderWidth_(1.0)
        layer.setBorderColor_(border.CGColor())
        catcher = FieldBox.alloc().initWithFrame_(((0, 0), (width, height)))
        catcher.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        box.getNSView().addSubview_(catcher)
        line = size + 6
        # the right margin can be wider than the left: something else may be
        # standing inside the box, and the text has to stop before it
        far = inset if rightInset is None else rightInset
        control = vanilla.EditText((x + inset, y + (height - line) / 2.0,
                                    width - inset - far, line), text,
                                   callback=callback or self.settingsChanged,
                                   sizeStyle="small")
        setattr(into or self.w, name, control)
        box = control.getNSTextField()
        box.setBordered_(False)
        box.setDrawsBackground_(False)
        box.setFont_(font or uiFont(size))
        box.setTextColor_(INK)
        box.setAlignment_(align)
        catcher.field = box
        # I campi che reggono un numero si annotano qui, e le frecce su e giu
        # li trovano. Quelli che tengono testo restano fuori per nome: un
        # colore come 003300 si lascerebbe leggere come tremilatrecento, e una
        # freccia lo cambierebbe senza che nessuno se ne accorga.
        if not (name.endswith("Hex") or name == "key"):
            self.stepFields.append((box, control, callback or self.settingsChanged))
        return control

    def popup(self, name, x, y, width, items, callback=None):
        x += self.colOff
        control = vanilla.PopUpButton((x, y, width, POPUP_H), items,
                                      callback=callback or self.settingsChanged,
                                      sizeStyle="small")
        setattr(self.w, name, control)
        try:
            control._nsObject.setFont_(uiFont(12))
        except Exception:
            pass
        return control

    def paintPill(self, control, title, fill=None, border=None, colour=INK,
                  size=12, weight=None, radius=7, align=NSTextAlignmentCenter):
        button = control.getNSButton()
        button.setBordered_(False)
        button.setWantsLayer_(True)
        layer = button.layer()
        layer.setCornerRadius_(radius)
        layer.setBackgroundColor_((fill or NSColor.clearColor()).CGColor())
        layer.setBorderWidth_(1.0 if border is not None else 0.0)
        if border is not None:
            layer.setBorderColor_(border.CGColor())
        button.setAttributedTitle_(
            attributed(title, uiFont(size, weight), colour, align=align))

    def pill(self, name, x, y, width, height, title, callback, into=None,
             containerH=None, **kwargs):
        """
        A button that is exactly the size it was asked for.

        vanilla grows a button's frame — five points either side, eleven down —
        so that AppKit's bezel lands on the rectangle given. These have no
        bezel, they are a coloured layer, so the grown frame is the thing you
        see and every pill came out too big. The frame is put back by hand,
        which means converting to AppKit's corner: the content view is not
        flipped.
        """
        if into is None:
            x += self.colOff
        control = vanilla.Button((x, y, width, height), title,
                                 callback=callback, sizeStyle="small")
        setattr(into or self.w, name, control)
        try:
            tall = self.contentH if containerH is None else containerH
            control._nsObject.setFrame_(((x, tall - y - height), (width, height)))
        except Exception:
            pass
        self.paintPill(control, title, **kwargs)
        return control

    def place(self, control, rect):
        """
        Move a piece that is already made to a rectangle of the layout.

        Not setPosSize: vanilla turns a rectangle the right way up against the
        frame of the view a piece stands in, and the panel's view is drawn
        smaller than the layout it holds (see drawSmaller), so those two
        heights are not the same number. The turn is done here against the
        layout's own height, the way pill() does it.
        """
        x, y, w, h = rect
        try:
            control._nsObject.setFrame_(((x, self.contentH - y - h), (w, h)))
        except Exception:
            control.setPosSize(rect)

    def check(self, name, x, y, width, title, on, callback, height=FIELD_H):
        x += self.colOff
        group = vanilla.Group((x, y, width, height))
        setattr(self.w, name, group)
        view = Check.alloc().initWithFrame_(((0, 0), (width, height)))
        view.on = bool(on)
        view.label = title
        view.callback = callback
        view.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        group.getNSView().addSubview_(view)
        return view

    def setButtonTitle(self, button, title):
        button.getNSButton().setTitle_(title)

    # -- window ---------------------------------------------------------------

    def buildUI(self):
        """
        Two columns of settings, stage, lanes, export bar.

        What the film is made of stands on the left, grouped under its own
        title: PROJECT and TEXT in the first column, CANVAS in the second. The
        picture stands on the dotted ground beside them at the shape of the
        chosen format. Underneath, what moves and how: the first column carries
        on down with MOTION, and beside it the transport and one lane per axis —
        the lane being the whole idea: a range from FROM to TO with the live
        value riding along it. The export bar is last, the whole width. The key
        stands up in the title bar, beside the name of the font.
        """
        self.sliders = []
        self.axisChecks = []
        self.hideChecks = []
        self.stepFields = []
        self.stepMonitor = None
        self.animate = [bool(ax.get("animate", True)) for ax in self.axes]
        # Hide leaves a lane's slider out of the frame; the lane still moves
        self.hidden = [bool(ax.get("hide", False)) for ax in self.axes]

        self.colOff = 0
        stageX = SIDE_W + 1
        # the lanes on the right, the MOTION column on the left: the band is
        # as tall as whichever of the two asks for more
        laneH = max(MOTION_H, 89 + LANE_H * len(self.axes))
        winW, winH = windowSize(laneH)
        self.winW = winW
        stageW = winW - stageX
        # the settings and the stage share the top band, and the lanes and the
        # bar run the whole width under them: the stage takes whatever the
        # lanes leave, so a font with many axes loses picture, not panel
        stageH = winH - laneH - EXPORT_H
        laneY = stageH
        exportY = laneY + laneH
        self.contentH = winH

        self.w = vanilla.Window((winW, winH),
                                self.font.familyName or "Kinomat")

        # ---------------- the bands, before anything stands on them ---------
        self.zone("sideZone", (0, 0, SIDE_W, stageH), SURF_SIDE)
        self.zone("stageZone", (stageX, 0, stageW, stageH))
        ground = StageBack.alloc().initWithFrame_(((0, 0), (stageW, stageH)))
        ground.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self.w.stageZone.getNSView().addSubview_(ground)
        self.zone("laneZone", (0, laneY, winW, laneH), SURF_SIDE)
        self.zone("exportZone", (0, exportY, winW, EXPORT_H),
                  gradient=(SURF_BAR_TOP, SURF_BAR_BOTTOM))
        self.zone("sideRule", (SIDE_W, 0, 1, stageH), LINE_ZONE)
        # the first column goes all the way down, MOTION under TEXT; the band
        # of the lanes begins where it ends
        self.zone("colRule", (COL_W, 0, 1, exportY), LINE_ZONE)
        self.zone("laneRule", (COL_W, laneY, winW - COL_W, 1), LINE_ZONE)
        self.zone("exportRule", (0, exportY, winW, 1), LINE_ZONE)

        # the canvas sits on a panel of its own so it can carry a shadow: a
        # layer that clips its corners cannot also cast one
        self.zone("canvasBack", (stageX + 20, 20, 100, 100), SURF_FIELD)
        back = self.w.canvasBack.getNSView().layer()
        back.setCornerRadius_(10.0)
        back.setShadowOpacity_(0.25)
        back.setShadowRadius_(14.0)
        back.setShadowOffset_((0, -8))

        # ---------------- PROJECT -------------------------------------------
        # first, as in the tools on the web: the work as a file of its own
        y = self.sectionTitle("hdProject", GUTTER, GUTTER, "PROJECT")
        half = (COL_W - GUTTER * 2 - 8) // 2
        for i, (name, title, action, tip) in enumerate((
                ("projSave", "Save…", self.saveProject,
                 "Save these settings as a .rsztools project. The font is not "
                 "in it: a project takes the font of the Glyphs file that is open."),
                ("projOpen", "Open…", self.openProject,
                 "Open a .rsztools project saved by Kinomat in Glyphs"))):
            self.pill(name, GUTTER + i * (half + 8), y, half, FIELD_H, title,
                      action, fill=SURF_FIELD, border=LINE_FIELD,
                      colour=INK_BUTTON, weight=NSFontWeightMedium)
            getattr(self.w, name).getNSButton().setToolTip_(tip)
        y += FIELD_H

        # ---------------- FONT ----------------------------------------------
        # which of the document's exports is being filmed. A family with a
        # stencil axis keeps a Roman variable setting and a Stencil one, each
        # cancelling the other's masters: two fonts, with axes of their own,
        # and no way to tell from outside which is the one being worked on.
        # So the panel asks. With a single setting, or none, there is nothing
        # to choose and the row is not there at all.
        self.settingNames = settingLabels(self.font)
        if len(self.settingNames) > 1:
            y = self.sectionTitle("hdFont", GUTTER,
                                  self.divider("divFont", y + 8), "FONT")
            self.rowLabel("lbSetting", y - 1, "Export")
            self.popup("vfPick", FIELD_X, y, FIELD_W, self.settingNames,
                       callback=self.pickSetting)
            if self.setting is not None and self.setting < len(self.settingNames):
                self.w.vfPick.set(self.setting)
            try:
                self.w.vfPick.getNSPopUpButton().setToolTip_(
                    "Which variable export of this Glyphs file is filmed. "
                    "Each setting has axes of its own, so the lanes below are "
                    "built again when it changes; the rest of the panel stays "
                    "as it is.")
            except Exception:
                pass
            y += POPUP_H

        # ---------------- TEXT ----------------------------------------------
        y = self.sectionTitle("hdText", GUTTER, self.divider("div0", y + 8),
                              "TEXT")
        # the font's own name, which is what you want to look at first
        self.w.text = vanilla.TextEditor((GUTTER, y, COL_W - GUTTER * 2, 56),
                                         openingText(self.font),
                                         callback=self.settingsChanged,
                                         checksSpelling=False)
        editor = self.w.text.getNSTextView()
        editor.setRichText_(False)
        editor.setAutomaticQuoteSubstitutionEnabled_(False)
        editor.setAutomaticDashSubstitutionEnabled_(False)
        editor.setFont_(uiFont(15, NSFontWeightSemibold))
        editor.setTextColor_(INK)
        editor.setBackgroundColor_(SURF_FIELD)
        editor.setTextContainerInset_((6, 8))
        editor.setTypingAttributes_({
            NSFontAttributeName: uiFont(15, NSFontWeightSemibold),
            NSForegroundColorAttributeName: INK, NSKernAttributeName: 0.4})
        scroll = self.w.text.getNSScrollView()
        scroll.setHasVerticalScroller_(False)
        scroll.setBorderType_(0)
        scroll.setDrawsBackground_(False)
        scroll.setWantsLayer_(True)
        frame = scroll.layer()
        frame.setBackgroundColor_(SURF_FIELD.CGColor())
        frame.setCornerRadius_(7.0)
        frame.setBorderWidth_(1.0)
        frame.setBorderColor_(LINE_FIELD.CGColor())
        frame.setMasksToBounds_(True)
        y += 68

        self.rowLabel("lbSize", y, "Size")
        self.field("size", FIELD_X, y, 66, "200")
        self.fitCheck = self.check("fitBox", FIELD_X + 74, y, 100, "Fit width",
                                   True, self.settingsChanged)
        y += FIELD_H + 8

        self.rowLabel("lbLead", y, "Leading")
        self.field("lead", FIELD_X, y, 66, "110")
        self.caption("leadPct", FIELD_X + 72, y + 4, 16, "%", INK_MUTED, 11)
        self.cycleCheck = self.check("cycleBox", FIELD_X + 122, y, 76,
                                     "Cycle", False, self.settingsChanged)
        y += FIELD_H + 8

        self.rowLabel("lbTrack", y, "Tracking")
        self.field("track", FIELD_X, y, 66, "0")
        self.caption("trackUnit", FIELD_X + 72, y + 4, 44, "/1000",
                     INK_MUTED, 11)
        # Sliders used to stand here; it draws the lanes' own sliders in the
        # frame, so it stands with the lanes now
        y += FIELD_H + 8

        # AppKit gives a segmented control the accent set in System Settings
        # and no way to ask for another, so the track and its three buttons are
        # drawn here instead
        self.rowLabel("lbAlign", y - 1, "Align")
        self.zone("alignTrack", (FIELD_X, y, 98, 26), SURF_SEGMENT)
        self.w.alignTrack.getNSView().layer().setCornerRadius_(7.0)
        self.alignButtons = []
        for i, icon in enumerate(("text.alignleft", "text.aligncenter",
                                  "text.alignright")):
            self.pill("align%d" % i, FIELD_X + 2 + i * 32, y + 2, 30, 22, "",
                      lambda sender, k=i: self.pickAlign(k), radius=5)
            control = getattr(self.w, "align%d" % i)
            image = symbol(icon)
            if image is not None:
                control.getNSButton().setImage_(image)
                control.getNSButton().setImagePosition_(NSImageOnly)
            self.alignButtons.append(control)
        self.alignIndex = 1
        self.paintAlign()
        y += 26

        # MOTION used to stand here, between TEXT and CANVAS. It is down with
        # the lanes now: what moves and how, read on one line

        # ---------------- CANVAS ---------------------------------------------
        # the second column starts here: back to the top, one column further
        # right. colOff is what every piece adds to its x, so the rows below are
        # written exactly as they were when they stood in a single column
        self.colOff = COL_W
        y = self.sectionTitle("hdCanvas", GUTTER, GUTTER, "CANVAS")
        self.rowLabel("lbPreset", y - 1, "Preset")
        self.popup("preset", FIELD_X, y, FIELD_W, PRESET_NAMES,
                   callback=self.presetChanged)
        y += POPUP_H + 8

        self.rowLabel("lbCanvas", y, "Size")
        self.field("canvasW", FIELD_X, y, 64, str(PRESETS[DEFAULT_PRESET][1]))
        self.caption("canvasX", FIELD_X + 70, y + 4, 12, "×", INK_MUTED, 11)
        self.field("canvasH", FIELD_X + 88, y, 64, str(PRESETS[DEFAULT_PRESET][2]))
        y += FIELD_H + 8

        colourY = y
        for target, title, colour in (("bg", "Paper", "#0B0B0D"),
                                      ("fg", "Ink", "#FF4D00")):
            self.rowLabel("lb" + target, y, title)
            well = vanilla.ColorWell((self.colOff + FIELD_X, y, 28, 24),
                                     color=nsColorFromHex(colour),
                                     callback=self.colourChanged)
            setattr(self.w, target, well)
            # bordered, and left that way: a well with its border taken off is
            # the swatch alone, and clicking it does nothing at all
            try:
                well._nsObject.setColorWellStyle_(1)      # minimal, macOS 13+
            except Exception:
                pass
            # the well and the value it holds: one to pick with, one to paste into
            self.field(target + "Hex", FIELD_X + 34, y, 88, colour,
                       callback=self.hexEdited, align=NSTextAlignmentLeft)
            y += FIELD_H + 8

        # one button for the two rows, so it stands between them rather than
        # beside either one: it belongs to the pair, not to Paper or to Ink
        self.pill("colourSwap", FIELD_X + FIELD_W - 30, colourY + 16, 30, FIELD_H,
                  "⇄", self.swapColours,
                  fill=SURF_FIELD, border=LINE_FIELD, colour=INK_BUTTON)
        self.w.colourSwap.getNSButton().setToolTip_(
            "Paper and Ink change places: the film in negative")

        # a picture or a film behind the text, over the paper. Pro, as in the
        # tools on the web
        self.rowLabel("lbBackdrop", y, "Media")
        self.pill("backdropPick", FIELD_X, y, FIELD_W - 32, FIELD_H, "",
                  self.chooseBackdrop)
        self.w.backdropPick.getNSButton().setToolTip_(
            "An image or a video behind the text, filling the canvas. A video "
            "runs at its own speed and starts over when it ends.")
        self.pill("backdropClear", FIELD_X + FIELD_W - 24, y, 24, FIELD_H, "✕",
                  self.clearBackdrop, fill=SURF_FIELD, border=LINE_FIELD,
                  colour=INK_MUTED)
        self.w.backdropClear.getNSButton().setToolTip_("No backdrop: the paper again")
        self.paintBackdrop()
        y += FIELD_H + 8

        # Real time: while it is on, a video behind the text sets the film's
        # time — the cycle is one whole play of the clip, at its own speed
        self.realTimeBox = self.check("realTimeBox", FIELD_X, y, 104, "Real time",
                                      self.realTime, self.toggleRealTime)
        self.caption("realTimeNote", FIELD_X + 108, y + 4, FIELD_W - 108, "",
                     INK_FAINT, 11)
        y += FIELD_H + 8

        # how large the media is drawn: the bar rests half way, at the size
        # that just covers the frame
        self.rowLabel("lbZoom", y, "Zoom")
        self.w.zoomGroup = vanilla.Group((self.colOff + FIELD_X, y + 1,
                                          FIELD_W - 52, 22))
        self.zoomSlider = Scrubber.alloc().initWithFrame_(
            ((0, 0), (FIELD_W - 52, 22)))
        self.zoomSlider.value = zoomToBar(self.zoom)
        self.zoomSlider.callback = self.zoomed
        self.zoomSlider.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self.w.zoomGroup.getNSView().addSubview_(self.zoomSlider)
        self.w.zoomGroup.getNSView().setToolTip_(
            "How large the image or video behind is drawn: 100% just covers "
            "the frame, more grows into it, less leaves the paper round it")
        self.caption("zoomNote", FIELD_X + FIELD_W - 46, y + 4, 46, "100%",
                     INK_MUTED, 11, align=NSTextAlignmentRight)
        y += FIELD_H + 8

        # and which way round it stands: the bar rests upright in the middle
        self.rowLabel("lbTurn", y, "Rotate")
        self.w.turnGroup = vanilla.Group((self.colOff + FIELD_X, y + 1,
                                          FIELD_W - 52, 22))
        self.turnSlider = Scrubber.alloc().initWithFrame_(
            ((0, 0), (FIELD_W - 52, 22)))
        self.turnSlider.value = turnToBar(self.turn)
        self.turnSlider.callback = self.turned
        self.turnSlider.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self.w.turnGroup.getNSView().addSubview_(self.turnSlider)
        self.w.turnGroup.getNSView().setToolTip_(
            "Which way round the image or video behind stands, from half a "
            "turn one way to half a turn the other. The frame stays full: "
            "turned, the picture is drawn larger to fill it.")
        self.caption("turnNote", FIELD_X + FIELD_W - 46, y + 4, 46, "0°",
                     INK_MUTED, 11, align=NSTextAlignmentRight)
        y += FIELD_H + 8

        # and how fast a video behind it runs: the bar rests at its own speed
        self.rowLabel("lbSpeed", y, "Speed")
        self.w.speedGroup = vanilla.Group((self.colOff + FIELD_X, y + 1,
                                           FIELD_W - 52, 22))
        self.speedSlider = Scrubber.alloc().initWithFrame_(
            ((0, 0), (FIELD_W - 52, 22)))
        self.speedSlider.value = speedToBar(self.speed)
        self.speedSlider.callback = self.speeded
        self.speedSlider.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self.w.speedGroup.getNSView().addSubview_(self.speedSlider)
        self.w.speedGroup.getNSView().setToolTip_(
            "How fast the video behind runs: 1x is its own speed. With Real "
            "time on, the film's length follows — a clip of 4 s at 2x makes a "
            "film of 2 s.")
        self.caption("speedNote", FIELD_X + FIELD_W - 46, y + 4, 46, "1×",
                     INK_MUTED, 11, align=NSTextAlignmentRight)
        y += FIELD_H + 8

        # Colorize: the image or the video in two colours, as in the tools on
        # the web — the darks' colour, the lights', on and off, and the swap
        self.rowLabel("lbTint", y, "Colorize")
        for i, (target, colour, tip) in enumerate((
                ("tintDark", TINT_DARK, "The colour the darks of the backdrop take"),
                ("tintLight", TINT_LIGHT, "The colour the lights of the backdrop take"))):
            well = vanilla.ColorWell((self.colOff + FIELD_X + i * 34, y, 28, 24),
                                     color=nsColorFromHex(colour),
                                     callback=self.settingsChanged)
            setattr(self.w, target, well)
            try:
                well._nsObject.setColorWellStyle_(1)      # as Paper and Ink's
            except Exception:
                pass
            well._nsObject.setToolTip_(tip)
        self.pill("tintOn", FIELD_X + 74, y, 46, FIELD_H, "", self.toggleTint)
        self.w.tintOn.getNSButton().setToolTip_(
            "The image or the video behind in two colours, or as it is")
        self.pill("tintSwap", FIELD_X + 128, y, 30, FIELD_H, "⇄", self.swapTint,
                  fill=SURF_FIELD, border=LINE_FIELD, colour=INK_BUTTON)
        self.w.tintSwap.getNSButton().setToolTip_("Swap the two colours")
        self.paintTint()
        y += FIELD_H + 8

        # and how light or dark it is drawn: the bar rests in the middle, where
        # the media is left as it is
        self.rowLabel("lbBright", y, "Bright")
        self.w.brightGroup = vanilla.Group((self.colOff + FIELD_X, y + 1,
                                            FIELD_W - 52, 22))
        self.brightSlider = Scrubber.alloc().initWithFrame_(
            ((0, 0), (FIELD_W - 52, 22)))
        self.brightSlider.value = brightToBar(self.bright)
        self.brightSlider.callback = self.brightened
        self.brightSlider.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self.w.brightGroup.getNSView().addSubview_(self.brightSlider)
        self.w.brightGroup.getNSView().setToolTip_(
            "Lighter or darker: white or black laid over the image or video "
            "behind, to let the text read over it. The paper round it keeps "
            "its own colour.")
        self.caption("brightNote", FIELD_X + FIELD_W - 46, y + 4, 46, "0%",
                     INK_MUTED, 11, align=NSTextAlignmentRight)
        y += FIELD_H + 8

        # and how far its light and its dark stand apart: the bar rests in the
        # middle, where the media is left as it is
        self.rowLabel("lbContrast", y, "Contrast")
        self.w.contrastGroup = vanilla.Group((self.colOff + FIELD_X, y + 1,
                                              FIELD_W - 52, 22))
        self.contrastSlider = Scrubber.alloc().initWithFrame_(
            ((0, 0), (FIELD_W - 52, 22)))
        self.contrastSlider.value = contrastToBar(self.contrast)
        self.contrastSlider.callback = self.contrasted
        self.contrastSlider.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self.w.contrastGroup.getNSView().addSubview_(self.contrastSlider)
        self.w.contrastGroup.getNSView().setToolTip_(
            "Harder or softer: to the right the lights of the image or video "
            "behind go lighter and the darks darker, to the left they come "
            "together towards a flat grey. The paper round it keeps its own "
            "colour.")
        self.caption("contrastNote", FIELD_X + FIELD_W - 46, y + 4, 46, "0%",
                     INK_MUTED, 11, align=NSTextAlignmentRight)
        y += FIELD_H + 8

        # the rows that only mean something with a picture or a film behind the
        # text: out of sight until there is one, and the film's own two — Real
        # time and Speed — only for a film. The rest close up under Media.
        self.mediaRows = [
            ("film", ["realTimeBox", "realTimeNote"]),
            ("any", ["lbZoom", "zoomGroup", "zoomNote"]),
            ("any", ["lbTurn", "turnGroup", "turnNote"]),
            ("film", ["lbSpeed", "speedGroup", "speedNote"]),
            ("any", ["lbTint", "tintDark", "tintLight", "tintOn", "tintSwap"]),
            ("any", ["lbBright", "brightGroup", "brightNote"]),
            ("any", ["lbContrast", "contrastGroup", "contrastNote"]),
        ]
        self.mediaBuilt = None
        self.showMediaRows()

        # ACCOUNT used to stand here, at the foot of the column. The key is up
        # in the title bar now, beside the name of the font: see addTitleInfo

        # the columns are done: the stage and the lanes are laid out on the
        # window itself
        self.colOff = 0

        # ---------------- the stage ------------------------------------------
        self.previewArea = (stageX + 20, 20, stageW - 40, stageH - 40)
        # the picture fills the stage it is given, up to the cap: drawing it
        # larger than that costs more than it shows
        self.canvasMax = (min(CANVAS_MAX_W, stageW - 60),
                          min(CANVAS_MAX_H, stageH - 60))
        self.previewFitted = None
        self.w.preview = vanilla.ImageView((stageX + 20, 20, stageW - 40,
                                            stageH - 40), scale="proportional")

        # ---------------- transport ------------------------------------------
        laneX = COL_W + ZONE_PAD          # MOTION stands to the left of them
        laneR = winW - ZONE_PAD
        y = laneY + 10
        self.pill("play", laneX, y, 30, 30, "", self.togglePlay,
                  fill=ACCENT, colour=NSColor.whiteColor(), radius=8)
        self.showTransport()
        scrubX = laneX + 42
        scrubW = laneR - 108 - scrubX
        self.w.scrubGroup = vanilla.Group((scrubX, y + 4, scrubW, 22))
        self.scrub = Scrubber.alloc().initWithFrame_(((0, 0), (scrubW, 22)))
        self.scrub.callback = self.scrubbed
        self.scrub.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self.w.scrubGroup.getNSView().addSubview_(self.scrub)
        self.caption("clock", laneR - 96, y + 8, 96, "0.00 / 0.00 s",
                     INK_TIME, 11, align=NSTextAlignmentRight)

        # ---------------- MOTION, in the column beside the lanes -------------
        # the first column carries on under the settings, in the same grammar:
        # what moves and how, standing next to the lanes it drives
        y = self.sectionTitle("hdMotion", GUTTER,
                              self.divider("divMotion", laneY) + 6, "MOTION")
        self.rowLabel("lbDuration", y, "Duration")
        self.field("duration", FIELD_X, y, 60, "2")
        self.caption("durUnit", FIELD_X + 66, y + 4, 12, "s", INK_MUTED, 11)
        self.field("fps", FIELD_X + 84, y, 52, "30")
        self.caption("fpsUnit", FIELD_X + 142, y + 4, 24, "fps", INK_MUTED, 11)
        y += FIELD_H + 8

        self.rowLabel("lbEase", y - 1, "Easing")
        self.popup("ease", FIELD_X, y, FIELD_W, EASE_NAMES)
        self.w.ease.set(3)
        y += POPUP_H + 8

        self.rowLabel("lbLoop", y - 1, "Loop")
        self.popup("mode", FIELD_X, y, FIELD_W, MODES)
        y += POPUP_H + 8

        self.rowLabel("lbUnit", y - 1, "Animate")
        self.popup("unit", FIELD_X, y, FIELD_W, UNITS)
        y += POPUP_H + 8

        self.rowLabel("lbRepeat", y, "Repeat")
        self.field("loops", FIELD_X, y, 52, "3")
        self.caption("loopsNote", FIELD_X + 58, y + 4, 110, "× in export",
                     INK_MUTED, 11)

        # ---------------- one lane per axis -----------------------------------
        # a static font has no axes: the title names what the lanes move
        # instead, and the hint says why
        self.sectionTitle("hdAxes", laneX + 2, laneY + 54,
                          "SIZE · TRACKING" if self.static else "AXES", 160)
        self.caption("axesHint", laneR - 260, laneY + 54, 260,
                     "static font · no axes, so size and tracking move"
                     if self.static else "drag handles to set FROM → TO",
                     INK_FAINT, 10, align=NSTextAlignmentRight, height=13)
        # how the lanes move, and whether their sliders are drawn in the frame:
        # the three of them stand with the lanes, after their title. Alternate
        # takes them one at a time; Random starts each somewhere else; the two
        # are different ideas, so ticking one lets the other go
        heading = "SIZE \u00b7 TRACKING" if self.static else "AXES"
        boxX = laneX + 2 + int(textWidth(heading, uiFont(10, NSFontWeightBold))) + 34
        self.alternateCheck = self.check("alternateBox", boxX, laneY + 49, 84,
                                         "Alternate", False, self.toggleAlternate)
        self.randomCheck = self.check("randomBox", boxX + 90, laneY + 49, 78,
                                      "Random", False, self.toggleRandom)
        self.sliderCheck = self.check("sliderBox", boxX + 174, laneY + 49, 74,
                                      "Sliders", False, self.settingsChanged)

        liveX = laneR - 52
        toX = liveX - 68
        arrowX = toX - 15
        fromX = arrowX - 61
        maxX = fromX - 46
        # beside each lane's name, its Hide box; the minimum and the range move
        # along to make room for it
        hideX = laneX + 86
        minX = hideX + 56
        trackX = minX + 46
        trackW = maxX - 12 - trackX

        y = laneY + 75
        for i, ax in enumerate(self.axes):
            self.axisChecks.append(
                self.check("axCheck%d" % i, laneX, y, 78, ax["name"],
                           self.animate[i],
                           lambda sender, k=i: self.toggleAnimate(k),
                           height=LANE_H))
            self.hideChecks.append(
                self.check("axHide%d" % i, hideX, y, 50, "Hide", self.hidden[i],
                           lambda sender, k=i: self.toggleHide(k),
                           height=LANE_H))
            unit = ax.get("unit", "")
            self.caption("axMin%d" % i, minX, y + 10, 34,
                         "%g%s" % (ax["min"], unit), INK_FAINT, 10)
            group = vanilla.Group((trackX, y + 3, trackW, 28))
            setattr(self.w, "axGroup%d" % i, group)
            slider = RangeSlider.alloc().initWithFrame_(((0, 0), (trackW, 28)))
            slider.mn, slider.mx = ax["min"], ax["max"]
            # an axis opens on its whole range, a static lane on its own pair
            slider.lo, slider.hi = ax.get("from", ax["min"]), ax.get("to", ax["max"])
            slider.callback = self.sliderChanged
            slider.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
            group.getNSView().addSubview_(slider)
            self.sliders.append(slider)
            self.caption("axMax%d" % i, maxX, y + 10, 34,
                         "%g%s" % (ax["max"], unit),
                         INK_FAINT, 10, align=NSTextAlignmentRight)
            self.field("axFrom%d" % i, fromX, y + 6, 56,
                       "%g" % ax.get("from", ax["min"]), size=11, height=22)
            self.caption("axArrow%d" % i, arrowX - 2, y + 9, 14, "→",
                         INK_FAINT, 11)
            self.field("axTo%d" % i, toX, y + 6, 56,
                       "%g" % ax.get("to", ax["max"]), size=11, height=22)
            self.caption("axNow%d" % i, liveX, y + 9, 52, "", ACCENT, 11,
                         align=NSTextAlignmentRight, weight=NSFontWeightSemibold)
            y += LANE_H

        # ---------------- export, last ----------------------------------------
        y = exportY + 11
        x = ZONE_PAD                      # the bar is the panel's, not a lane's
        width = int(textWidth("Export MP4", uiFont(12, NSFontWeightSemibold))) + 36
        self.pill("mp4", x, y, width, 30, "Export MP4", self.exportMP4,
                  fill=ACCENT, colour=NSColor.whiteColor(),
                  weight=NSFontWeightSemibold)
        x += width + 10
        for name, title, action in (("gif", "GIF", self.exportGIF),
                                    ("png", "PNG sequence", self.exportPNG)):
            width = int(textWidth(title, uiFont(12, NSFontWeightMedium))) + 28
            self.pill(name, x, y, width, 30, title, action, fill=SURF_FIELD,
                      border=LINE_FIELD, colour=INK_BUTTON,
                      weight=NSFontWeightMedium)
            x += width + 10

        # how large the film comes out, round and round: the canvas, half as
        # large again, twice it
        self.pill("filmSize", x, y, 54, 30, "1×", self.stepFilmSize,
                  fill=SURF_FIELD, border=LINE_FIELD, colour=INK_BUTTON,
                  weight=NSFontWeightMedium)
        self.w.filmSize.getNSButton().setToolTip_(
            "How large the film comes out: the canvas, half as large again, or "
            "twice it — 1080 becomes 1620 or 2160, so the letters stay sharp on "
            "a large screen. Larger is heavier to write; what will not fit "
            "inside 4096 is kept at the canvas.")
        self.paintFilmSize()

        # which codec writes the MP4: H.264 plays everywhere, HEVC 4:2:2 at
        # 10 bits carries the colour at full width and draws a finer edge on
        # coloured letters \u2014 1.32 px against 1.43, measured \u2014 and
        # plays on Apple's machines and nowhere else
        x += 54 + 10
        self.pill("codecPill", x, y, 62, 30, "H.264", self.stepCodec,
                  fill=SURF_FIELD, border=LINE_FIELD, colour=INK_BUTTON,
                  weight=NSFontWeightMedium)
        self.w.codecPill.getNSButton().setToolTip_(
            "Which codec writes the MP4. H.264 plays everywhere \u2014 "
            "browsers, phones, anything that takes a film. HEVC draws a finer "
            "edge on coloured letters and plays on Macs, iPhones and Safari, "
            "and nowhere else.")
        self.paintCodec()

        self.caption("status", laneR - 340, exportY + 19, 340, "",
                     INK_STATUS, 11, align=NSTextAlignmentRight, height=14)

        self.styleUI()
        drawSmaller(self.w.getNSWindow(), (winW, winH))
        # built again around another variable setting: it opens at the corner
        # the one before it stood at, before it is shown rather than after, so
        # there is nothing to see of the move
        if self.openAt is not None:
            try:
                self.w.getNSWindow().setFrameTopLeftPoint_(self.openAt)
            except Exception:
                pass
        try:
            self.w.bind("close", self.windowClosed)
        except Exception:
            pass
        self.w.open()
        self.startStepping()
        # the screen is only known once the window is on one
        self._backing = self.backingScale()
        self.paintKey()
        self.settingsChanged()
        # it opens running: the panel is about the movement, and asking for it
        # every time was a click that never had a reason not to happen
        self.togglePlay()


    # -- arrows on a field ---------------------------------------------------

    def startStepping(self):
        """
        Up and down arrows raise and lower whatever number the caret is in.

        A monitor on the window rather than a subclass of the field: the fields
        are vanilla's, and a monitor reaches all of them at once without
        reaching inside anything vanilla owns. It returns None for an event it
        has handled, which is how AppKit is told to stop passing it on — the
        caret would otherwise jump to the other end of the line as well.
        """
        def handler(event):
            try:
                return None if self.stepEvent(event) else event
            except Exception:
                return event
        try:
            self.stepMonitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
                NSEventMaskKeyDown, handler)
        except Exception:
            self.stepMonitor = None

    def stopStepping(self):
        # senza questo il monitor resta acceso a finestra chiusa, e continua a
        # ricevere ogni tasto premuto in Glyphs per il resto della sessione
        if self.stepMonitor is not None:
            try:
                NSEvent.removeMonitor_(self.stepMonitor)
            except Exception:
                pass
            self.stepMonitor = None

    def fieldUnderCaret(self):
        """
        (campo, controllo, callback) del campo che si sta scrivendo, o None.

        Mentre si scrive, il primo a rispondere non e il campo ma l editor di
        testo che la finestra presta a chi ha il fuoco; il campo e il suo
        delegato. Cercare direttamente il campo non lo troverebbe mai.
        """
        try:
            window = self.w.getNSWindow()
        except Exception:
            return None
        if window is None or not window.isKeyWindow():
            return None
        responder = window.firstResponder()
        if responder is None:
            return None
        campo = responder
        if isinstance(responder, NSTextView):
            campo = responder.delegate()
        if campo is None:
            return None
        for box, control, callback in self.stepFields:
            # == e non is: PyObjC costruisce un involucro nuovo a ogni lettura,
            # quindi due riferimenti allo stesso campo non sono mai lo stesso
            # oggetto Python. == passa per isEqual:, che qui e il confronto fra
            # puntatori — cioe la domanda giusta.
            if box == campo:
                return box, control, callback
        return None

    def stepEvent(self, event):
        """True se la freccia e stata usata per cambiare un numero."""
        code = event.keyCode()
        if code not in (125, 126):          # 126 su, 125 giu
            return False
        trovato = self.fieldUnderCaret()
        if trovato is None:
            return False
        box, control, callback = trovato

        testo = (box.stringValue() or "").strip().replace(",", ".")
        try:
            valore = float(testo)
        except ValueError:
            return False                    # non e un numero: la freccia passa

        # gli stessi passi che usa Glyphs: Shift decuplica, Alt assottiglia
        flags = event.modifierFlags()
        passo = 1.0
        if flags & NSEventModifierFlagShift:
            passo = 10.0
        elif flags & NSEventModifierFlagOption:
            passo = 0.1
        nuovo = valore + (passo if code == 126 else -passo)

        # si scrive come era scritto: un campo che diceva 30 non deve
        # diventare 30.0 solo per essere stato toccato
        if passo >= 1 and float(valore) == int(valore):
            scritto = "%d" % int(round(nuovo))
        else:
            scritto = ("%.2f" % nuovo).rstrip("0").rstrip(".")

        box.setStringValue_(scritto)
        editor = box.currentEditor()
        if editor is not None:
            # il testo visibile durante la scrittura sta nell editor, non nel
            # campo: senza questo il numero cambia sotto e non a schermo
            editor.setString_(scritto)
            editor.selectAll_(None)
        try:
            callback(control)
        except Exception:
            pass
        return True

    def styleUI(self):
        """
        The window itself.

        The design is drawn in one light appearance, and its surfaces are
        painted rather than taken from the system — so the window is pinned to
        Aqua. Left to follow Glyphs, a dark menu would open over white fields.
        """
        window = self.w.getNSWindow()
        try:
            # the panel is laid out to the point: it does not stretch. The size
            # to hold is the frame's, which counts the title bar the content
            # size does not
            window.setMinSize_(window.frame().size)
            window.setMaxSize_(window.frame().size)
        except Exception:
            pass
        try:
            window.setBackgroundColor_(SURF_WINDOW)
            window.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameAqua"))
        except Exception:
            pass
        try:
            window.setSubtitle_(("Kinomat %s" % VERSION) if VERSION
                                else "Kinomat")
        except Exception:
            pass
        try:
            preview = self.w.preview.getNSImageView()
            preview.setWantsLayer_(True)
            preview.layer().setCornerRadius_(10.0)
            preview.layer().setMasksToBounds_(True)
        except Exception:
            pass
        self.addTitleInfo(window)

    def titleLine(self):
        """
        What stands beside the name in the title bar: the family the font goes
        out under, and nothing else.

        It used to carry the setting being filmed and the count of axes as
        well. Both are on the panel already \u2014 the setting in FONT \u25b8
        Export, the axes one lane each \u2014 and up here they only made the
        line long: a document whose settings make two families said the family
        twice, "Monologo \u00b7 Monologo Serif \u00b7 1 axis", and ran out of
        title bar, in under the key.

        Made apart from the label so it can be written again under a window
        that is not being rebuilt.
        """
        text = "  %s  " % (self.font.familyName or "Font")
        line = NSMutableAttributedString.alloc().init()
        # the two runs share a baseline, not a centre: a 9pt bullet sits
        # a point below the middle of 11pt text. Measured, not guessed
        line.appendAttributedString_(
            attributed("● ", uiFont(9), ACCENT, baseline=1.0))
        line.appendAttributedString_(attributed(text, uiFont(11), INK_STATUS))
        return line

    def paintTitle(self):
        """The title bar's line written again, as wide as it now reads."""
        label = getattr(self, "titleLabel", None)
        if label is None:
            return
        line = self.titleLine()
        label.setAttributedStringValue_(line)
        frame = label.frame()
        label.setFrame_(((frame.origin.x, frame.origin.y),
                         (line.size().width + 16, frame.size.height)))
        # the key stands where the label ends, so it has to be put there again
        # whenever the label changes width
        self.paintKey()

    def addTitleInfo(self, window):
        """The font, its axes and the key, in the right of the title bar."""
        try:
            from AppKit import NSTitlebarAccessoryViewController
            line = self.titleLine()
            label = NSTextField.alloc().initWithFrame_(
                ((0, 0), (line.size().width + 16, 22)))
            label.setBordered_(False)
            label.setEditable_(False)
            label.setDrawsBackground_(False)
            label.setAttributedStringValue_(line)
            self.titleLabel = label
            # and the account beside the name: the key that opens the export,
            # and the way back to the serial. It is a button, and looks like
            # one; paintKey gives it its colours and its width
            self.keyControl = vanilla.Button((0, 0, 60, 20), "",
                                             callback=self.showKey)
            key = self.keyControl.getNSButton()
            key.setToolTip_("The Pro key: what it is registered to, and where "
                            "to type a new one")
            holder = NSView.alloc().initWithFrame_(
                ((0, 0), (label.frame().size.width + 140, 28)))
            label.setFrameOrigin_((0, 4))
            holder.addSubview_(label)
            holder.addSubview_(key)
            self.titleHolder = holder
            controller = NSTitlebarAccessoryViewController.alloc().init()
            controller.setView_(holder)
            controller.setLayoutAttribute_(2)          # NSLayoutAttributeRight
            window.addTitlebarAccessoryViewController_(controller)
            self.titleBar = controller
            self.paintKey()
        except Exception:
            pass


    def num(self, control, fallback):
        try:
            return float(str(control.get()).replace(",", "."))
        except (ValueError, TypeError):
            return fallback

    def clamped(self, control, fallback, low, high):
        return max(low, min(high, self.num(control, fallback)))

    def syncConfig(self):
        """Read every control once. The playback loop only touches this dict,
        so a frame costs one layout instead of twenty ObjC round trips."""
        cw = int(self.clamped(self.w.canvasW, PRESETS[DEFAULT_PRESET][1], 64, 4096))
        ch = int(self.clamped(self.w.canvasH, PRESETS[DEFAULT_PRESET][2], 64, 4096))
        ranges, raw = [], []
        for i, ax in enumerate(self.axes):
            a = self.num(getattr(self.w, "axFrom%d" % i), ax.get("from", ax["min"]))
            b = self.num(getattr(self.w, "axTo%d" % i), ax.get("to", ax["max"]))
            a = min(max(a, ax["min"]), ax["max"])
            b = min(max(b, ax["min"]), ax["max"])
            raw.append((a, b))
            # ◈ off: the axis sits still on its From value
            ranges.append((ax["id"], a, b if self.animate[i] else a))
        self.cfg = {
            "canvas": (cw - cw % 2, ch - ch % 2),
            "lines": (self.w.text.get() or " ").replace("\\n", "\n").splitlines() or [" "],
            "lead": self.clamped(self.w.lead, 110, 40, 300),
            "track": self.clamped(self.w.track, 0, -300, 1000),
            "align": ALIGNMENTS[self.alignIndex],
            "bg": cgColorFromNSColor(self.w.bg.get()),
            "fg": cgColorFromNSColor(self.w.fg.get()),
            # Colorize: the backdrop's darks and lights, or None when it is off
            "tint": ((rgbOf(self.w.tintDark.get()), rgbOf(self.w.tintLight.get()))
                     if self.tintOn else None),
            "zoom": self.zoom,
            "turn": self.turn,
            "speed": self.speed,
            "bright": self.bright,
            "contrast": self.contrast,
            "ranges": ranges,
            "raw": raw,
            "mode": MODES[self.w.mode.get()],
            "unit": UNITS[self.w.unit.get()],
            "ease": self.w.ease.get(),
            "fps": int(self.clamped(self.w.fps, 30, 6, 60)),
            "duration": self.clamped(self.w.duration, 2.0, 0.2, 30.0),
        }
        # the lanes that move, in the order they stand: Alternate takes them one
        # at a time, and with fewer than two there is nothing to take turns
        self.cfg["moving"] = [i for i in range(len(self.axes)) if self.animate[i]]
        self.cfg["alternate"] = bool(self.alternateCheck.on) and len(self.cfg["moving"]) > 1
        # Random: every lane on the same way round the loop, each starting from
        # its own point of it
        if len(self.offsets) != len(self.axes):
            self.rollOffsets()
        self.cfg["random"] = bool(self.randomCheck.on) and not self.cfg["alternate"]
        self.cfg["offsets"] = list(self.offsets)
        self.cfg["frames"] = self.cycleFrames() if self.cycleCheck.on else None
        # the fit is 9 layouts: compute it here, never inside the loop — and the
        # reach of the ink with it, which places the block in every frame
        block = self.measureBlock()
        self.cfg["size"] = self.fitSize(block)
        self.cfg["ink"] = (block["topEm"] / 1000.0, block["belowEm"] / 1000.0)
        return self.cfg

    def frameCount(self):
        return max(2, int(round(self.cfg["duration"] * self.cfg["fps"])))

    def fps(self):
        return self.cfg["fps"]

    def previewFPS(self):
        return min(30, self.cfg["fps"])

    def sliderInfo(self, progress):
        """Un cursore per ogni asse in movimento, o niente se la casella e spenta.

        Si prende il minimo e il massimo dell asse dal font compilato, non gli
        estremi dell animazione: un cursore che arriva sempre a fondo corsa non
        direbbe niente su quanto l asse e stato davvero percorso.
        """
        if not self.sliderCheck.on:
            return None
        perId = dict((ax["id"], ax) for ax in self.axes)
        valori = self.axisValues(progress)
        fuori = []
        for i, (ident, a, b) in enumerate(self.cfg["ranges"]):
            ax = perId.get(ident)
            # Hide: the lane still moves, only its slider is left out of the frame
            if ax is None or self.hidden[i]:
                continue
            basso, alto = ax["min"], ax["max"]
            # l animazione puo uscire dagli estremi dichiarati: il binario si
            # allarga, invece di lasciare il cursore fuori strada
            basso = min(basso, a, b)
            alto = max(alto, a, b)
            fuori.append({"name": ax["name"] or ax["tag"], "min": basso,
                          "max": alto, "from": a, "to": b,
                          "value": valori.get(ident, a)})
        return fuori or None

    def progressAt(self, phase):
        """What a frame is drawn at, for a phase of the cycle.

        Moving together, the lanes share one progress, looped and eased once.
        Taking turns, the way through the loop is shared out between them and
        each is eased on its own, so the phase itself goes on and axisValues()
        takes it from there."""
        if self.cfg.get("alternate") or self.cfg.get("random"):
            return phase
        return phaseToProgress(phase, self.cfg["mode"], self.cfg["ease"])

    def axisValues(self, progress):
        if self.cfg.get("alternate"):
            return self.alternateValues(progress)
        if self.cfg.get("random"):
            return self.randomValues(progress)
        return dict((ident, a + (b - a) * progress)
                    for ident, a, b in self.cfg["ranges"])

    def randomValues(self, phase):
        """
        Every lane goes the same way round the loop — out and back, or over
        and over, as the Loop says — but starts from its own point of it, drawn
        when Random was ticked. They move together without ever being in step.
        """
        mode, ease = self.cfg["mode"], self.cfg["ease"]
        offsets = self.cfg.get("offsets") or []
        values = {}
        for i, (ident, a, b) in enumerate(self.cfg["ranges"]):
            shift = offsets[i] if i < len(offsets) else 0.0
            values[ident] = a + (b - a) * phaseToProgress(
                (phase + shift) % 1.0, mode, ease)
        return values

    def alternateValues(self, phase):
        """
        The lanes one after another, in the order they stand, each adding to
        the ones before it.

        The way through the loop is the Loop's own — out and back in Ping-pong,
        out and from the start again in Restart, out once in Play once — shared
        out between the lanes that move instead of eased as a whole. The first
        lane goes from its From to its To while the others wait; there it
        stays, and the second sets off; at the far end every lane is on its To.
        Coming back in Ping-pong they go home in the opposite order, the last
        first. Each lane's own movement carries the easing, so only one is ever
        on the way. A lane left unticked sits on its From throughout.
        """
        ranges, moving = self.cfg["ranges"], self.cfg["moving"]
        # the loop's way, linear: the easing is given to each lane's own stretch
        way = phaseToProgress(phase, self.cfg["mode"], LINEAR)
        ease = EASINGS[self.cfg["ease"]][1]
        reached = way * len(moving)
        values = dict((ident, a) for ident, a, b in ranges)
        for order, index in enumerate(moving):
            ident, a, b = ranges[index]
            share = min(1.0, max(0.0, reached - order))
            if 0.0 < share < 1.0:
                share = ease(share)
            values[ident] = a + (b - a) * share
        return values

    def cycleFrames(self):
        """One frame per glyph: what is typed in the box, or the whole font when
        the box is empty.

        Only glyphs with a unicode take part. Every frame is drawn by setting
        text in the compiled font, so a glyph nothing spells cannot be asked
        for — which leaves the components a modular font is built from out of
        the run, and that is where they belong.

        In the box a glyph can be named the way Glyphs names one anywhere else:
        /Aacute, ending at a space or at the next slash. Everything else is read
        a character at a time.
        """
        typed = (self.w.text.get() or "").replace("\\n", "\n")
        wanted = []
        index = 0
        while index < len(typed):
            letter = typed[index]
            if letter == "/":
                end = index + 1
                while end < len(typed) and typed[end] not in " \t\n/":
                    end += 1
                name = typed[index + 1:end]
                if name:
                    wanted.append(("name", name))
                index = end + 1 if end < len(typed) and typed[end] == " " else end
            elif letter.isspace():
                index += 1
            else:
                wanted.append(("char", letter))
                index += 1

        def spelled(glyph):
            try:
                return chr(int(glyph.unicode, 16))
            except Exception:
                return None

        master = None
        try:
            master = self.font.selectedFontMaster.id
        except Exception:
            master = None

        def drawn(glyph):
            """Whether there is anything to look at. A glyph still empty shows
            as a held blank in the middle of the run, which reads as the film
            having stopped rather than as a letter yet to be drawn."""
            layers = []
            if master is not None:
                try:
                    if glyph.layers[master] is not None:
                        layers = [glyph.layers[master]]
                except Exception:
                    layers = []
            if not layers:
                try:
                    layers = list(glyph.layers)
                except Exception:
                    return True
            for layer in layers:
                try:
                    if len(layer.paths) or len(layer.components):
                        return True
                except Exception:
                    continue
            return False

        def isMark(glyph):
            """An accent on its own. It is nonspacing, so it would arrive in the
            middle of the run with no width of its own and hang off the edge of
            the frame — a stroke of ink where a letter was expected."""
            try:
                if glyph.category == "Mark":
                    return True
            except Exception:
                pass
            try:
                return glyph.subCategory == "Nonspacing"
            except Exception:
                return False

        if wanted:
            out = []
            for kind, value in wanted:
                if kind == "char":
                    out.append([value])
                    continue
                glyph = self.font.glyphs[value]
                if glyph is None or not drawn(glyph):
                    continue
                letter = spelled(glyph)
                if letter is not None:
                    out.append([letter])
            return out or None

        out = []
        for glyph in self.font.glyphs:
            try:
                if not glyph.export:
                    continue
            except Exception:
                pass
            # Named in the box an accent is honoured — asking for one by name
            # is asking for it. Swept up by the whole font, it is not.
            if not drawn(glyph) or isMark(glyph):
                continue
            letter = spelled(glyph)
            if letter is not None:
                out.append([letter])
        return out or None

    def measureBlock(self):
        """
        What the text takes up, at 1000 upm, the most it does over the cycle:
        its widest line, its cap height, how far its ink reaches above the first
        baseline and below the last — both grown by a static font's Size lane,
        for the fit — and the same two reaches as the font draws them, for
        placing the block. Measured once a change, never inside the loop.
        """
        lines = self.cfg["lines"]
        # Cycling, the size has to suit every glyph that will pass, not the one
        # showing now: fitted glyph by glyph, a wide W would shrink the frame it
        # arrives in and the whole run would pulse.
        candidates = self.cfg.get("frames") or [lines]
        # nine axis positions for one frame, three when a whole font is queued:
        # the measuring is per frame and a full set would be felt on every keypress
        steps = 9 if len(candidates) <= 8 else 3
        positions = [k / float(max(1, steps - 1)) for k in range(steps)]
        if self.cfg.get("alternate"):
            # one after another, the lanes meet in pairings they never reach
            # moving together — the first on its To while the next is still on
            # its From — so every stretch of the way is looked at on its own
            inside = (0.0, 0.25, 0.5, 0.75) if len(candidates) <= 8 else (0.0, 0.5)
            count = len(self.cfg["moving"])
            ways = [(turn + t) / float(count) for turn in range(count) for t in inside] + [1.0]
            # in Ping-pong the way out is the first half of the cycle
            half = 0.5 if self.cfg["mode"] == "Ping-pong" else 1.0
            positions = [way * half for way in ways]
        elif self.cfg.get("random"):
            # each lane starts somewhere else, so the widest moment is none of
            # the usual few: the whole cycle is looked at in small steps
            steps = 16 if len(candidates) <= 8 else 6
            positions = [k / float(steps) for k in range(steps)]
        found = {"widest": 0.0, "capH": 0.0, "top": 0.0, "below": 0.0,
                 "topEm": 0.0, "belowEm": 0.0}
        for position in positions:
            variations = self.axisValues(position)
            for item in candidates:
                w, c = measureLines(self.baseFont, item, variations,
                                    self.cfg["track"])
                top, below, grown = measureInk(self.baseFont, item, variations,
                                               self.cfg["track"])
                found["widest"] = max(found["widest"], w)
                found["capH"] = max(found["capH"], c)
                found["top"] = max(found["top"], top * grown)
                found["below"] = max(found["below"], below * grown)
                found["topEm"] = max(found["topEm"], top)
                found["belowEm"] = max(found["belowEm"], below)
        found["lines"] = max(candidates, key=len)
        return found

    def fitSize(self, block=None):
        """Type size in pixels: fixed, or fitted to the widest frame — and to
        the tallest, counted from the highest ink of the first line to the
        lowest of the last, so a square frame keeps the descenders. Less an
        overshoot, which goes in the margin as it did when only the caps were
        counted: an O or a 5 comes out the size it always had."""
        if not self.fitCheck.on:
            return self.clamped(self.w.size, 200, 8, 2000)
        block = block or self.measureBlock()
        canvasW, canvasH = self.cfg["canvas"]
        widest, lines = block["widest"], block["lines"]
        if widest <= 0:
            return self.clamped(self.w.size, 200, 8, 2000)
        byWidth = (canvasW * 0.90) / (widest / 1000.0)
        spill = block["capH"] * OVERSHOOT
        blockPerEm = (max(block["capH"], block["top"] - spill) +
                      max(0.0, block["below"] - spill)) / 1000.0 + \
            (self.cfg["lead"] / 100.0) * (len(lines) - 1)
        byHeight = (canvasH * 0.85) / max(0.01, blockPerEm)
        return min(byWidth, byHeight)



    def canvasSize(self):
        return self.cfg["canvas"]

    def renderAt(self, progress, w, h, size, at=None):
        """A frame at that point of the cycle; at is its time in the film, in
        seconds, which a video backdrop takes its picture from."""
        c = self.cfg
        lines = c["lines"]
        frames = c.get("frames")
        if frames:
            # progress is the eased, looped one, so the run breathes with the
            # easing and turns back on itself in ping-pong, like everything else;
            # alternating, what arrives is the phase, and the run is eased here
            at = (phaseToProgress(progress, c["mode"], c["ease"])
                  if (c.get("alternate") or c.get("random")) else progress)
            lines = frames[min(len(frames) - 1, max(0, int(at * len(frames))))]
        backdrop, zoom, turn = None, c.get("zoom", 1.0), c.get("turn", 0.0)
        if self.backdrop is not None:
            # a clip filmed on its side carries its own quarter turn: it is
            # drawn with it, on top of the angle that was asked for
            turn += getattr(self.backdrop, "spin", 0.0)
            # how far into the video that moment of the film is: its own speed
            # times how fast it was asked to run
            seconds = (c["duration"] * progress if at is None else at)
            backdrop = self.backdrop.imageAt(
                seconds * c.get("speed", 1.0), w, h, zoom, turn)
            if backdrop is not None and c.get("tint"):
                # the two-colour version comes out the size of the frame, with
                # the zoom and the turn already in it: it is drawn as it is
                backdrop = self.tinted(backdrop, w, h, c["tint"], zoom, turn)
                zoom, turn = 1.0, 0.0
        return renderFrame(self.baseFont, w, h, lines, size, c["lead"],
                           self.axisValues, progress,
                           c["bg"], c["fg"], c["align"], c["unit"], c["track"],
                           self.sliderInfo(progress), backdrop, zoom, turn,
                           c.get("bright", 0.0), c.get("contrast", 0.0), c.get("ink"))

    # -- preview -------------------------------------------------------------

    def backingScale(self):
        try:
            screen = self.w.getNSWindow().screen()
            if screen is not None:
                return float(screen.backingScaleFactor())
        except Exception:
            pass
        return 2.0

    def drawPreview(self):
        # a pool of its own: the images a frame is made of are let go as soon as
        # it is on screen, instead of piling up until the app comes up for air
        with objc.autorelease_pool():
            self.paintPreview()

    def paintPreview(self):
        cw, ch = self.cfg["canvas"]
        maxW, maxH = getattr(self, "canvasMax", (CANVAS_MAX_W, CANVAS_MAX_H))
        fit = min(float(maxW) / cw, float(maxH) / ch, 1.0)
        pw, ph = max(2, int(cw * fit)), max(2, int(ch * fit))
        # render at the screen's physical resolution, not at point size
        bs = self._backing
        progress = self.progressAt(self.phase)
        values = self.axisValues(progress)
        for i, (ident, a, b) in enumerate(self.cfg["ranges"]):
            slider = self.sliders[i]
            at = values.get(ident, a) if self.animate[i] else None
            slider.playhead = at
            slider.setNeedsDisplay_(True)
            getattr(self.w, "axNow%d" % i).set("%g" % round(at if at is not None else a, 1))
        self.updateClock()
        # the stage takes exactly the shape of the format, centred in its area
        if self.previewFitted != (pw, ph):
            self.previewFitted = (pw, ph)
            ax, ay, aw, ah = self.previewArea
            rect = (ax + (aw - pw) / 2.0, ay + (ah - ph) / 2.0, pw, ph)
            self.place(self.w.preview, rect)
            self.place(self.w.canvasBack, rect)

        cg = self.renderAt(progress, int(pw * bs), int(ph * bs),
                           self.cfg["size"] * fit * bs, at=self.clock)
        img = NSImage.alloc().initWithCGImage_size_(cg, (pw, ph))
        self.w.preview.setImage(imageObject=img)

    def tick(self, timer=None):
        # the film's own clock runs on through the cycles: a video backdrop
        # plays on as the text starts over, as it does in the MP4. It follows
        # the clock on the wall, not the count of frames drawn: a frame that
        # takes too long is skipped, and the film keeps its own time instead of
        # slowing down with the drawing.
        now = time.time()
        step = min(0.25, max(0.0, now - (self.lastTick or now - 1.0 / self.previewFPS())))
        self.lastTick = now
        self.clock += step
        self.phase += step / max(0.05, self.cfg["duration"])
        if self.phase >= 1.0:
            if self.cfg["mode"] == "Play once":
                self.phase = 1.0
                self.stopTimer()
                self.playing = False
                self.showTransport()
            else:
                self.phase -= 1.0
        self.drawPreview()

    def startTimer(self):
        self.stopTimer()
        self.lastTick = None
        # the preview never runs faster than 30 fps; the export keeps the real one
        self.timer = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            1.0 / self.previewFPS(), True, lambda t: self.tick(t))

    def stopTimer(self):
        if self.timer is not None:
            self.timer.invalidate()
            self.timer = None

    # -- callbacks -----------------------------------------------------------

    def pickAlign(self, index):
        self.alignIndex = index
        self.paintAlign()
        self.settingsChanged()

    def paintAlign(self):
        for i, control in enumerate(self.alignButtons):
            lit = (i == self.alignIndex)
            self.paintPill(control, "", fill=ACCENT if lit else None, radius=5)
            control.getNSButton().setContentTintColor_(
                NSColor.whiteColor() if lit else INK_TIME)

    def presetChanged(self, sender=None):
        name, pw, ph = PRESETS[self.w.preset.get()]
        if pw is None:                 # Custom: the fields already say it
            return
        self.w.canvasW.set(str(pw))
        self.w.canvasH.set(str(ph))
        self.settingsChanged()

    def syncPreset(self):
        """Name the format the canvas is at, and Custom when it is at none."""
        cw, ch = self.canvasSize()
        for i, (name, pw, ph) in enumerate(PRESETS):
            if pw == cw and ph == ch:
                self.w.preset.set(i)
                return
        self.w.preset.set(len(PRESETS) - 1)

    # -- colour: well and hex field ------------------------------------------

    def well(self, target):
        return getattr(self.w, target)

    def colourChanged(self, sender=None):
        for target in ("bg", "fg"):
            getattr(self.w, target + "Hex").set(
                hexFromNSColor(self.well(target).get()).upper())
        self.settingsChanged()

    def swapColours(self, sender=None):
        """Paper and Ink change places: the film in negative.

        Only the two wells are set. Everything downstream reads from them, and
        colourChanged writes the hex fields from the wells and tells the window
        the settings moved, so the frame is redrawn with no further help."""
        paper, ink = self.well("bg").get(), self.well("fg").get()
        self.well("bg").set(ink)
        self.well("fg").set(paper)
        self.colourChanged()

    def hexEdited(self, sender=None):
        """
        Typed text moves the well. It never comes back the other way.

        vanilla calls this on every keystroke, and the well's own callback
        writes the well's colour into both fields — so going through it meant
        the first character you typed put the old value straight back, and the
        field could not be edited at all.
        """
        for target in ("bg", "fg"):
            colour = nsColorFromHex(getattr(self.w, target + "Hex").get())
            if colour:
                self.well(target).set(colour)
        self.settingsChanged()

    def sliderChanged(self, slider):
        """A diamond was dragged: write it back into the number fields."""
        i = self.sliders.index(slider)
        getattr(self.w, "axFrom%d" % i).set("%g" % round(slider.lo, 2))
        getattr(self.w, "axTo%d" % i).set("%g" % round(slider.hi, 2))
        self.settingsChanged()

    def syncSliders(self):
        for i, (a, b) in enumerate(self.cfg["raw"]):
            slider = self.sliders[i]
            slider.lo, slider.hi = a, b
            slider.animating = self.animate[i]
            slider.setNeedsDisplay_(True)
            getattr(self.w, "axTo%d" % i).enable(self.animate[i])
        # while Fit is on the size is measured, not typed
        self.w.size.enable(not self.fitCheck.on)
        # and while Real time follows a video, the film's time is the clip's
        following = self.following()
        self.w.duration.enable(not following)
        self.w.fps.enable(not following)
        self.paintRealTime()
        # taking turns, the hint says in what order
        if self.cfg.get("alternate"):
            self.w.axesHint.set("one after another, adding up")
        elif self.cfg.get("random"):
            self.w.axesHint.set("each lane starting somewhere else")
        else:
            self.w.axesHint.set("static font \u00b7 no axes, so size and tracking move"
                                if self.static else "drag handles to set FROM \u2192 TO")

    def toggleAnimate(self, index):
        self.animate[index] = bool(self.axisChecks[index].on)
        self.settingsChanged()

    def toggleAlternate(self, sender=None):
        """One lane at a time and each starting somewhere else are two
        different ideas: ticking one lets the other go."""
        if self.alternateCheck.on and self.randomCheck.on:
            self.randomCheck.on = False
            self.randomCheck.setNeedsDisplay_(True)
        self.settingsChanged()

    def toggleRandom(self, sender=None):
        if self.randomCheck.on:
            if self.alternateCheck.on:
                self.alternateCheck.on = False
                self.alternateCheck.setNeedsDisplay_(True)
            self.rollOffsets()        # ticked again, the lanes are drawn again
        self.settingsChanged()

    def rollOffsets(self):
        """Where in the cycle each lane starts: one number drawn for each."""
        self.offsets = [random.random() for _ in self.axes]

    def toggleHide(self, index):
        self.hidden[index] = bool(self.hideChecks[index].on)
        self.settingsChanged()

    def settingsChanged(self, sender=None):
        self.syncConfig()
        try:                          # the shadow panel is the paper colour
            self.w.canvasBack.getNSView().layer().setBackgroundColor_(
                self.w.bg.get().CGColor())
        except Exception:
            pass
        self.syncSliders()
        self.syncPreset()
        self.updateInfo()
        if self.playing:
            self.startTimer()
        self.drawPreview()
        self.keepUp()

    def updateInfo(self):
        self.w.status.set("Ready · %.1f s × %d · %d fps"
                          % (self.cfg["duration"],
                             int(self.clamped(self.w.loops, 3, 1, 20)),
                             self.cfg["fps"]))

    # -- a part of the font ---------------------------------------------------

    def typed(self):
        """The box as it is drawn: \\n typed out is a line break."""
        return (self.w.text.get() or "").replace("\\n", "\n")

    def keepUp(self):
        """
        With a part of the font compiled: whether it still has all the panel
        asks for. Letters it lacks are exported once the typing stops; Cycle,
        which can run through every glyph there is, has the whole font
        exported straight away.
        """
        if self.kept is None or self.stuck:
            return
        if self.cycleCheck.on:
            self.later(0.05)
            return
        if self.charset is None:
            try:
                self.charset = CoreText.CTFontCopyCharacterSet(self.baseFont)
            except Exception:
                return
        lacking = [letter for letter in set(self.typed())
                   if not letter.isspace() and letter not in self.absent
                   and not self.charset.longCharacterIsMember_(ord(letter))]
        if lacking:
            self.later(0.6)
        else:
            self.cancelLater()

    def later(self, delay):
        """widen() in that many seconds: every call starts the wait over."""
        self.cancelLater()
        self.widenTimer = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            delay, False, lambda timer: self.widen())

    def cancelLater(self):
        if self.widenTimer is not None:
            self.widenTimer.invalidate()
            self.widenTimer = None

    def widen(self):
        """
        Export again: for Cycle the whole font, otherwise the part the box asks
        for now together with all there was, so going back costs nothing. The
        panel stands still while the export runs — a moment for a part, as
        long as ever for the whole font — and goes on with the new font.
        """
        self.widenTimer = None
        if self.kept is None or self.stuck:
            return
        letters, needed = self.letters, None
        if not self.cycleCheck.on:
            letters = self.letters | frozenset(
                letter for letter in self.typed() if not letter.isspace())
            needed = neededGlyphs(self.font, letters)
            if needed is not None and needed[0] <= self.kept:
                # nothing to add: what the font lacks the document lacks too,
                # and CoreText draws it from another font, as it always has
                self.absent = self.absent | frozenset(self.typed())
                return
        started = time.time()
        try:
            self.w.status.set("Exporting %s\u2026" % ("the new letters" if needed
                                                     else "the whole font"))
            self.w.getNSWindow().displayIfNeeded()
            path, kept = exportFont(self.font, self.staticOf, needed,
                                    self.setting)
            base = makeBaseFont(path)
        except Exception as trouble:
            # typing on will not make it work: no more tries until it reopens
            self.stuck = True
            print("Kinomat \u2014 no new export:\n%s" % trouble)
            self.w.status.set("No new export \u00b7 see the Macro panel")
            return
        self.baseFont, self.vfPath, self.kept, self.charset = base, path, kept, None
        if needed is not None:
            self.letters = letters
        self.settingsChanged()
        spent = time.time() - started
        if kept is None:
            self.w.status.set("Whole font exported in %.1f s" % spent)
        else:
            self.w.status.set("New letters exported in %.1f s \u00b7 %d of %d glyphs"
                              % (spent, len(kept), needed[2]))

    def scrubbed(self, sender=None):
        """Dragging the bar moves the animation, and stops it playing."""
        if self.playing:
            self.togglePlay()
        self.phase = max(0.0, min(1.0, self.scrub.value))
        self.clock = self.phase * self.cfg["duration"]
        self.updateClock()
        self.drawPreview()

    def updateClock(self):
        total = max(0.1, self.cfg["duration"])
        at = self.phase * total
        self.w.clock.set("%0.2f / %0.2f s" % (at, total))
        if not self.playing:
            return
        self.scrub.value = self.phase
        self.scrub.setNeedsDisplay_(True)

    def togglePlay(self, sender=None):
        self.playing = not self.playing
        if self.playing:
            if self.phase >= 1.0:
                self.phase = 0.0
                self.clock = 0.0
            self.startTimer()
            self.showTransport()
        else:
            self.stopTimer()
            self.showTransport()

    # -- export --------------------------------------------------------------

    def buildFrames(self):
        self.syncConfig()
        cw, ch = self.cfg["canvas"]
        size = self.cfg["size"]
        n = self.frameCount()
        fps = float(self.fps())
        frames = []
        for i in range(n):
            with objc.autorelease_pool():
                frames.append(self.renderAt(self.progressAt(i / float(n)),
                                            cw, ch, size, at=i / fps))
        return frames, cw, ch

    def filmFrames(self, repeats=1):
        """The film's frames, made one at a time as the writer asks for them,
        so that they are never all held at once — and, over a moving backdrop,
        each repeat of the cycle its own, as the video runs on."""
        self.syncConfig()
        cw, ch = self.cfg["canvas"]
        size, n, fps = self.cfg["size"], self.frameCount(), float(self.fps())

        # How large the film is: the canvas, or twice it with 2× ticked — and
        # where it can be afforded it is drawn at twice that and brought back
        # down, so the letters' edges come out as smooth as they look on the
        # stage (drawn straight, the edges measured 32.5 against 12.1 this way).
        # A film is even on both sides, and past twelve million pixels to draw
        # there are enough already: it is drawn at the size it is.
        grade = float(self.filmStep or 1.0)
        if cw * grade > 4096 or ch * grade > 4096:
            grade = 1.0
        fw, fh = int(round(cw * grade)), int(round(ch * grade))
        fw -= fw % 2
        fh -= fh % 2
        step = 2 if fw * fh * 4 <= 12000000 else 1
        dw, dh = fw * step, fh * step
        grow = dw / float(cw)

        def frames():
            for k in range(n * repeats):
                with objc.autorelease_pool():
                    frame = self.renderAt(self.progressAt((k % n) / float(n)),
                                          dw, dh, size * grow, at=k / fps)
                    if step > 1:
                        frame = shrunk(frame, fw, fh)
                yield frame
        return frames(), fw, fh

    def defaultName(self):
        """What files are called: after the project saved or opened last, or
        else after the font — as the Name field does in the tools on the web."""
        if self.projectName:
            return self.projectName
        return (self.font.familyName or "Kinomat").replace(" ", "") + "-kinomat"

    def openTools(self, sender=None):
        """Straight to the checkout, not to the page that links to it."""
        self.openPage(BUY_URL)

    def openSite(self, sender=None):
        """The tools page, for reading rather than buying."""
        self.openPage(TOOLS_URL)

    def openPage(self, url):
        try:
            NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(url))
        except Exception:
            os.system('open "%s"' % url)

    def proName(self):
        return Glyphs.defaults.get(NAME_DEFAULT, "") or ""

    def isPro(self):
        """Verified at least once on this machine, and remembered.

        On the key alone: a licence with no name against it is still a licence,
        and requiring the name turned valid keys away."""
        return bool(Glyphs.defaults.get(KEY_DEFAULT))

    def paintKey(self, failed=False):
        """
        The key, up in the title bar beside the name of the font.

        As wide as what it says — a company's name is longer than "Insert Key"
        — so the bar is measured again around it every time it changes.
        """
        pro = self.isPro()
        title = (self.proName() or "Activated") if pro else "Insert Key"
        colour = GREEN_TEXT if pro else ACCENT_TEXT
        control = getattr(self, "keyControl", None)
        if control is not None:
            self.paintPill(control, title, radius=6, size=11, colour=colour,
                           border=colour,
                           fill=GREEN_TINT if pro else ACCENT_TINT)
            try:
                # set by hand, as pill() does it: vanilla grows a button's
                # frame, and the title bar has no room to spare
                width = int(textWidth(title, uiFont(11))) + 22
                beside = self.titleLabel.frame().size.width
                control._nsObject.setFrame_(((beside + 2, 4), (width, 20)))
                self.titleHolder.setFrameSize_((beside + 2 + width + 12, 28))
            except Exception:
                pass
        # the buttons stay live: a dead button cannot say why it is dead, and
        # it is the click itself that opens the sheet
        for button in (self.w.gif, self.w.mp4, self.w.png):
            button.enable(True)

    def showTransport(self):
        """Play or pause, as an SF Symbol with the text triangle as a fallback."""
        button = self.w.play.getNSButton()
        image = symbol("pause.fill" if self.playing else "play.fill")
        if image is not None:
            button.setImage_(image)
            button.setContentTintColor_(NSColor.whiteColor())
            button.setImagePosition_(NSImageOnly)
            # both titles: setTitle_ alone leaves the attributed one drawing,
            # and the button shows the symbol with "Play" beside it
            button.setTitle_("")
            button.setAttributedTitle_(
                NSAttributedString.alloc().initWithString_(""))
        else:
            self.setButtonTitle(self.w.play, "❚❚" if self.playing else "▶")

    def showKey(self, sender=None):
        """The same sheet, opened to read the serial rather than to ask for one."""
        self.askForKey()

    def askForKey(self, pending=None):
        """
        The licence sheet.

        Same panel, smaller: painted surfaces, a field that shows it is the
        thing to type in, and a foot listing what the key already covers —
        which is the argument for buying one, and the reason not to sell a
        licence per tool.
        """
        self.pending = pending
        held = Glyphs.defaults.get(KEY_DEFAULT, "") or ""
        W, H = 436, 328
        left, right = 24, 412
        wide = right - left

        self.sheet = vanilla.Sheet((W, H), self.w)
        s = self.sheet
        try:
            s.getNSWindow().setBackgroundColor_(SURF_WINDOW)
        except Exception:
            pass

        # ---- the foot, before anything stands on it ---------------------
        footY = 238
        self.zone("footZone", (0, footY, W, H - footY), tone("#F5F5F7"), into=s)
        self.zone("footRule", (0, footY, W, 1), LINE_DIVIDER, into=s)

        # ---- what it is ---------------------------------------------------
        self.caption("title", left, 22, 220, "Kinomat Pro key", INK, 16,
                     weight=NSFontWeightSemibold, height=22, into=s)
        self.caption("brand", right - 180, 26, 180,
                     ("RESISTENZA TYPE  %s" % VERSION) if VERSION
                     else "RESISTENZA TYPE", INK_FAINT,
                     10, align=NSTextAlignmentRight, weight=NSFontWeightBold,
                     height=14, into=s, kern=0.9)
        # the foot already names what the key covers: the line on top says it
        # once and points down there, instead of arguing the same case twice
        self.caption("blurb", left, 48, wide,
                     ("Registered to %s. Everything below is open."
                      % self.proName()) if held and self.proName()
                     else "Export needs a Pro key — the same one that opens "
                          "the tools below.",
                     INK_LABEL, 12.5, height=38, into=s, wraps=True)

        mono = NSFont.monospacedSystemFontOfSize_weight_(13, NSFontWeightRegular) \
            if hasattr(NSFont, "monospacedSystemFontOfSize_weight_") \
            else NSFont.userFixedPitchFontOfSize_(13)
        self.field("key", left, 102, wide, held, callback=self.typedKey,
                   height=40, align=NSTextAlignmentLeft, into=s, font=mono,
                   radius=9, inset=12, rightInset=56)
        # AppKit rings a focused field in the accent colour, and around the
        # frame vanilla asks for, not around the box drawn behind it: an orange
        # halo standing off the field on every side. The box is the border.
        try:
            s.key.getNSTextField().setFocusRingType_(NSFocusRingTypeNone)
            s.key.getNSTextField().cell().setFocusRingType_(NSFocusRingTypeNone)
        except Exception:
            pass
        # the box holds both, so the second one is drawn over it, not beside it
        s.key.getNSTextField().setPlaceholderString_("RSZ-0000-0000-0000")
        self.caption("status", right - 52, 113, 40, "", INK_FAINT, 13,
                     align=NSTextAlignmentRight, weight=NSFontWeightBold,
                     into=s)
        self.caption("note", left, 150, wide,
                     "Paste it from the receipt email. Checked once, then "
                     "remembered — it works offline after that.",
                     INK_MUTED, 11, height=30, into=s, wraps=True)

        # ---- what to do about it -------------------------------------------
        y = 184
        self.pill("buy", left, y, self.wideEnough("Deactivate" if held
                                                  else "Get a key", 28),
                  32, "Deactivate" if held else "Get a key",
                  self.deactivate if held else self.openTools,
                  into=s, containerH=H, fill=SURF_FIELD, border=LINE_FIELD,
                  colour=INK_BUTTON, weight=NSFontWeightMedium, radius=8)
        width = self.wideEnough("Activate", 36, NSFontWeightSemibold)
        self.pill("ok", right - width, y, width, 32, "Activate", self.activate,
                  into=s, containerH=H, fill=ACCENT,
                  colour=NSColor.whiteColor(), weight=NSFontWeightSemibold,
                  radius=8)
        cancel = self.wideEnough("Cancel", 28)
        self.pill("cancel", right - width - 8 - cancel, y, cancel, 32, "Cancel",
                  self.closeSheet, into=s, containerH=H, fill=SURF_FIELD,
                  border=LINE_FIELD, colour=INK_BUTTON,
                  weight=NSFontWeightMedium, radius=8)

        # ---- and what it already covers -------------------------------------
        self.caption("kicker", left, footY + 16, 240, "INCLUDED WITH YOUR KEY",
                     INK_MUTED, 10, weight=NSFontWeightBold, height=14,
                     into=s, kern=0.9)
        self.pill("alltools", right - 90, footY + 14, 90, 16,
                  "All tools ↗", self.openSite, into=s, containerH=H,
                  colour=ACCENT, size=11, weight=NSFontWeightMedium, radius=0,
                  align=NSTextAlignmentRight)
        card = (wide - 12) / 3.0
        for i, name in enumerate(TOOLS):
            x = left + i * (card + 6)
            self.pill("tool%d" % i, x, footY + 40, int(card), 32, name,
                      self.openSite, into=s, containerH=H, fill=SURF_FIELD,
                      border=LINE_DIVIDER, colour=INK_BUTTON, radius=8)
            mark = NSMutableAttributedString.alloc().init()
            mark.appendAttributedString_(attributed(
                "%02d  " % (i + 1),
                NSFont.monospacedSystemFontOfSize_weight_(11, NSFontWeightBold)
                if hasattr(NSFont, "monospacedSystemFontOfSize_weight_")
                else uiFont(11, NSFontWeightBold), ACCENT))
            mark.appendAttributedString_(attributed(
                name, uiFont(12, NSFontWeightSemibold), INK_BUTTON))
            getattr(s, "tool%d" % i).getNSButton().setAttributedTitle_(mark)

        s.setDefaultButton(s.ok)
        drawSmaller(s.getNSWindow(), (W, H))
        s.open()

    def wideEnough(self, title, padding, weight=None):
        return int(textWidth(title, uiFont(12, weight))) + padding

    def typedKey(self, sender=None):
        """A key half typed is neither right nor wrong: clear the last verdict."""
        self.sheet.status.set("")

    def deactivate(self, sender=None):
        """Give the key back: this machine forgets it, the licence is untouched."""
        Glyphs.defaults[KEY_DEFAULT] = ""
        Glyphs.defaults[NAME_DEFAULT] = ""
        self.closeSheet()
        self.paintKey()

    def closeSheet(self, sender=None):
        try:
            self.sheet.close()
        except Exception:
            pass
        self.sheet = None

    def sheetSays(self, mark, note, colour=INK_MUTED):
        """The verdict in the field, the reason under it."""
        self.sheet.status.set(mark)
        self.sheet.status.getNSTextField().setTextColor_(colour)
        self.sheet.note.set(note)
        self.sheet.note.getNSTextField().setTextColor_(colour)
        try:                      # the check blocks: paint before it starts
            self.sheet.getNSWindow().displayIfNeeded()
        except Exception:
            pass

    def activate(self, sender=None):
        key = (self.sheet.key.get() or "").strip()
        self.sheetSays("\u2026", "Asking resistenza.es about this key\u2026")
        ok, name = verifyKey(key)
        if ok is None:
            self.sheetSays("!", "Could not reach resistenza.es \u2014 %s. The "
                           "key can only be checked online the first time."
                           % name[:60], ACCENT_TEXT)
            return
        if not ok:
            self.sheetSays("\u2717", "That key is not valid. Check it and "
                           "try again.", ACCENT_TEXT)
            return
        Glyphs.defaults[KEY_DEFAULT] = key
        Glyphs.defaults[NAME_DEFAULT] = name
        pending = self.pending
        self.closeSheet()
        self.paintKey()
        # straight on with whatever was asked for before the key was wanted
        if pending:
            pending()

    def blockedWithoutPro(self, pending=None):
        if self.isPro():
            return False
        self.askForKey(pending)
        return True

    def exportGIF(self, sender=None):
        if self.blockedWithoutPro(self.exportGIF):
            return
        path = putFile(fileTypes=["gif"], fileName=self.defaultName() + ".gif",
                       title="Export GIF")
        if not path:
            return
        wasPlaying = self.playing
        self.stopTimer()
        self.w.status.set("Rendering…")
        try:
            frames, cw, ch = self.filmFrames()
            writeGIF(path, frames, self.fps(), count=self.frameCount())
        except Exception as e:
            Message("Kinomat", "GIF export failed:\n%s" % e)
            return
        finally:
            if wasPlaying:
                self.startTimer()
        mb = os.path.getsize(path) / 1048576.0
        self.w.status.set("Saved · %s · %.1f MB" % (os.path.basename(path), mb))
        if mb > 8:
            Message("Kinomat", "The GIF is %.1f MB.\nLower the canvas, fps or "
                                 "duration to stay under 8 MB." % mb)

    def exportMP4(self, sender=None):
        if self.blockedWithoutPro(self.exportMP4):
            return
        path = putFile(fileTypes=["mp4"], fileName=self.defaultName() + ".mp4",
                       title="Export MP4")
        if not path:
            return
        wasPlaying = self.playing
        self.stopTimer()
        self.w.status.set("Rendering…")
        try:
            repeats = int(self.clamped(self.w.loops, 3, 1, 20))
            once = MODES[self.w.mode.get()] == "Play once"
            frames, cw, ch = self.filmFrames(1 if once else repeats)
            codec = writeMP4(path, frames, self.fps(), cw, ch,
                             wantHEVC=self.wantHEVC)
            if not codec:
                raise Exception("AVAssetWriter did not finish writing.")
        except Exception as e:
            Message("Kinomat", "MP4 export failed:\n%s" % e)
            return
        finally:
            if wasPlaying:
                self.startTimer()
        mb = os.path.getsize(path) / 1048576.0
        self.w.status.set("Saved · %s · %d×%d · %.1f MB · %s"
                          % (os.path.basename(path), cw, ch, mb, codec))

    def exportPNG(self, sender=None):
        """Every frame as its own PNG, in a folder named after the font."""
        if self.blockedWithoutPro(self.exportPNG):
            return
        folder = getFolder(messageText="Where should the frames go?")
        if not folder:
            return
        stem = self.defaultName()
        target = os.path.join(folder[0], stem)
        wasPlaying = self.playing
        self.stopTimer()
        self.w.status.set("Rendering…")
        written = 0
        try:
            if not os.path.isdir(target):
                os.makedirs(target)
            frames, cw, ch = self.filmFrames()
            written = 0
            for i, frame in enumerate(frames):
                with objc.autorelease_pool():
                    writePNG(os.path.join(target, "%s-%04d.png" % (stem, i + 1)),
                             frame)
                written = i + 1
        except Exception as e:
            Message("Kinomat", "PNG export failed:\n%s" % e)
            return
        finally:
            if wasPlaying:
                self.startTimer()
        self.w.status.set("Saved · %d frames · %s" % (written, stem))

    # -- the backdrop -----------------------------------------------------------

    def following(self):
        """Whether the film is taking its time from a video behind the text."""
        return bool(self.realTime and self.backdrop is not None
                    and self.backdrop.moving)

    def zoomed(self, sender=None):
        self.zoom = zoomFromBar(self.zoomSlider.value)
        self.paintZoom()
        self.settingsChanged()

    def turned(self, sender=None):
        self.turn = turnFromBar(self.turnSlider.value)
        self.paintTurn()
        self.settingsChanged()

    def paintTurn(self):
        """The bar where the angle says, and the angle beside it."""
        self.turnSlider.value = turnToBar(self.turn)
        self.turnSlider.setNeedsDisplay_(True)
        self.w.turnNote.set("%d°" % int(round(self.turn)))

    def speeded(self, sender=None):
        self.speed = speedFromBar(self.speedSlider.value)
        self.paintSpeed()
        # with Real time on, a faster video makes a shorter film
        self.applyRealTime()
        self.settingsChanged()

    def paintSpeed(self):
        """The bar where the speed says, and the speed beside it."""
        self.speedSlider.value = speedToBar(self.speed)
        self.speedSlider.setNeedsDisplay_(True)
        self.w.speedNote.set("%g×" % round(self.speed, 2))

    def brightened(self, sender=None):
        self.bright = brightFromBar(self.brightSlider.value)
        self.paintBright()
        self.settingsChanged()

    def paintBright(self):
        """The bar where the light says, and how much of it beside."""
        self.brightSlider.value = brightToBar(self.bright)
        self.brightSlider.setNeedsDisplay_(True)
        percent = int(round(self.bright * 100))
        self.w.brightNote.set("0%" if not percent else "%+d%%" % percent)

    def stepCodec(self, sender=None):
        """H.264 and HEVC, turn and turn about."""
        self.wantHEVC = not self.wantHEVC
        self.paintCodec()

    def paintCodec(self):
        """What it says, and \u2014 when it is the one that plays in fewer
        places \u2014 that it is doing something."""
        try:
            control = self.w.codecPill
        except Exception:
            return
        fine = bool(self.wantHEVC)
        self.paintPill(control, "HEVC" if fine else "H.264",
                       fill=ACCENT_TINT if fine else SURF_FIELD,
                       border=ACCENT_RANGE if fine else LINE_FIELD,
                       colour=ACCENT_TEXT if fine else INK_BUTTON,
                       weight=NSFontWeightMedium)

    def stepFilmSize(self, sender=None):
        """Round to the next size the film can come out at."""
        order = (1.0, 1.5, 2.0)
        here = min(range(len(order)),
                   key=lambda i: abs(order[i] - float(self.filmStep or 1.0)))
        self.filmStep = order[(here + 1) % len(order)]
        self.paintFilmSize()
        self.settingsChanged()

    def paintFilmSize(self):
        """What it says, and — when the film is larger than the canvas — that it
        is doing something."""
        grade = float(self.filmStep or 1.0)
        on = grade > 1.0
        self.paintPill(self.w.filmSize, ("%g×" % grade).replace(".", "."),
                       fill=ACCENT_TINT if on else SURF_FIELD,
                       border=ACCENT if on else LINE_FIELD,
                       colour=ACCENT_TEXT if on else INK_BUTTON,
                       weight=NSFontWeightMedium)

    def contrasted(self, sender=None):
        self.contrast = contrastFromBar(self.contrastSlider.value)
        self.paintContrast()
        self.settingsChanged()

    def paintContrast(self):
        """The bar where the contrast says, and how much of it beside."""
        self.contrastSlider.value = contrastToBar(self.contrast)
        self.contrastSlider.setNeedsDisplay_(True)
        percent = int(round(self.contrast * 100))
        self.w.contrastNote.set("0%" if not percent else "%+d%%" % percent)

    def paintZoom(self):
        """The bar where the size says, and the size beside it."""
        self.zoomSlider.value = zoomToBar(self.zoom)
        self.zoomSlider.setNeedsDisplay_(True)
        self.w.zoomNote.set("%d%%" % int(round(self.zoom * 100)))

    def toggleRealTime(self, sender=None):
        self.realTime = bool(self.realTimeBox.on)
        self.applyRealTime()
        self.settingsChanged()

    def applyRealTime(self):
        """
        Following a video, Duration and fps are the clip's: the cycle is one
        whole play of it, at its own speed, instead of a length of its own that
        cuts the clip or starts it over half way.

        What was typed before is kept, and comes back when the switch goes off
        or the video goes away.
        """
        if self.following():
            if self.ownTime is None:
                self.ownTime = (self.w.duration.get(), self.w.fps.get())
            # at twice the speed the clip is over in half the time
            self.w.duration.set(shortNumber(round(min(30.0, max(
                0.2, self.backdrop.duration / max(0.05, self.speed))), 2)))
            rate = int(round(self.backdrop.rate or 0))
            if 6 <= rate <= 60:
                self.w.fps.set("%d" % rate)
        elif self.ownTime is not None:
            self.w.duration.set(self.ownTime[0])
            self.w.fps.set(self.ownTime[1])
            self.ownTime = None
        self.paintRealTime()

    def paintRealTime(self):
        """Beside the switch: what the film is following, or what it waits for."""
        if self.following():
            rate = int(round(self.backdrop.rate or 0))
            note = "%s s%s of clip" % (shortNumber(round(self.backdrop.duration, 2)),
                                       (" at %d fps" % rate) if rate else "")
        elif self.realTime:
            note = "when a video is behind"
        else:
            note = ""
        self.w.realTimeNote.set(note)

    def tinted(self, image, w, h, tint, zoom=1.0, turn=0.0):
        """The backdrop in its two colours, at the size it is drawn. A still is
        the same in every frame, so its two-colour version is kept until the
        still, the size, the zoom or the colours change; a video's frames are
        each their own."""
        if self.backdrop is None or self.backdrop.moving:
            return duotone(image, w, h, tint[0], tint[1], zoom, turn)
        key = (self.backdrop, int(w), int(h), tint, zoom, turn)
        if self.tintCache is None or self.tintCache[0] != key:
            self.tintCache = (key, duotone(image, w, h, tint[0], tint[1], zoom, turn))
        return self.tintCache[1]

    def toggleTint(self, sender=None):
        self.tintOn = not self.tintOn
        self.paintTint()
        self.settingsChanged()

    def swapTint(self, sender=None):
        """The darks' colour to the lights and the other way round."""
        dark, light = self.w.tintDark.get(), self.w.tintLight.get()
        self.w.tintDark.set(light)
        self.w.tintLight.set(dark)
        self.settingsChanged()

    def paintTint(self):
        on = bool(self.tintOn)
        self.paintPill(self.w.tintOn, "On" if on else "Off",
                       fill=ACCENT_TINT if on else SURF_FIELD,
                       border=ACCENT if on else LINE_FIELD,
                       colour=ACCENT_TEXT if on else INK_MUTED,
                       weight=NSFontWeightMedium)

    def chooseBackdrop(self, sender=None):
        """An image or a video behind the text. Pro, as in the tools on the web."""
        if self.blockedWithoutPro(self.chooseBackdrop):
            return
        paths = getFile(fileTypes=IMAGE_TYPES + VIDEO_TYPES, title="Backdrop")
        if paths:
            self.setBackdrop(paths[0])

    def clearBackdrop(self, sender=None):
        self.setBackdrop(None)

    def setBackdrop(self, path):
        """The backdrop from that file, or none: whether it could be had. A file
        that cannot be read says why and leaves the backdrop as it was."""
        try:
            backdrop = Backdrop(path) if path else None
        except Exception as trouble:
            Message("Kinomat", str(trouble))
            return False
        if self.backdrop is not None and self.backdrop is not backdrop:
            self.backdrop.stopReading()
        self.backdrop = backdrop
        self.paintBackdrop()
        self.applyRealTime()
        self.settingsChanged()
        return True

    def paintBackdrop(self):
        """The row says what is behind the text; its ✕ is there when something is."""
        name = self.backdrop.name if self.backdrop is not None else "Image or video…"
        if len(name) > 24:
            name = name[:12] + "…" + name[-10:]
        self.paintPill(self.w.backdropPick, name, fill=SURF_FIELD,
                       border=LINE_FIELD, colour=INK_BUTTON,
                       weight=NSFontWeightMedium)
        self.w.backdropClear.show(self.backdrop is not None)
        self.showMediaRows()

    def showMediaRows(self):
        """
        Only the rows the backdrop has a use for: none without one, all but the
        film's own two for a still, every one of them for a film. The rows shown
        close up under Media in their order, so a still leaves no gap where
        Real time and Speed would be.

        Moved as views, by how far they stand from where they were built, and
        never laid out again through vanilla: the panel is drawn at UI_SCALE,
        and vanilla would flip a new position against a height the window no
        longer has. The content view is not flipped, so up is a larger y.
        """
        rows = getattr(self, "mediaRows", None)
        if not rows:
            return
        views = []
        for kind, names in rows:
            found = []
            for name in names:
                thing = getattr(self.w, name, None)
                found.append(getattr(thing, "_nsObject", None))
            views.append(found)
        if self.mediaBuilt is None:
            self.mediaBuilt = [[(v.frame().origin.x, v.frame().origin.y) if v is not None else None
                                for v in row] for row in views]
        film = self.backdrop is not None and self.backdrop.moving
        step = FIELD_H + 8
        shown = 0
        for index, ((kind, names), row, built) in enumerate(zip(rows, views, self.mediaBuilt)):
            wanted = self.backdrop is not None and (kind == "any" or film)
            lift = (index - shown) * step       # the rows hidden above it
            for view, origin in zip(row, built):
                if view is None:
                    continue
                view.setHidden_(not wanted)
                if origin is not None:
                    view.setFrameOrigin_((origin[0], origin[1] + lift))
            if wanted:
                shown += 1

    # -- a project: the settings as a file of their own -----------------------

    def projectData(self):
        """
        Everything the panel is set to, as plain data for a .rsztools file:
        JSON that says which app it is for, like the projects of the tools on
        the web.

        The font is not in it. A project takes the font of the Glyphs file that
        is open, and its lanes go back to the axes with the same tag.
        """
        self.syncConfig()
        lanes = []
        for i, ax in enumerate(self.axes):
            a, b = self.cfg["raw"][i]
            lanes.append({"tag": laneKey(ax), "name": ax.get("name", ""),
                          "from": a, "to": b, "animate": bool(self.animate[i]),
                          "hide": bool(self.hidden[i])})
        return {
            "app": PROJECT_APP,
            "v": 1,
            "saved": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "plugin": VERSION or "",
            "font": self.font.familyName or "",
            "text": self.w.text.get() or "",
            "size": self.num(self.w.size, 200.0),
            "fit": bool(self.fitCheck.on),
            "leading": self.num(self.w.lead, 110.0),
            "cycle": bool(self.cycleCheck.on),
            "tracking": self.num(self.w.track, 0.0),
            "sliders": bool(self.sliderCheck.on),
            "filmSize": float(self.filmStep or 1.0),
            "align": ALIGNMENTS[self.alignIndex],
            "duration": self.num(self.w.duration, 2.0),
            "fps": int(round(self.num(self.w.fps, 30))),
            "easing": EASE_NAMES[self.w.ease.get()],
            "loop": MODES[self.w.mode.get()],
            "animate": UNITS[self.w.unit.get()],
            "repeat": int(round(self.num(self.w.loops, 3))),
            "canvas": [int(round(self.num(self.w.canvasW, 1080))),
                       int(round(self.num(self.w.canvasH, 1080)))],
            "paper": hexFromNSColor(self.w.bg.get()).upper(),
            "ink": hexFromNSColor(self.w.fg.get()).upper(),
            "alternate": bool(self.alternateCheck.on),
            "lanes": lanes,
            # where it is: a project is settings, the file stays where it was
            "backdrop": self.backdrop.path if self.backdrop is not None else None,
            "realTime": bool(self.realTime),
            "zoom": self.zoom,
            "rotate": self.turn,
            "speed": self.speed,
            "bright": self.bright,
            "contrast": self.contrast,
            "random": bool(self.randomCheck.on),
            "offsets": [round(float(v), 4) for v in self.offsets],
            "colorize": {"on": bool(self.tintOn),
                         "dark": hexFromNSColor(self.w.tintDark.get()).upper(),
                         "light": hexFromNSColor(self.w.tintLight.get()).upper()},
        }

    def reskinLanes(self, axes):
        """
        The lanes made to read other axes, with the window left standing.

        Two variable settings of one document often vary along the same number
        of axes — a Serif and a Sans built over the same masters vary along
        both of theirs — and then every piece of every lane is already
        there: only what it says has to change. Nothing is taken down and
        nothing is put up, so the panel does not blink and nothing moves,
        which was the whole trouble: the window was being built again for
        lanes that had not changed shape.

        A range that was typed is kept where the new axis has room for it,
        matched by tag the way a project's lanes are. A lane that turns out to
        be another axis altogether opens on that axis's whole range.
        """
        was = {}
        for i, ax in enumerate(self.axes):
            try:
                was[laneKey(ax)] = (
                    self.num(getattr(self.w, "axFrom%d" % i), ax["min"]),
                    self.num(getattr(self.w, "axTo%d" % i), ax["max"]))
            except Exception:
                pass
        self.axes = axes
        for i, ax in enumerate(axes):
            unit = ax.get("unit", "")
            a, b = was.get(laneKey(ax), (ax.get("from", ax["min"]),
                                         ax.get("to", ax["max"])))
            a = min(max(a, ax["min"]), ax["max"])
            b = min(max(b, ax["min"]), ax["max"])
            box = self.axisChecks[i]
            box.label = ax["name"]
            box.setNeedsDisplay_(True)
            getattr(self.w, "axMin%d" % i).set("%g%s" % (ax["min"], unit))
            getattr(self.w, "axMax%d" % i).set("%g%s" % (ax["max"], unit))
            getattr(self.w, "axFrom%d" % i).set(shortNumber(a))
            getattr(self.w, "axTo%d" % i).set(shortNumber(b))
            slider = self.sliders[i]
            slider.mn, slider.mx = ax["min"], ax["max"]
            slider.lo, slider.hi = a, b
            slider.setNeedsDisplay_(True)
        self.paintTitle()

    def pickSetting(self, sender=None):
        """
        Another of the document's variable exports chosen in the panel.

        The work waits for the next turn of the run loop, because it ends by
        building the window again: a window must not be taken down from
        inside the action of a control standing in it, or the popup that
        called has the floor pulled from under it.
        """
        try:
            wanted = int(self.w.vfPick.get())
        except Exception:
            return
        if wanted == self.setting:
            return
        self.w.status.set("Exporting %s\u2026" % (
            self.settingNames[wanted] if wanted < len(self.settingNames)
            else "the setting"))
        self.cancelSwitch()
        self.switchTimer = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            0.0, False, lambda timer: self.switchSetting(wanted))

    def cancelSwitch(self):
        """The waiting change of setting called off: the panel closing, or
        another one chosen before this one got its turn."""
        if self.switchTimer is not None:
            self.switchTimer.invalidate()
            self.switchTimer = None

    def switchSetting(self, wanted):
        """
        Another of the document's variable exports into the panel.

        Its axes are not the other's — a Stencil setting varies along a
        stencil axis the Roman one does not have — so the lanes have to be
        built again, and with them the window they stand in. Everything that
        was set is carried across the way a project is, which is the road a
        saved project already takes back in: a lane whose axis the new setting
        does not have is left behind, the rest arrives as it was.

        When the chosen setting cannot export, nothing changes: the popup goes
        back to the one that is playing and the status line says so.
        """
        self.switchTimer = None
        if wanted == self.setting:
            return
        was = self.setting if self.setting is not None else 0
        # the plain name for what is said about it: "Roman (not exported) did
        # not export" is not a sentence worth reading
        plain = settingLabels(self.font, plain=True)
        name = plain[wanted] if wanted < len(plain) else "the setting"
        try:
            carried = self.projectData()
        except Exception:
            carried = None
        self.stopTimer()
        self.stopStepping()
        self.cancelLater()
        # a part of the font, as it was exported for the text that is in the
        # box; with the whole font in hand, the whole font again
        needed = None
        if self.kept is not None:
            needed = neededGlyphs(self.font, self.letters)
        started = time.time()
        try:
            how = "cached"
            path, kept = cachedFont(self.font, None, needed, wanted)
            if not path:
                how = "exported"
                path, kept = exportFont(self.font, None, needed, wanted)
            base = makeBaseFont(path)
            axes = fontAxes(base)
        except Exception as trouble:
            self.w.vfPick.set(was)
            self.w.status.set("%s did not export \u00b7 see the Macro panel" % name)
            print("Kinomat \u2014 %s did not export:\n%s" % (name, trouble))
            self.startStepping()
            return

        self.setting = wanted
        self.vfPath, self.kept, self.baseFont = path, kept, base
        self.staticOf = None
        self.charset = None
        self.stuck = False
        self.absent = frozenset()
        self.vfName = settingName(self.font, wanted)
        missing = None

        # As many lanes as before, and real axes on both sides: the lanes
        # standing are made to read the new axes and the window is not touched
        # at all. Only a different number of them — or a setting that came
        # out with no axes to show — asks for the panel to be built again.
        if axes and not self.static and len(axes) == len(self.axes):
            self.reskinLanes(axes)
            self.startStepping()
            if self.playing:
                self.startTimer()
            self.settingsChanged()
        else:
            self.axes = axes
            self.static = not self.axes
            if self.static:
                self.axes = staticLanes()
            # The window is built again around the new lanes, and the old one
            # goes behind it: at the same top left corner, and in that order,
            # or the panel blinks out and comes back somewhere else. It must
            # not take the export with it on the way out, nor the new window's
            # own timers: rebuilding holds windowClosed off until it has gone.
            # And buildUI ends by starting the film, which it does by turning
            # it on from off, so off is where it has to find it.
            old = self.w
            try:
                frame = old.getNSWindow().frame()
                self.openAt = (frame.origin.x, frame.origin.y + frame.size.height)
            except Exception:
                self.openAt = None
            self.playing = False
            self.rebuilding = True
            self.buildUI()
            try:
                old.close()
            except Exception:
                pass
            self.rebuilding = False
            self.openAt = None
            if carried is not None:
                try:
                    missing = self.applyProject(carried)
                except Exception as trouble:
                    print("Kinomat \u2014 the settings did not all carry "
                          "across:\n%s" % trouble)
        note = "%s \u00b7 %d %s %s in %.1f s" % (
            self.vfName or name, len(self.axes),
            "axis" if len(self.axes) == 1 else "axes", how,
            time.time() - started)
        if missing:
            note += " \u00b7 %s left behind" % ", ".join(missing)
        self.w.status.set(note)

    def saveProject(self, sender=None):
        """The settings to a .rsztools file, where you choose. Pro, as projects
        are in the tools on the web."""
        if self.blockedWithoutPro(self.saveProject):
            return
        path = putFile(fileTypes=["rsztools"], title="Save Project",
                       fileName=self.defaultName() + ".rsztools")
        if not path:
            return
        import json
        try:
            text = json.dumps(self.projectData(), ensure_ascii=False, indent=1)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        except (OSError, TypeError, ValueError) as trouble:
            Message("Kinomat", "The project was not saved:\n%s" % trouble)
            return
        self.projectName = os.path.splitext(os.path.basename(path))[0]
        self.w.status.set("Saved · %s" % os.path.basename(path))

    def openProject(self, sender=None):
        """
        A .rsztools file back into the panel: one Kinomat saved in Glyphs. A
        project of the tools on the web holds settings this panel does not
        have, so it is turned away, with the reason, and nothing changes.
        """
        if self.blockedWithoutPro(self.openProject):
            return
        paths = getFile(fileTypes=["rsztools"], title="Open Project")
        if not paths:
            return
        path = paths[0]
        name = os.path.basename(path)
        import json
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = None
        app = data.get("app") if isinstance(data, dict) else None
        if app != PROJECT_APP:
            if app == "cinema":
                why = ("%s is a project of Kinomat on the web: its settings are "
                       "not this panel's, and it opens there." % name)
            elif isinstance(app, str) and app:
                why = "%s is a project of %s, not of Kinomat." % (
                    name, app.capitalize())
            else:
                why = "%s is not a Kinomat project." % name
            Message("Kinomat", why)
            return
        missing = self.applyProject(data)
        self.projectName = os.path.splitext(name)[0]
        note = "Opened · %s" % name
        if missing:
            note += " · %s not in this font" % ", ".join(missing)
        if self.lostBackdrop:
            note += " · %s not found" % self.lostBackdrop
        self.w.status.set(note)

    def applyProject(self, data):
        """
        A project's settings into the panel's controls, then one
        settingsChanged(), which reads them as it reads a click. A setting that
        is missing or unreadable leaves its control as it is, so a project from
        an older or a newer Kinomat opens as far as it can. Returns the lanes
        of the project that the font has no axis for.
        """
        def usable(value):
            return isinstance(value, (int, float)) and not isinstance(value, bool)

        def number(key, field, whole=False):
            if usable(data.get(key)):
                getattr(self.w, field).set(shortNumber(data[key], whole))

        def tick(key, box):
            if isinstance(data.get(key), bool):
                box.on = data[key]
                box.setNeedsDisplay_(True)

        def choose(key, popup, names):
            if data.get(key) in names:
                getattr(self.w, popup).set(names.index(data[key]))

        if isinstance(data.get("text"), str):
            self.w.text.set(data["text"])
        number("size", "size")
        tick("fit", self.fitCheck)
        number("leading", "lead")
        tick("cycle", self.cycleCheck)
        number("tracking", "track")
        tick("sliders", self.sliderCheck)
        if usable(data.get("filmSize")):
            self.filmStep = min(2.0, max(1.0, float(data["filmSize"])))
            self.paintFilmSize()
        elif data.get("double") is not None:      # saved when it was a 2× box
            self.filmStep = 2.0 if data["double"] else 1.0
            self.paintFilmSize()
        if data.get("align") in ALIGNMENTS:
            self.alignIndex = ALIGNMENTS.index(data["align"])
            self.paintAlign()
        number("duration", "duration")
        number("fps", "fps", True)
        choose("easing", "ease", EASE_NAMES)
        choose("loop", "mode", MODES)
        choose("animate", "unit", UNITS)
        number("repeat", "loops", True)
        canvas = data.get("canvas")
        if isinstance(canvas, list) and len(canvas) == 2 \
                and all(usable(value) for value in canvas):
            self.w.canvasW.set(shortNumber(canvas[0], True))
            self.w.canvasH.set(shortNumber(canvas[1], True))
        for target, key in (("bg", "paper"), ("fg", "ink")):
            colour = (nsColorFromHex(data[key])
                      if isinstance(data.get(key), str) else None)
            if colour is not None:
                self.well(target).set(colour)
                getattr(self.w, target + "Hex").set(hexFromNSColor(colour).upper())
        tick("alternate", self.alternateCheck)
        tint = data.get("colorize")
        if isinstance(tint, dict):
            for key, target in (("dark", "tintDark"), ("light", "tintLight")):
                colour = (nsColorFromHex(tint[key])
                          if isinstance(tint.get(key), str) else None)
                if colour is not None:
                    getattr(self.w, target).set(colour)
            if isinstance(tint.get("on"), bool):
                self.tintOn = tint["on"]
            self.paintTint()

        # the backdrop, from where it was; one no longer there is said
        self.lostBackdrop = None
        if "backdrop" in data:
            path = data["backdrop"]
            if path is None:
                self.backdrop = None
            elif isinstance(path, str):
                try:
                    self.backdrop = Backdrop(path) if os.path.exists(path) else None
                    if self.backdrop is None:
                        self.lostBackdrop = os.path.basename(path)
                except Exception:
                    self.lostBackdrop = os.path.basename(path)
            self.paintBackdrop()
        if usable(data.get("zoom")):
            self.zoom = max(0.25, min(3.0, float(data["zoom"])))
            self.paintZoom()
        if usable(data.get("rotate")):
            self.turn = max(-180.0, min(180.0, float(data["rotate"])))
            self.paintTurn()
        if usable(data.get("speed")):
            self.speed = max(0.25, min(4.0, float(data["speed"])))
            self.paintSpeed()
        if usable(data.get("bright")):
            self.bright = max(-1.0, min(1.0, float(data["bright"])))
            self.paintBright()
        if usable(data.get("contrast")):
            self.contrast = max(-1.0, min(1.0, float(data["contrast"])))
            self.paintContrast()
        if isinstance(data.get("offsets"), list) and all(
                usable(v) for v in data["offsets"]):
            self.offsets = [float(v) % 1.0 for v in data["offsets"]]
        tick("random", self.randomCheck)
        if isinstance(data.get("realTime"), bool):
            self.realTime = data["realTime"]
            self.realTimeBox.on = self.realTime
            self.realTimeBox.setNeedsDisplay_(True)
        # the project's own Duration and fps are the ones to come back to
        self.ownTime = None
        self.applyRealTime()

        # the lanes go back to the axes with the same tag; the ones this font
        # has no axis for are said, not guessed at
        keys = [laneKey(ax) for ax in self.axes]
        lanes = data.get("lanes")
        missing = []
        for lane in lanes if isinstance(lanes, list) else []:
            if not isinstance(lane, dict) or not isinstance(lane.get("tag"), str):
                continue
            if lane["tag"] not in keys:
                missing.append(lane["tag"])
                continue
            i = keys.index(lane["tag"])
            ax = self.axes[i]
            for part, field in (("from", "axFrom%d" % i), ("to", "axTo%d" % i)):
                if usable(lane.get(part)):
                    value = min(max(float(lane[part]), ax["min"]), ax["max"])
                    getattr(self.w, field).set(shortNumber(value))
            for part, box, held in (("animate", self.axisChecks[i], self.animate),
                                    ("hide", self.hideChecks[i], self.hidden)):
                if isinstance(lane.get(part), bool):
                    held[i] = lane[part]
                    box.on = lane[part]
                    box.setNeedsDisplay_(True)
        self.settingsChanged()
        return missing

    def windowClosed(self, sender=None):
        # the panel built again around another variable setting closes its own
        # window on the way: the export it is about to show must stay
        if getattr(self, "rebuilding", False):
            return
        self.stopTimer()
        self.stopStepping()
        self.cancelLater()
        self.cancelSwitch()
        if self.backdrop is not None:
            self.backdrop.stopReading()
        # nothing of the font left behind: the font is in memory, and another
        # panel still open exports again if it needs to
        emptyCache()



# ----------------------------------------------------------------------------
# the plugin around it
# ----------------------------------------------------------------------------
from GlyphsApp.plugins import GeneralPlugin
from AppKit import (NSMenuItem, NSNotificationCenter,
                    NSApplicationWillTerminateNotification,
                    NSApplication, NSEventModifierFlagCommand,
                    NSEventModifierFlagOption, NSEventModifierFlagShift,
                    NSEventModifierFlagControl)

SHORTCUT = "k"   # with Command: the key that opens the window


def alreadyHolds(key):
	"""The menu item already answering to Command and this key, if any.

	Two items sharing a shortcut is not something macOS complains about: it
	hands the keystroke to the first one it meets walking the menus and the
	other simply never fires. Better to say so in the Macro window than to
	leave somebody wondering why nothing happens."""
	plain = NSEventModifierFlagCommand
	all_of_them = (NSEventModifierFlagCommand | NSEventModifierFlagOption
	               | NSEventModifierFlagShift | NSEventModifierFlagControl)
	wanted = key.lower()

	def walk(menu):
		for item in menu.itemArray():
			try:
				if (item.keyEquivalent().lower() == wanted
						and item.keyEquivalentModifierMask() & all_of_them == plain):
					return item.title()
			except Exception:
				pass
			below = item.submenu()
			if below is not None:
				found = walk(below)
				if found:
					return found
		return None

	try:
		return walk(NSApplication.sharedApplication().mainMenu())
	except Exception:
		return None


class KINOMATPlugin(GeneralPlugin):

	@objc.python_method
	def settings(self):
		self.name = "\U0001F3A5 Kinomat"

	@objc.python_method
	def start(self):
		# the whole of launch: one menu item, no window, no font touched
		try:
			item = NSMenuItem(self.name, self.openWindow_)
			# without a target the action goes up the responder chain, nobody
			# answers, and macOS greys the item out
			item.setTarget_(self)
			# ⌘K opens the window from anywhere in Glyphs
			taken = alreadyHolds(SHORTCUT)
			item.setKeyEquivalent_(SHORTCUT)
			item.setKeyEquivalentModifierMask_(NSEventModifierFlagCommand)
			if taken:
				print("Kinomat — ⌘%s already belongs to “%s”. macOS gives "
					"the keystroke to whichever menu it finds first, so one of "
					"the two will not answer." % (SHORTCUT.upper(), taken))
			Glyphs.menu[WINDOW_MENU].append(item)
		except Exception:
			import traceback
			print("Kinomat \u2014 menu:\n%s" % traceback.format_exc())

	def openWindow_(self, sender):
		self.sweepAtQuit()
		try:
			KINOMAT()
		except Exception:
			import traceback
			report = traceback.format_exc()
			print("Kinomat:\n%s" % report)
			Message("Kinomat", report.strip().splitlines()[-1])

	@objc.python_method
	def sweepAtQuit(self):
		"""Once, when a panel first opens: the cache emptied when Glyphs quits
		too. A window still open is not closed on the way out, so it never gets
		to empty the cache itself."""
		if getattr(self, "sweeping", False):
			return
		NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
			self, "kinomatWillQuit:", NSApplicationWillTerminateNotification, None)
		self.sweeping = True

	def kinomatWillQuit_(self, notification):
		emptyCache()

	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__
