# encoding: utf-8
"""
Increase Font Version on Export — counts the font version up, once per export.

Like Numeratore, but without the palette: no interface of its own, driven
only by the custom parameter it is named after, so the two can be installed
side by side without getting in each other's way.

Every export gets its own number without anyone remembering to type one: when
the export is done, versionMinor goes up by one and the .glyphs file is saved,
so the file you just made carries the version it was made with and the next one
will carry the next.

What it does is asked for by the font, not by a preference: a custom parameter
in Font Info > Font, which travels with the document and reads the same on
anyone's machine. A font that does not ask for it is left alone.

Putting the version into the name of the exported file is not this plugin's
job — Glyphs does that natively, with a template in the fileName parameter of
an export:

    {{{familyName}}}-{{{versionMajor}}}.{{{versionMinor}}}

That writes the number the font carries while the file is being written,
which is the number inside it. This plugin then moves the font on to the
next one, so the file the next export writes carries the next number.
"""
from __future__ import division, print_function, unicode_literals

import traceback

import objc
from GlyphsApp import Glyphs, GSGlyphsInfo, GSFont, DOCUMENTEXPORTED
from GlyphsApp.plugins import GeneralPlugin
from Foundation import NSDate

# The one thing to say, said in the font itself — typed into Font Info like
# any other custom parameter, there being no plugin UI to write it for you:
#
#   Increase Font Version on Export   1 → count the version up after an export
#
BUMP_PARAMETER = "Increase Font Version on Export"

# One export of a family writes one file per instance and calls back once for
# each: inside this many seconds they are one export, and count for one.
BATCH_WINDOW = 5.0

_lastBump = 0.0
_callbackRegistered = False


def _truthy(value):
	"""Whether a custom parameter is switched on, however it was written."""
	try:
		text = str(value).strip().lower()
	except Exception:
		return False
	return text not in ("", "0", "no", "off", "false", "none")


def _wanted(font):
	"""Whether the font asks to be counted up. A font that says nothing is left alone."""
	if font is None:
		return False
	try:
		value = font.customParameters[BUMP_PARAMETER]
	except Exception:
		return False
	return False if value is None else _truthy(value)


def _documentExported(info):
	global _lastBump
	try:
		font = Glyphs.font
		if not _wanted(font):
			return

		now = NSDate.date().timeIntervalSince1970()
		if now - _lastBump < BATCH_WINDOW:   # one increase per export, not per file
			return
		_lastBump = now

		font.versionMinor += 1
		if font.versionMinor > 999:          # rollover 1.999 -> 2.000
			font.versionMajor += 1
			font.versionMinor = 0

		if font.parent:                      # updates Font Info and saves
			font.parent.saveDocument_(None)

		Glyphs.showNotification(
			"Increase Font Version on Export",
			"Version → %d.%03d" % (font.versionMajor, font.versionMinor))
		print("Increase Font Version on Export: %s → %d.%03d"
			% (font.familyName, font.versionMajor, font.versionMinor))
	except Exception:
		print("Increase Font Version on Export error: %s" % traceback.format_exc())


def _ensure_engine():
	global _callbackRegistered
	if not _callbackRegistered:
		Glyphs.addCallback(_documentExported, DOCUMENTEXPORTED)
		_callbackRegistered = True


# ----------------------------------------------------------------------
# The plugin itself.
#
# Font Info draws a tick box only for the parameters it already knows about —
# but a plugin CAN add itself to that list, through GSGlyphsInfo, at launch.
# Nothing is written to disk: the parameter is registered fresh every time
# Glyphs starts, the way the app registers its own.
# ----------------------------------------------------------------------
class IncreaseFontVersionOnExport(GeneralPlugin):

	@objc.python_method
	def settings(self):
		self.name = "Increase Font Version on Export"

	@objc.python_method
	def start(self):
		_ensure_engine()   # registers the callback only once
		try:
			GSGlyphsInfo.addType_forParameter_forClass_(True, BUMP_PARAMETER, GSFont.__class__)
			GSGlyphsInfo.addDescription_forParameter_(
				"This increases the font.version on every font export", BUMP_PARAMETER)
		except Exception:
			print("Increase Font Version on Export -- registerCustomType:\n%s" % traceback.format_exc())

	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__
