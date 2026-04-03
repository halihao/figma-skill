# Decorative Rasterization Rules

Use rasterization only for decorative regions that add visual polish but do not need to remain editable in code.

## Default Export Rule

- export decorative regions as `PNG`
- use `4x` scale for small card illustrations and badge-like visuals
- use `3x` scale for larger decorative panels when file size becomes a concern
- place the exported image back at the original display size

This keeps the rendered asset sharper than a `1x` or `2x` export without changing the layout geometry.
When the decorative group contains text or shapes that visually overflow its nominal width or height, export against the descendants' visual union bounds instead of the group's raw node bounds.

## Card-Level Scoring

When deciding between full-card rasterization and partial rasterization, score the container instead of relying on one hard rule.

Suggested score bands:

- `>= 65`: `full_raster_candidate`
- `marketing override`: `full_raster_candidate` even with a decorative CTA
- `shell-heavy with preserved content`: `shell_raster_candidate`
- `40-64`: `partial_raster_candidate`
- `< 40`: `keep_structured`

Add a separate `marketing_card_score` for promo-entry tiles. This catches cards that developers would normally export as one PNG even though they contain a small CTA-like arrow or button.

Suggested positive signals for `marketing_card_score`:

- small homepage promo tile or entry card
- strong art-text title
- mascot/IP or illustration-heavy composition
- static promo subtitle or slogan
- decorative CTA that is visually part of the card
- no dynamic counts, prices, scores, or other business data
- no stateful control like switch, tab set, input, or toggle

If `marketing_card_score >= 24`, `art_text_strength >= 10`, `illustration_strength >= 8`, and the CTA is decorative rather than semantic, classify the whole card as `full_raster_candidate`.

Use `shell_raster_candidate` when the container itself is mostly a decorative shell:

- large masked or gradient background
- textured/patterned card chrome
- complex decorative multi-layer shell
- but meaningful text, lists, CTA, QR, or other semantic content should stay outside the rasterized shell

In that case, flatten the shell/background region as one image and keep the foreground structure editable.

### Positive Signals

- visual complexity: masks, booleans, dense vectors, freeform overlap
- art-text strength: layered text clones, oversized display text, prominent display text, promo text badges
- illustration strength: large decorative cluster, mascot/IP-like region, shape-heavy illustration subtree

For standalone art text such as campaign slogans, hand-drawn titles, or visually treated promotional headlines, bias toward rasterization more aggressively than normal text. In mobile apps these are often not safe to ship as live text because the exact font or text effect is not guaranteed to exist in code.

Important limitation:

- metadata-only audit does not know the actual font family
- so the algorithm cannot reliably exempt PingFang or other system fonts at this stage
- if you want a font-aware exception pass, add an optional Figma read step that inspects the real font family before writing

### Negative Signals

- editable semantic text that should stay live
- explicit CTA or interaction entry
- dynamic labels, counts, or status-bearing layers

Important nuance:

- `semantic_cta`: a true reusable button, stateful control, or independently maintained action should still block full-card rasterization
- `decorative_cta`: a small arrow or promo button that is visually fused into a marketing card should not block full-card rasterization by itself

The algorithm should emit both a score and a reason list so design and engineering can review why the card was classified that way.

## Flatten Good Candidates

Flatten a whole decorative region when it contains several of these traits:

- masks or clipped illustrations
- dense vector clusters
- boolean operations
- pattern overlays or textures
- art-directed compositions that developers do not need to reproduce node-by-node

## Do Not Flatten

Keep these layers editable whenever possible:

- `text/*`
- `button/*`
- simple `icon/*`
- semantic counters, badges, or labels that may need localization or dynamic data

Even when a card scores high enough for full rasterization, downgrade it to partial rasterization if it contains a true CTA or clearly dynamic business content.
If the container is mostly shell graphics but its meaningful content is layered outside that shell, prefer `shell_raster_candidate` instead of `full_raster_candidate`.

For static marketing cards, do the opposite:

- if the title is art text
- the illustration is decorative
- the CTA is decorative
- and the copy is not expected to change in code

then prefer `full_raster_candidate` because developers will usually ship the whole card as one image-backed entry tile.

## Boundary Rule

Flatten the full decorative region, not just one mascot or one ornament inside it.

Good:

- mascot + local pattern + decorative badge together

Bad:

- mascot rasterized alone while its paired texture or mask remains outside
- export cropped to the group's nominal box even though descendant pixels visibly overflow beyond it

The bad version usually changes the visual balance and makes the resulting card look “off” even if the hierarchy is cleaner.

## Verification Checklist

After flattening a decorative region:

1. Compare the single-card screenshot against the original.
2. Compare the full-screen screenshot to confirm the card still reads correctly in context.
3. Check that no title, subtitle, or CTA moved outside the card.
4. Check that the asset is not visibly soft at normal zoom.
