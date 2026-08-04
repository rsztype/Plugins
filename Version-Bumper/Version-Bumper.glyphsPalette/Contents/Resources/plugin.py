# encoding: utf-8
from __future__ import division, print_function, unicode_literals
import objc
from GlyphsApp import Glyphs, DOCUMENTEXPORTED
from GlyphsApp.plugins import PalettePlugin
from vanilla import Window, Group, TextBox
from Foundation import NSDate
from AppKit import NSViewWidthSizable, NSViewMinXMargin, NSControlSizeMini

PREF_KEY = "com.rsztype.RSZVersionBumper.enabled"


# ----------------------------------------------------------------------
# Shared export hook, registered once for the entire app regardless of
# how many windows/palettes are open. Uses Glyphs' own documented
# callback API (Glyphs.addCallback / DOCUMENTEXPORTED) instead of a
# hand-rolled NSObject/NSNotificationCenter observer, since that's the
# supported integration point across Glyphs versions.
# ----------------------------------------------------------------------
_lastBump = 0.0
_callbackRegistered = False


def _documentExported(info):
	global _lastBump
	try:
		if not Glyphs.defaults[PREF_KEY]:      # switch OFF -> does nothing
			return
		now = NSDate.date().timeIntervalSince1970()
		if now - _lastBump < 10.0:             # debounce for batch of instances
			return
		_lastBump = now

		font = Glyphs.font
		if font is None:
			return

		font.versionMinor += 1
		if font.versionMinor > 999:            # rollover 1.999 -> 2.000
			font.versionMajor += 1
			font.versionMinor = 0

		if font.parent:                        # updates Info panel and saves
			font.parent.saveDocument_(None)

		Glyphs.showNotification(
			"RSZ Version Bumper",
			"Version \u2192 %d.%03d" % (font.versionMajor, font.versionMinor)
		)
	except Exception:
		import traceback
		print("RSZ Version Bumper error: %s" % traceback.format_exc())


def _ensure_engine():
	global _callbackRegistered
	if not _callbackRegistered:
		Glyphs.addCallback(_documentExported, DOCUMENTEXPORTED)
		_callbackRegistered = True


# ----------------------------------------------------------------------
# Palette: the switch in the right-hand inspector column.
# ----------------------------------------------------------------------
class RSZVersionBumperPalette(PalettePlugin):

	@objc.python_method
	def settings(self):
		self.name = "Version Bumper"

		width = 160
		height = 30
		self.paletteView = Window((width, height))
		self.paletteView.group = Group((0, 0, width, height))
		self.paletteView.group.label = TextBox((8, 7, 90, 18), "Increase Version when Export", sizeStyle="small")

		groupView = self.paletteView.group.getNSView()
		groupView.setAutoresizingMask_(NSViewWidthSizable)

		# macOS switch (NSSwitch), built and attached defensively: if anything
		# about raw AppKit interop fails here, the rest of the palette (and
		# the export hook) should still come up rather than taking Glyphs down.
		try:
			NSSwitch = objc.lookUpClass("NSSwitch")
			sw = NSSwitch.alloc().init()
			sw.setControlSize_(NSControlSizeMini)
			sw.sizeToFit()                      # ask AppKit for the mini switch's real size
			frame = sw.frame()
			sw.setFrameOrigin_((width - 8 - frame.size.width, (height - frame.size.height) / 2))
			sw.setTarget_(self)
			sw.setAction_("toggle:")
			sw.setState_(1 if Glyphs.defaults[PREF_KEY] else 0)
			sw.setAutoresizingMask_(NSViewMinXMargin)
			groupView.addSubview_(sw)
			self.switch = sw
		except Exception:
			import traceback
			print("RSZ Version Bumper: could not create the switch control: %s" % traceback.format_exc())

		self.dialog = groupView

	@objc.python_method
	def start(self):
		_ensure_engine()   # registers the observer only once

	def toggle_(self, sender):
		Glyphs.defaults[PREF_KEY] = bool(sender.state())

	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__

	# Compatibility fix: Glyphs calls these methods on palettes.
	_sortID = 0

	@objc.python_method
	def setSortID_(self, sortID):
		try:
			self._sortID = sortID
		except Exception as e:
			self.logToConsole("setSortID_: %s" % str(e))

	@objc.python_method
	def sortID(self):
		return self._sortID
