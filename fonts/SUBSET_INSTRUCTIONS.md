# Embedding the font (fixes the Windows/Consolas 7% narrower issue)

External font URLs don't work here — these SVGs load through an `img` tag,
and browsers refuse subresource fetches for image documents. A `@font-face`
with a base64 data URI does work.

**Use JetBrains Mono** — SIL OFL licensed, and its metrics are 600/1000
units, exactly the 0.600em the portrait grid assumes, so embedding it
changes nothing about the layout math already baked into the scripts.

## 1. Download JetBrains Mono
Get `JetBrainsMono-Regular.ttf` from https://github.com/JetBrains/JetBrainsMono
(SIL Open Font License — ship the `OFL.txt` license file alongside it in
this repo, since the font file lands in a public repo).

## 2. Subset it — only the characters actually used

```bash
pip install fonttools brotli

# Just the 13 ramp characters, for the portrait:
pyftsubset JetBrainsMono-Regular.ttf --text=' .`:-=+*cs#%@' \
  --flavor=woff2 --layout-features='' --no-hinting -o fonts/ramp.woff2

# Basic latin (for section headings / data graphics text) — adjust
# --text or --unicodes to only what you actually use, to keep it small:
pyftsubset JetBrainsMono-Regular.ttf \
  --unicodes="U+0020-007E" \
  --flavor=woff2 --layout-features='' --no-hinting -o fonts/basic-latin.woff2
```

Expect roughly:
| Subset | Covers | Size |
|---|---|---|
| ramp | 13 characters | ~1.3 KB |
| basic latin | printable ASCII | ~4.5 KB |

**Do not** embed the full, unsubsetted TTF — that's ~4.5 MB per file if
inlined naively. Subset per role and the whole page stays under ~60 KB.

## 3. Use it
Pass `--font fonts/ramp.woff2` to `scripts/generate_portrait.py` — it
base64-encodes the file and inlines a `@font-face` block into the SVG.
Every SVG that needs the font carries its own copy (that's the ~57 KB
total across the page mentioned in the guide) since each SVG loads as
an independent image document with no shared cache between them.

## Licence
Ship `OFL.txt` next to the subsetted files in this `fonts/` folder.
Commercial fonts are not an option here — the file is public.
