---
name: figma-mcp-layout-prep
description: Prepare Figma pages or frames for MCP-friendly implementation by auditing layer names, suggesting semantic renames, identifying safe Auto Layout opportunities, and generating conservative `use_figma` execution scaffolds. Use when Codex receives a Figma page/frame link and needs to clean up handoff structure before developers consume the design through Figma MCP, especially for admin dashboards, forms, content pages, modal flows, and other rule-based interfaces.
---

# Figma MCP Layout Prep

## Overview

Use this skill to turn a designer-facing Figma tree into a developer-facing structure that is easier for Figma MCP to consume. Favor conservative, auditable edits over aggressive “auto-fix everything” behavior.

## Modes

Support these five user-facing modes:

- `audit-page`: inspect an entire page, report naming issues, missing Auto Layout opportunities, and manual-review zones
- `audit-frame`: inspect one frame subtree without touching sibling frames
- `rename-page`: rename page descendants using the naming system in `references/naming-rules.md`
- `autolayout-frame`: add Auto Layout only inside one target frame subtree
- `prepare-for-mcp`: run audit, safe rename suggestions, safe Auto Layout suggestions, and a post-change verification checklist

Infer scope from the link:

- If the link points to a page, process all top-level frames on that page
- If the link points to a specific frame, process only that frame subtree

## Workflow

Follow this order every time:

1. Fetch structure with `mcp__figma__get_metadata`.
2. Fetch a screenshot with `mcp__figma__get_screenshot` when the structure is visually ambiguous or before any write operation.
3. Save the metadata response to a temporary XML or JSON file.
4. Run `scripts/analyze_figma_metadata.py` to produce an audit report.
5. Read `references/naming-rules.md` and `references/autolayout-rules.md` if the report contains uncertain or borderline suggestions.
6. Run `scripts/generate_use_figma_prompt.py` on the audit report to generate a conservative `use_figma` scaffold.
7. Review the scaffold before writing. Skip or comment out low-confidence changes instead of forcing them through.
8. Apply writes with `mcp__figma__use_figma`.
9. Re-fetch screenshot or metadata to confirm the edited structure is cleaner and still visually correct.
10. If the next step is code generation, hand the cleaned node link to the Figma MCP design-to-code flow.

When a card or module contains a complex decorative cluster that should be flattened into an image asset, export that cluster at `4x` PNG and place it back at the original display size. If descendants visibly overflow the group bounds, export using their visual union bounds instead of the raw node box. Keep editable text, CTA, and simple icons outside the flattened asset whenever possible.

Exception for marketing promo cards:

- if a small homepage card is illustration-heavy
- uses art text or a treated lockup
- contains only static promo copy
- and its CTA is decorative rather than a reusable semantic control

then prefer full-card rasterization. In real product handoff these cards are often implemented as one image-backed entry tile with a single click target rather than reconstructed as reusable UI sublayers.

## Safety Rules

- Preserve instances and component names unless the existing name is clearly useless.
- Do not rename nodes outside the requested page or frame subtree.
- Do not auto-convert obviously freeform marketing layouts into Auto Layout.
- Do not force Auto Layout onto overlapping stacks, rotated art, masks, or irregular grids.
- Keep overlays absolute-positioned when the report marks them as overlay candidates.
- Prefer leaving a node in the report with a manual-review reason over making a low-confidence mutation.
- Do not flatten live text, CTA buttons, or simple icons into a raster asset unless the user explicitly wants a non-editable marketing image.
- When you flatten a decorative subtree, prefer a whole decorative region over a partial character-only crop so the visual composition stays intact.
- For static marketing entry cards, allow a decorative CTA to be flattened with the whole card when the audit marks it as a marketing-card override.

## Script Usage

Run the analyzer on the saved metadata file:

```bash
python3 scripts/analyze_figma_metadata.py /tmp/figma-page.xml \
  --mode prepare-for-mcp \
  --figma-url "https://www.figma.com/design/FILE/NAME?node-id=1-2" \
  --output /tmp/figma-audit.json
```

Render a `use_figma` scaffold from the audit:

```bash
python3 scripts/generate_use_figma_prompt.py /tmp/figma-audit.json \
  --mode prepare-for-mcp \
  --format markdown
```

Use `--format js` when you want only the executable JavaScript scaffold.

## Interpreting the Audit

Treat the audit output as a decision aid, not a blind patch:

- `rename_candidates`: safe or reviewable semantic names
- `autolayout_candidates`: direct frame updates that can usually be applied
- `group_conversion_candidates`: groups that look convertible but need extra care
- `rasterization_candidates`: scored card-level recommendations for `full_raster_candidate`, `shell_raster_candidate`, or `partial_raster_candidate`, including marketing-card overrides
- `manual_review`: nodes that should stay untouched until a human confirms intent

Prioritize high-confidence rename and Auto Layout suggestions first. Save group conversion and ambiguous text-role decisions for a second pass.

## References

- `references/naming-rules.md`: semantic naming system and default-name cleanup rules
- `references/autolayout-rules.md`: safe Auto Layout heuristics, blocklist patterns, and application defaults
- `references/rasterization-rules.md`: when and how to flatten decorative regions into sharp raster assets
- `references/workflow-examples.md`: page-mode and frame-mode usage examples plus handoff expectations
