# Alte DIN 1451 numerals — hand trace

`alte_din_trace.svg` is a single-stroke, hand-made tracing of the Alte DIN
1451 Mittelschrift numerals: one `<path>` per digit, stroked centreline, all
glyphs sharing the same cap line (28.801 units) and baseline.
`alte_din_trace.af` is the Affinity Designer source.

`cad/stroke_din.json` is generated from that SVG by
`cad/tools/derive_stroke.py`; it is the data `cad/vecfont.py` engraves with.

## Provenance and licence

- The letterforms are Ludwig Goller's DIN 1451 Mittelschrift (1936). The
  design is public domain: German design rights have expired and US law does
  not protect typeface designs.
- The SVG is this project's own tracing, not a conversion of a font file, so
  the derived data can be published with the repository under whatever
  licence the repository uses. Crediting the 1936 design is courteous, not
  required.
- Spacing is measured, not assumed: the renderer places each glyph by its
  drawn ink box (channel included, and including how far a slanted stroke
  reaches past its ends) and leaves a fixed `GAP` of 0.11 cap between one
  glyph's ink and the next: 0.15 cap, but never less than 0.43 mm, so a
  slicer always resolves the gap.
- Kerning is per glyph side, in `stroke_din.json` as
  `{"1": {"before": -40, "after": 25}, "7": {"after": -20}}`: a pair gets
  `prev.after + next.before` on top of `GAP`. The `1`'s flag tapers away to
  the left, and the `7`'s diagonal leaves the lower right empty, so both read
  wider than they are. Add or tune entries in `KERN` in `derive_stroke.py`.
- **Do not name a published font "DIN 1451" or anything starting with "DIN"**:
  "DIN" is a registered trademark of DIN e.V. A description such as
  "technical lettering after DIN 1451" is fine.

## Shape notes

- The `7` carries DIN's short downward terminal at the left end of the top
  bar; the `4` is two strokes (diagonal + crossbar, and the stem).
- The period is not traced. `derive_stroke.py` synthesises it as the single
  dot at advance/2, 0.075 cap above the baseline.

## Regenerating

```sh
python cad/tools/derive_stroke.py            # write cad/stroke_din.json
python cad/tools/derive_stroke.py --check    # fail if the JSON is stale
```

No extra dependencies: the script uses only the standard library.
