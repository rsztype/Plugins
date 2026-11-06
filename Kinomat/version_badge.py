"""
Writes the version on the screenshot the Plugin Manager shows.

The Plugin Manager has no field for a version: it shows a title, a
description and a picture. Title and description sit in Glyphs' own registry,
where every change is a pull request; the picture is read from this repository
every time. So the version goes on the picture.

Run before every push:  python3 version_badge.py
Reads CFBundleShortVersionString from the bundle, draws it on
Kinomat-screen.png and writes Kinomat.png.
"""
import os
import plistlib
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
INFO = os.path.join(HERE, "Kinomat.glyphsPlugin", "Contents", "Info.plist")
SOURCE = os.path.join(HERE, "Kinomat-screen.png")
TARGET = os.path.join(HERE, "Kinomat.png")
FONT = "/Library/Fonts/Monologo-Bold.otf"
TITLE_FONT = "/Library/Fonts/Monologo-Medium.otf"   # where SF is not there
ORANGE = (255, 77, 0)

with open(INFO, "rb") as fh:
    version = plistlib.load(fh)["CFBundleShortVersionString"]
label = "v" + version

image = Image.open(SOURCE).convert("RGBA")   # the shadow round the window is transparent
w, h = image.size
draw = ImageDraw.Draw(image)

# the window's own title still names the version the picture was taken with:
# it is written again, in the system font, sized to cover the old one exactly
OLD_TITLE, TITLE_BOX = "Industria Serif \u2013 Kinomat 0.59", (143, 50, 336, 59)
try:
    def systemFont(px):
        try:
            f = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", px)
        except OSError:
            return ImageFont.truetype(TITLE_FONT, px)
        try: f.set_variation_by_name("Semibold")
        except Exception: pass
        return f
    want = TITLE_BOX[2] - TITLE_BOX[0]
    px = min(range(8, 30), key=lambda n: abs(draw.textlength(OLD_TITLE, font=systemFont(n)) - want))
    tf = systemFont(px)
    draw.rectangle((TITLE_BOX[0] - 3, TITLE_BOX[1] - 6, TITLE_BOX[2] + 12, TITLE_BOX[3] + 6), fill=(255, 255, 255, 255))
    capTop = draw.textbbox((0, 0), "I", font=tf)[1]
    draw.text((TITLE_BOX[0], TITLE_BOX[1] - capTop), "Industria Serif \u2013 Kinomat " + version,
              font=tf, fill=(77, 77, 79, 255))
except OSError:
    pass

# the badge sits inside the window, in the empty space of the left column
# under Align, big enough to be read in the Plugin Manager's small preview
AREA = (60, 372, 296, 518)          # left column, below the Text group
size = round(w * 0.03)
font = None
for f in (FONT, "/Library/Fonts/Performa-Bold.otf"):   # the first one that is installed
    try:
        font = ImageFont.truetype(f, size); break
    except OSError:
        pass
if font is None:
    raise SystemExit("No badge font installed: " + FONT)
box = draw.textbbox((0, 0), label, font=font)
tw, th = box[2] - box[0], box[3] - box[1]
padX, padY = round(size * 0.6), round(size * 0.4)
bw, bh = tw + 2 * padX, th + 2 * padY
x0 = (AREA[0] + AREA[2] - bw) // 2
y0 = (AREA[1] + AREA[3] - bh) // 2
x1, y1 = x0 + bw, y0 + bh
draw.rounded_rectangle((x0, y0, x1, y1), radius=bh // 2, fill=ORANGE + (255,))
draw.text((x0 + padX - box[0], y0 + padY - box[1]), label, font=font, fill=(255, 255, 255, 255))
image.save(TARGET, optimize=True)
print("Kinomat.png:", label)
