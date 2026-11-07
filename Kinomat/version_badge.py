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

# the badge sits on the top right corner of the window, big enough to be
# read in the Plugin Manager's small preview
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
outline = image.split()[3].point(lambda v: 255 if v > 200 else 0).getbbox()
CORNER = (outline[2], outline[1])      # the window's top right corner, from its own outline
x0 = min(w - 4 - bw, CORNER[0] - bw // 2)
y0 = max(4, CORNER[1] - bh // 2)
x1, y1 = x0 + bw, y0 + bh
draw.rounded_rectangle((x0, y0, x1, y1), radius=bh // 2, fill=ORANGE + (255,))
draw.text((x0 + padX - box[0], y0 + padY - box[1]), label, font=font, fill=(255, 255, 255, 255))
image.save(TARGET, optimize=True)
print("Kinomat.png:", label)
