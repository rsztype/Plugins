# encoding: utf-8
"""
magicPaste — paste the shapes you copied into every selected glyph.

Copy a shape with ⌘C, select the glyphs you want, then This Layer (current
master only) or All Layers (every layer of each glyph).
"""
from __future__ import division, print_function, unicode_literals
import objc
import GlyphsApp
from GlyphsApp import Glyphs
from GlyphsApp.plugins import PalettePlugin
from vanilla import Window, Group, Button
from AppKit import (NSPasteboard, NSViewWidthSizable, NSButton, NSColor, NSFont,
	NSTrackingArea, NSTrackingMouseEnteredAndExited, NSTrackingActiveInActiveApp,
	NSTrackingInVisibleRect, NSBezelStyleRounded, NSControlSizeSmall,
	NSMutableParagraphStyle, NSTextAlignmentCenter, NSForegroundColorAttributeName,
	NSFontAttributeName, NSParagraphStyleAttributeName)
from Foundation import NSMakeRect, NSAttributedString
from Foundation import NSPropertyListSerialization, NSPropertyListMutableContainers

# Glyphs' own pasteboard flavours, newest first.
GLYPHS_PASTEBOARD_TYPES = (
	"Glyphs elements pasteboard type v4",
	"Glyphs elements pasteboard type v3",
)

NODE_TYPES = {
	# the v3/v4 clipboard spells these out in caps
	"line": GlyphsApp.LINE,
	"curve": GlyphsApp.CURVE,
	"offcurve": GlyphsApp.OFFCURVE,
	"qcurve": GlyphsApp.QCURVE,
	# .glyphs-file shorthand, kept for older payloads
	"l": GlyphsApp.LINE, "ls": GlyphsApp.LINE,
	"c": GlyphsApp.CURVE, "cs": GlyphsApp.CURVE,
	"o": GlyphsApp.OFFCURVE,
	"q": GlyphsApp.QCURVE, "qs": GlyphsApp.QCURVE,
}

# Resistenza's fluor orange
ACCENT = NSColor.colorWithSRGBRed_green_blue_alpha_(1.0, 0x4D / 255.0, 0.0, 1.0)


def is_mapping(value):
	"""isinstance(x, dict) is False for a bridged NSDictionary, so duck-type."""
	return hasattr(value, "keys") and hasattr(value, "__getitem__")


def is_sequence(value):
	return (not isinstance(value, (str, bytes))
		and not is_mapping(value)
		and hasattr(value, "__iter__"))


def is_true(value):
	"""The clipboard writes booleans as the string ':true'."""
	if isinstance(value, str):
		return value.lower() in (":true", "true", "1", "yes")
	return bool(value)


# ----------------------------------------------------------------------
# Reading what ⌘C put on the clipboard. The payload is the same plist
# dialect as a .glyphs file, but its layout isn't documented, so the walk
# below is deliberately permissive.
# ----------------------------------------------------------------------
def pasteboard_plist():
	"""Returns (parsed_plist, type_it_came_from, all_types_present)."""
	pb = NSPasteboard.generalPasteboard()
	types = list(pb.types() or [])

	candidates = [t for t in GLYPHS_PASTEBOARD_TYPES if t in types]
	candidates += [t for t in types if t not in candidates and ("Glyphs" in t or "GeorgSeifert" in t)]

	for pb_type in candidates:
		data = pb.dataForType_(pb_type)
		if not data:
			continue
		plist, _fmt, _err = NSPropertyListSerialization.propertyListWithData_options_format_error_(
			data, NSPropertyListMutableContainers, None, None)
		if plist is not None:
			return plist, pb_type, types
	return None, None, types


def node_from_entry(entry):
	"""
	v3/v4 clipboard: {pos = (x, y); type = OFFCURVE;}
	.glyphs-file shorthand: (x, y, "ls") or the Glyphs 2 string "x y ls"
	"""
	smooth = False
	if is_mapping(entry):
		position = entry["pos"]
		x, y = position[0], position[1]
		node_type = entry["type"] if "type" in entry else "line"
		smooth = is_true(entry["smooth"]) if "smooth" in entry else False
	elif isinstance(entry, str):
		parts = entry.split(" ")
		x, y = parts[0], parts[1]
		node_type = parts[2] if len(parts) > 2 else "l"
	else:
		x, y = entry[0], entry[1]
		node_type = entry[2] if len(entry) > 2 else "l"

	key = str(node_type).strip().lower()

	node = GlyphsApp.GSNode()
	node.position = (float(x), float(y))
	node.type = NODE_TYPES.get(key, GlyphsApp.LINE)
	node.smooth = smooth or (key.endswith("s") and key != "s")
	return node


def paths_from_plist(plist):
	"""Every path in the clipboard payload, whatever nesting it uses."""
	shape_lists = []

	def collect(container):
		if is_mapping(container):
			for key in ("shapes", "paths"):
				if key in container:
					shape_lists.append(container[key])
			for key in container.keys():
				collect(container[key])
		elif is_sequence(container):
			for value in container:
				collect(value)

	collect(plist)

	paths = []
	for shapes in shape_lists:
		for shape in shapes or []:
			if not is_mapping(shape) or "nodes" not in shape:
				continue   # a component, not a path
			path = GlyphsApp.GSPath()
			for entry in shape["nodes"] or []:
				path.nodes.append(node_from_entry(entry))
			path.closed = is_true(shape["closed"]) if "closed" in shape else True
			paths.append(path)
	return paths


def target_glyphs(font):
	"""Font view selection, falling back to the glyphs open in an Edit tab."""
	selection = list(font.selection or [])
	if selection:
		return selection
	return [layer.parent for layer in (font.selectedLayers or [])]


# ----------------------------------------------------------------------
# A push button that turns orange under the pointer.
# ----------------------------------------------------------------------
class _RSZMagicPasteHoverButton(NSButton):
	"""
	NSButton has no hover state of its own, so this watches a tracking area
	and swaps the bezel colour — white title over the orange, since black
	would be hard to read.

	The class name must be unique across every installed plugin: ObjC has
	one flat class namespace per process, so two plugins registering the
	same name make the second one fail to load.
	"""

	def initWithFrame_(self, frame):
		self = objc.super(_RSZMagicPasteHoverButton, self).initWithFrame_(frame)
		if self is None:
			return None
		self._trackingArea = None
		self._plainTitle = ""
		return self

	def updateTrackingAreas(self):
		objc.super(_RSZMagicPasteHoverButton, self).updateTrackingAreas()
		try:
			if self._trackingArea is not None:
				self.removeTrackingArea_(self._trackingArea)
			self._trackingArea = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
				self.bounds(),
				NSTrackingMouseEnteredAndExited | NSTrackingActiveInActiveApp | NSTrackingInVisibleRect,
				self, None)
			self.addTrackingArea_(self._trackingArea)
		except Exception:
			import traceback
			print("magicPaste — tracking area:\n%s" % traceback.format_exc())

	@objc.python_method
	def titleColoured(self, colour):
		style = NSMutableParagraphStyle.alloc().init()
		style.setAlignment_(NSTextAlignmentCenter)
		return NSAttributedString.alloc().initWithString_attributes_(
			self._plainTitle, {
				NSForegroundColorAttributeName: colour,
				NSFontAttributeName: self.font(),
				NSParagraphStyleAttributeName: style,
			})

	def mouseEntered_(self, event):
		try:
			self.setBezelColor_(ACCENT)
			self.setAttributedTitle_(self.titleColoured(NSColor.whiteColor()))
		except Exception:
			import traceback
			print("magicPaste — hover in:\n%s" % traceback.format_exc())

	def mouseExited_(self, event):
		try:
			self.setBezelColor_(None)
			self.setAttributedTitle_(self.titleColoured(NSColor.labelColor()))
		except Exception:
			import traceback
			print("magicPaste — hover out:\n%s" % traceback.format_exc())


def hoverButton(groupView, frameFromTop, title, target, action):
	"""Place a hover button; frameFromTop is (x, y-from-top, width, height)."""
	x, yFromTop, w, h = frameFromTop
	viewHeight = groupView.frame().size.height
	y = yFromTop if groupView.isFlipped() else viewHeight - yFromTop - h

	button = _RSZMagicPasteHoverButton.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
	button._plainTitle = title
	button.setTitle_(title)
	button.setBezelStyle_(NSBezelStyleRounded)
	button.setControlSize_(NSControlSizeSmall)
	button.setFont_(NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()))
	button.setTarget_(target)
	button.setAction_(action)
	groupView.addSubview_(button)
	return button


# ----------------------------------------------------------------------
# Palette: the two paste buttons.
# ----------------------------------------------------------------------
class magicPastePalette(PalettePlugin):

	@objc.python_method
	def settings(self):
		self.name = "magicPaste"

		width, height = 160, 30
		self.paletteView = Window((width, height))
		self.paletteView.group = Group((0, 0, width, height))
		groupView = self.paletteView.group.getNSView()
		groupView.setAutoresizingMask_(NSViewWidthSizable)

		# side by side, with a gap wide enough that the rounded bezels don't
		# read as one segmented control
		try:
			hoverButton(groupView, (8, 4, 86, 20), "This Layer", self, "pasteThisLayer:")
			allLayers = hoverButton(groupView, (106, 4, width - 114, 20),
				"All Layers", self, "pasteAllLayers:")
			allLayers.setAutoresizingMask_(NSViewWidthSizable)
		except Exception:
			# fall back to plain vanilla buttons rather than an empty palette
			import traceback
			print("magicPaste — could not build hover buttons:\n%s" % traceback.format_exc())
			self.paletteView.group.thisLayer = Button((8, 4, 86, 20), "This Layer",
				callback=self.pasteThisLayer, sizeStyle="small")
			self.paletteView.group.allLayers = Button((106, 4, -8, 20), "All Layers",
				callback=self.pasteAllLayers, sizeStyle="small")

		self.dialog = groupView

	@objc.python_method
	def paste(self, allLayers):
		font = Glyphs.font
		if font is None:
			return

		glyphs = target_glyphs(font)
		if not glyphs:
			Glyphs.showNotification("magicPaste", "Select the glyphs to paste into first.")
			return

		plist, pb_type, types = pasteboard_plist()
		if plist is None:
			print("magicPaste — nothing from Glyphs on the clipboard. Types found: %r" % (types,))
			Glyphs.showNotification("magicPaste", "Copy a shape with ⌘C first.")
			return

		paths = paths_from_plist(plist)
		if not paths:
			print("magicPaste — read clipboard type %r but found no paths. Parsed payload:" % pb_type)
			print(plist)
			Glyphs.showNotification("magicPaste", "No paths found on the clipboard — see the Macro Panel.")
			return

		master_id = font.selectedFontMaster.id
		pasted = 0
		font.disableUpdateInterface()
		try:
			for glyph in glyphs:
				layers = list(glyph.layers) if allLayers else [glyph.layers[master_id]]
				glyph.beginUndo()
				for layer in layers:
					if layer is None:
						continue
					for path in paths:
						layer.shapes.append(path.copy())
					pasted += 1
				glyph.endUndo()
		finally:
			font.enableUpdateInterface()

		Glyphs.showNotification("magicPaste", "Pasted %d path%s into %d layer%s." % (
			len(paths), "" if len(paths) == 1 else "s",
			pasted, "" if pasted == 1 else "s"))

	# ObjC entry points for the hand-made buttons. Anything escaping from here
	# would reach PyObjC and take Glyphs down, so both are wrapped.
	def pasteThisLayer_(self, sender):
		try:
			self.paste(False)
		except Exception:
			import traceback
			print("magicPaste — this layer:\n%s" % traceback.format_exc())

	def pasteAllLayers_(self, sender):
		try:
			self.paste(True)
		except Exception:
			import traceback
			print("magicPaste — all layers:\n%s" % traceback.format_exc())

	@objc.python_method
	def pasteThisLayer(self, sender):
		self.paste(False)

	@objc.python_method
	def pasteAllLayers(self, sender):
		self.paste(True)

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
