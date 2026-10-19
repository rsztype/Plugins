# 🎥 Kinomat

**Version 0.77** — for Glyphs 3 and 4, macOS 10.15 or later.

By Giuseppe Salerno co-founder of [Resistenza Type](https://rsztype.com).

A plugin for the [Glyphs font editor](https://glyphsapp.com/) that films the font you are drawing: a word travelling along its own variable axes, over a colour or over a photograph, out as MP4, GIF or a PNG sequence. No timeline and no keyframes — each axis gets a lane, with a **from** and a **to**.

**Exporting the film needs the Pro version.** Everything else is the demo, and the demo is the whole panel. One payment, no subscription: **[get the key — €19](https://buy.stripe.com/5kQ5kD5SX38m19New9eQM05)**. The same key opens the tools at [resistenza.es/tools](https://resistenza.es/tools/).

<img src="Kinomat.png" alt="The Kinomat panel: the settings on the left with the FONT Export row, the word on the stage, and one lane per axis underneath." title="Kinomat screenshot" width="720">

### Final result

<img src="Kinomat.gif" alt="A capital R in Industria Serif, widening and growing heavier over an orange photograph, back and forth." title="Kinomat — final result" width="320">

[The MP4 it was written as](Kinomat.mp4) — 1080 × 1920, 30 fps.

### Installation

Unzip and double-click `Kinomat.glyphsPlugin`, or drop it into `~/Library/Application Support/Glyphs 4/Plugins/`. Restart Glyphs, then *Window ▸ Kinomat*, or ⌘K.

The Pro key goes in the top right of the panel, beside the name of the font: the button says *Insert Key* until it carries one.

### The panel

The panel opens as you left it: every setting below is kept when the window closes, or when Glyphs quits with it open, and comes back the next time. Lanes return by axis tag, so a font with other axes keeps its own; media behind the word returns with the Pro key.

**PROJECT** — `Save…` and `Open…` write and read a `.rsztools` project: every setting below, the font excluded, since a project takes the font of the Glyphs file that is open. *Pro.*

**FONT** — `Export` picks which of the document's variable exports is filmed, naming each one, with the family in front where they do not all make the same one. The row appears only when there is more than one to choose. Changing it rebuilds the lanes around the new axes and carries the rest of the panel across.

A document with axes films its **variable font export** from *Font Info ▸ Exports*. Without one, the panel opens on the static font of the master in front, with Size and Tracking for lanes, and the panel says so in orange beside the lanes. A variable export that fails — glyphs not compatible across masters — opens the same way, naming the glyphs.

**TEXT**

| | |
|---|---|
| the box | what is filmed, one line per line. It opens on the font's own name |
| `Size` | in points, on the canvas — with **Fit width** it is set for you, as wide as the canvas allows |
| `Leading` | the distance between lines, as a percentage |
| `Cycle` | instead of the word, the font's glyphs one after another, components included |
| `Tracking` | letter-spacing, per thousand of the em, on top of the font's own kerning |
| `Align` | left, centre, right |
| `Ligatures` | **liga** standard ones, clig with them · **dlig** the discretionary ones. Measured as they are drawn |

**CANVAS**

| | |
|---|---|
| `Preset` | Reel / Story 9:16 · Post 1:1 · Post 4:5 · Post 5:4 · Landscape 16:9 · Square 2000 · Custom |
| `Size` | width × height in pixels, if none of those fits |
| `Stage`, `Ink` | the two colours, by picker or by hex. The **⇄** between them is the film in negative |

**BACKGROUND**

| | |
|---|---|
| `Media` | an image or a video behind the word — png, jpg, heic, tif, gif, bmp, webp · mov, mp4, m4v. **✕** takes it away. *Pro* |
| `Real time` | a video behind sets the film's length and speed; switched off, Duration and fps are yours again |
| `Zoom`, `Rotate`, `Speed` | how large the media is drawn, which way round, and how fast a video runs |
| `Colorize` | the media in two colours of your choosing — one for its darks, one for its lights — with its own **⇄** |
| `Bright`, `Contrast` | over the media only: the word is never touched |

**MOTION**

| | |
|---|---|
| `Duration` | seconds, and `fps` frames a second |
| `Easing` | Linear · Ease In · Ease Out · Ease In-Out · Sine In-Out · Expo In-Out · Back In-Out · Elastic Out · Bounce Out |
| `Loop` | **Ping-pong** out and back · **Restart** out and from the start again · **Play once** |
| `Animate` | **Whole** the text as one · **Words** · **Letters**, each piece a step behind the one before. A single word has nothing to divide, and the panel says so |
| `Repeat` | how many times the loop runs in the exported file |

**THE LANES** — one per axis, then **Size** and **Tracking**, always. With axes those two start switched off; with none they are the whole film.

| | |
|---|---|
| the tick beside the name | this axis moves. Unticked, it stands still on its **from** |
| `from → to` | where the axis starts and ends. The diamonds on the track do the same by hand |
| the number in orange | where the axis is, right now, in the frame on the stage |
| `Alternate` | the lanes one after another, each adding to the ones before |
| `Random` | every lane starts from its own point of the loop, drawn when it was ticked |
| `Sliders` | draws the lanes in the film itself. With it on, each lane gets a **Hide** box to leave its own slider out |

**THE BAR** — `Export MP4`, `GIF`, `PNG sequence`. *Pro.*

Beside them, how large the film comes out — **1×** the canvas, 1.5×, 2× — and the codec: **H.264**, which plays everywhere, or **HEVC**, a finer edge on coloured letters and a film that plays on Apple's machines and nowhere else. The status line says what was written, how large, and in which of the two.

### What is filmed

Not the masters: Kinomat exports the font, as Font Info would, filters and parameters and features included, and films that. So the film shows the font as it goes out, not the drawing. Only the glyphs the text needs are exported, which is quick; type a letter that was not in it and the missing ones are added once the typing stops.

### Requirements

Glyphs 3 or Glyphs 4, macOS 10.15 or later. MP4 and GIF are written by the system's own encoders, so nothing else has to be installed.

### License

Copyright 2026 Giuseppe Salerno / Resistenza Type [rsztype.com](https://rsztype.com).

You may use, modify, and distribute this plugin freely. It is provided as-is, without warranty of any kind.
