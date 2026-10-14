# 🎥 Kinomat

**Version 0.62** — for Glyphs 3 and 4, macOS 10.15 or later.

By Giuseppe Salerno co-founder of [Resistenza Type](https://rsztype.com).

This is a plugin for the [Glyphs font editor](https://glyphsapp.com/). It films the font you are drawing: a word, moving along its own variable axes, and out the other side an MP4, a GIF or a sequence of PNGs. No timeline, no keyframes — each axis gets a lane with a **from** and a **to**, and the word travels between them.

A font with no axes is not turned away. It is filmed as the static font of the master in front, and the lanes become the two things such a font can still do: its size and its tracking.

<img src="Kinomat.png" alt="The Kinomat panel: the settings on the left with the FONT Export row, the word on the stage, and one lane per axis underneath." title="Kinomat screenshot" width="720">

### Installation

1. Unzip the download and double-click `Kinomat.glyphsPlugin` — Glyphs will offer to install it. (Alternatively, drop it into `~/Library/Application Support/Glyphs 3/Plugins/` or `~/Library/Application Support/Glyphs 4/Plugins/`.)

2. Restart Glyphs.app.

`Kinomat.glyphsTool` is optional and installs the same way: it puts Kinomat's icon in the toolbar, and opens the same panel. Nothing else.

### Usage Instructions

1. Open a font and choose *Window ▸ Kinomat*, or press ⌘K.
2. Type a word in the box — it opens on the font's own name.
3. Set each lane's **from** and **to**, the ones left ticked are the ones that move.
4. Set the canvas, the paper and the ink, how long the film runs and how fast.
5. **Export MP4**, **GIF** or **PNG sequence**.

The panel opens running, so the word is already moving while you set the rest.

### Which export is filmed

A document can hold more than one variable setting — a Roman and a Stencil, each cancelling the other's masters, or a Serif and a Sans built over the same masters. They are different fonts, with axes of their own, and the panel cannot guess which one you mean. So it asks: a row **FONT ▸ Export** appears in the settings, naming each setting, with the family in front of it where the settings do not all make the same one.

With a single variable setting, or none, there is nothing to choose and the row is not there.

Changing it re-reads the font and rebuilds the lanes around the new axes. Everything else you set is carried across, and a lane whose axis the new setting does not have is left behind, named in the status line.

With no variable setting at all, Kinomat films a variable font made up on the spot — every master, nothing switched off. It comes out right, but it is not the font the document would export, and the panel says so where the chooser would be. Add a Variable Instance in *Font Info ▸ Exports* and that one is filmed instead.

### What the font it films is

Kinomat does not draw from the masters: it exports the font, as Font Info would, and films that — filters, custom parameters and features included. So the film shows the font as it goes out, not the drawing. To keep the wait short, only the glyphs the word needs are exported; type a letter that was not in it and the missing ones are added, once the typing stops.

### Requirements

The plugin requires Glyphs 3 or Glyphs 4, running on macOS 10.15 or later. MP4 and GIF are written by the system's own encoders, so nothing else has to be installed.

### License

Copyright 2026 Giuseppe Salerno / Resistenza Type [rsztype.com](https://rsztype.com).

You may use, modify, and distribute this plugin freely. It is provided as-is, without warranty of any kind.
