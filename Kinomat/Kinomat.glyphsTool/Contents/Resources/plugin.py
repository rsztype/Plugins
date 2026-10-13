# encoding: utf-8
"""
Kinomat in the toolbar: an icon among the tools that opens the panel.

The panel itself lives in KINOMAT.glyphsPlugin and is not repeated here — this
asks the menu item that plugin already registered to do its job, so there is
one copy of the code and one place to change it.

A tool is a mode, not a button: picking it would leave you holding it. So it
opens the panel and hands the pointer straight back, one turn of the run loop
later, once Glyphs has finished switching tools.

Two things went wrong with that, and a diary of every activation settled both.

Glyphs loads this bundle twice — start() writes its line twice at every launch
— so one press of the icon arrives at two instances and used to open two
panels. Nothing here can stop the second instance from existing, so the two
agree between themselves instead: the moment a panel is opened is written where
both can see it, and the one that arrives second within half a second says
nothing. The note goes in Glyphs' own defaults rather than in a variable,
because two loads of a module do not share their variables.

And Glyphs activates tools on its own as well, restoring the one a document was
saved with. Reading the event on the desk was not enough to tell that from a
person pressing the icon — opening a file from the dialog leaves the click that
opened it lying there. What does tell them apart is where that click landed:
the diary shows a real press at y=786 of a window 812 tall, in the strip along
the top where the toolbar is. A click that opened a file is somewhere else
entirely, and an activation with no click at all is the application talking to
itself.
"""
from __future__ import division, print_function, unicode_literals

import os
import time
import traceback

import objc
from AppKit import (
	NSApp,
	NSEventTypeKeyDown,
	NSEventTypeLeftMouseDown,
	NSEventTypeLeftMouseUp,
)
from GlyphsApp import Glyphs, Message
from GlyphsApp.plugins import SelectTool

NOTE = os.path.expanduser("~/Library/Caches/com.rsztype.Kinomat.activations.txt")

# Where the two loaded copies leave each other messages.
LAST_OPEN_KEY = "com.rsztype.Kinomat.lastOpened"

# How far down from the top of the window the toolbar reaches, and how long
# after opening a panel a second activation is taken for the twin of the first.
TOOLBAR_STRIP = 70.0
TWIN_WINDOW = 0.6

# How long to keep offering the pointer back before giving up, in turns of a
# fifth of a second. A document takes a moment to arrive; nothing takes ten.
HAND_BACK_TRIES = 10


def clickedTheIcon():
	"""
	Whether this activation is a person pressing the icon in the toolbar.

	A press leaves a mouse event in the document's own window, up in the strip
	where the tools are. Opening a file leaves a click too — in the open
	dialog, or none at all if it came from the Finder — and a document
	restoring its tool leaves nothing. Where the click landed is what
	separates them; that it exists is not enough.
	"""
	try:
		event = NSApp.currentEvent()
		if event is None or event.type() not in (
				NSEventTypeLeftMouseDown, NSEventTypeLeftMouseUp):
			return False
		window = event.window()
		content = window.contentView() if window is not None else None
		if content is None:
			return False
		return event.locationInWindow().y > (
			content.frame().size.height - TOOLBAR_STRIP)
	except Exception:
		return False


def alreadyOpening():
	"""
	Whether the other copy of this plugin has just opened the panel.

	Glyphs loads the bundle twice, so one press arrives twice. The first to
	arrive writes the time down where both can read it; the second finds it
	fresh and stands down.
	"""
	now = time.time()
	last = 0.0
	# read and write are kept apart on purpose: wrapped together, a reading
	# that throws would swallow the writing with it, and then neither copy
	# would ever find the other's mark — which is the failure that looks
	# exactly like having no guard at all
	try:
		stored = Glyphs.defaults[LAST_OPEN_KEY]
		last = float(stored) if stored else 0.0
	except Exception:
		last = 0.0

	if now - last < TWIN_WINDOW:
		return True

	try:
		Glyphs.defaults[LAST_OPEN_KEY] = now
	except Exception:
		pass
	return False


def describeEvent():
	"""The event on the desk, as a line: what kind, and in which window."""
	try:
		event = NSApp.currentEvent()
		if event is None:
			return "no event"
		window = event.window()
		title = "no window"
		if window is not None:
			title = window.title() or window.className()
		where = ""
		try:
			point = event.locationInWindow()
			content = window.contentView() if window is not None else None
			height = content.frame().size.height if content is not None else 0
			where = " at y=%.0f of %.0f" % (point.y, height)
		except Exception:
			pass
		return "type %s in %s%s" % (event.type(), title, where)
	except Exception:
		return "event unreadable"


def describeTool():
	"""Who Glyphs currently hands mouse events to."""
	try:
		font = Glyphs.font
		if font is None:
			return "no font"
		controller = font.parent.windowController()
		if controller is None:
			return "no window controller"
		tool = controller.toolEventDelegate()
		if tool is None:
			return "no delegate"
		if hasattr(tool, "currentTool"):
			inner = tool.currentTool()
			if inner is not None:
				tool = inner
		return tool.className()
	except Exception:
		return "unreadable"


def describeState():
	try:
		font = Glyphs.font
		if font is None:
			return "font: none"
		tabs = len(font.tabs) if hasattr(font, "tabs") else -1
		tab = "yes" if getattr(font, "currentTab", None) is not None else "no"
		return "font: %s, tabs: %s, currentTab: %s" % (
			font.familyName, tabs, tab)
	except Exception:
		return "font: unreadable"


def note(what):
	try:
		with open(NOTE, "a") as handle:
			handle.write("%s  %s\n" % (time.strftime("%H:%M:%S"), what))
	except Exception:
		pass


def openPanel():
	"""
	Fire the menu item the panel plugin put in the Window menu.

	By its title, because that is the only handle the two bundles share: they
	are separate plug-ins, loaded separately, and neither can import the other.
	"""
	menu = NSApp.mainMenu()
	for i in range(menu.numberOfItems()):
		submenu = menu.itemAtIndex_(i).submenu()
		if submenu is None:
			continue
		for j in range(submenu.numberOfItems()):
			item = submenu.itemAtIndex_(j)
			if "kinomat" in (item.title() or "").lower():
				action = item.action()
				if action is not None:
					NSApp.sendAction_to_from_(action, item.target(), item)
					return True
	return False


class KINOMATTool(SelectTool):

	@objc.python_method
	def settings(self):
		self.name = "Kinomat"
		# between the drawing tools and the ones that only look: this opens a
		# window rather than touching the outline
		self.toolbarPosition = 200
		self._icon = "ToolbarIconTemplate.pdf"
		self.handBackTries = 0

	@objc.python_method
	def start(self):
		note("--- Glyphs launched, Kinomat tool loaded ---")

	def activate(self):
		# give the pointer back whatever happens: this is a button wearing a
		# tool's clothes, and a document that saves it as its tool will call
		# for it again at every opening
		self.handBackTries = 0
		self.performSelector_withObject_afterDelay_("handBack", None, 0.0)

		asked = clickedTheIcon()
		try:
			note("activate | asked: %s | %s | tool: %s | %s" % (
				asked, describeState(), describeTool(), describeEvent()))
		except Exception:
			print("Kinomat — note:\n%s" % traceback.format_exc())

		if not asked or alreadyOpening():
			return

		try:
			if not openPanel():
				Message("Kinomat", "The Kinomat panel is not installed, or "
								   "Glyphs has not loaded it yet.")
		except Exception:
			print("Kinomat — toolbar:\n%s" % traceback.format_exc())

	def handBack(self):
		"""
		Give the pointer back to the select tool, and keep offering.

		With no font open there is nothing to set the tool on — which is the
		case while a document is still arriving, and the case in which leaving
		Kinomat as the current tool costs a panel at the next window. So it
		asks again in a moment, a few times, and then lets it be.
		"""
		try:
			font = Glyphs.font
			if font is not None:
				font.tool = "SelectTool"
				note("   handed the pointer back after %d tries" % self.handBackTries)
				return
		except Exception:
			pass

		try:
			self.handBackTries += 1
			if self.handBackTries <= HAND_BACK_TRIES:
				self.performSelector_withObject_afterDelay_("handBack", None, 0.2)
			else:
				note("   gave up handing the pointer back: no font")
		except Exception:
			pass

	@objc.python_method
	def __file__(self):
		"""Please leave this method unchanged"""
		return __file__
