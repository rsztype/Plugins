# encoding: utf-8
from __future__ import division, print_function, unicode_literals
import objc
from GlyphsApp import Glyphs, DOCUMENTEXPORTED
from GlyphsApp.plugins import PalettePlugin
from vanilla import Window, Group, TextBox
from Foundation import NSDate, NSMakeRect, NSTimer
from AppKit import NSViewWidthSizable, NSViewMinXMargin, NSControl, NSBezierPath, NSColor

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
# Custom-drawn pill switch: a plain NSSwitch can't be reshaped (its knob
# is drawn entirely by the system), so this hand-draws a round track and
# a circular knob instead. Subclasses NSControl (not NSView) to get
# target/action dispatch and .state() for free, matching NSSwitch's API
# closely enough that toggle_() below needs no changes.
# ----------------------------------------------------------------------
class _RSZPillSwitch(NSControl):

	def initWithFrame_(self, frame):
		self = objc.super(_RSZPillSwitch, self).initWithFrame_(frame)
		if self is None:
			return None
		self._on = False
		self._position = 0.0     # 0 = off, 1 = on; animates between the two
		self._animTarget = 0.0
		self._timer = None
		return self

	@objc.python_method
	def setOn_(self, on):
		self._on = bool(on)
		self._position = 1.0 if self._on else 0.0   # jump, no animation for the initial state
		self.setNeedsDisplay_(True)

	def state(self):
		return 1 if self._on else 0

	def drawRect_(self, rect):
		bounds = self.bounds()
		h = bounds.size.height
		track = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(bounds, h / 2.0, h / 2.0)
		(NSColor.controlAccentColor() if self._position >= 0.5 else NSColor.quaternaryLabelColor()).set()
		track.fill()

		d = h - 4
		x = 2 + (bounds.size.width - d - 4) * self._position
		knob = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(x, 2, d, d))
		NSColor.whiteColor().set()
		knob.fill()

	def mouseDown_(self, event):
		self._on = not self._on
		self._animTarget = 1.0 if self._on else 0.0
		if self._timer is None:
			self._timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
				1.0 / 60.0, self, "_tick:", None, True)
		self.sendAction_to_(self.action(), self.target())

	def _tick_(self, timer):
		diff = self._animTarget - self._position
		if abs(diff) < 0.01:
			self._position = self._animTarget
			timer.invalidate()
			self._timer = None
		else:
			self._position += diff * 0.35            # ease toward the target each frame
		self.setNeedsDisplay_(True)


# ----------------------------------------------------------------------
# Palette: the switch in the right-hand inspector column.
# ----------------------------------------------------------------------
class RSZVersionBumperPalette(PalettePlugin):

	@objc.python_method
	def settings(self):
		self.name = "Version Bumper"

		width = 160
		height = 30
		switch_width = 40
		self.paletteView = Window((width, height))
		self.paletteView.group = Group((0, 0, width, height))
		self.paletteView.group.label = TextBox((8, 7, width - 16 - switch_width, 18), "Increase Vers.", sizeStyle="small")
		self.paletteView.group.label.getNSView().setAlphaValue_(1.0 if Glyphs.defaults[PREF_KEY] else 0.4)

		groupView = self.paletteView.group.getNSView()
		groupView.setAutoresizingMask_(NSViewWidthSizable)

		# custom pill switch, built and attached defensively: if anything
		# about raw AppKit interop fails here, the rest of the palette (and
		# the export hook) should still come up rather than taking Glyphs down.
		try:
			sw = _RSZPillSwitch.alloc().initWithFrame_(NSMakeRect(0, 0, switch_width - 8, 14))
			sw.setOn_(bool(Glyphs.defaults[PREF_KEY]))
			frame = sw.frame()
			sw.setFrameOrigin_((width - 8 - frame.size.width, (height - frame.size.height) / 2))
			sw.setTarget_(self)
			sw.setAction_("toggle:")
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
		on = bool(sender.state())
		Glyphs.defaults[PREF_KEY] = on
		self.paletteView.group.label.getNSView().setAlphaValue_(1.0 if on else 0.4)

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
