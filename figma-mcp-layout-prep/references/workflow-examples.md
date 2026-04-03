# Workflow Examples

## Page Flow

Use this flow for `audit-page`, `rename-page`, or page-scoped `prepare-for-mcp`:

1. Call `mcp__figma__get_metadata` on the page link.
2. Save the XML to a temp file.
3. Run:

```bash
python3 scripts/analyze_figma_metadata.py /tmp/page.xml --mode audit-page --output /tmp/page-audit.json
```

4. Review `rename_candidates`, `autolayout_candidates`, and `manual_review`.
5. If the page is safe to edit, render the scaffold:

```bash
python3 scripts/generate_use_figma_prompt.py /tmp/page-audit.json --mode prepare-for-mcp --format markdown
```

6. Apply only the confident updates with `mcp__figma__use_figma`.
7. Re-check screenshot and structure.
8. If a marketing card includes a decorative illustration cluster that should be flattened, export the full decorative region at `4x` PNG and place it back at the original visual size instead of rasterizing only one character or icon inside that region.

## Frame Flow

Use this flow for `audit-frame`, `autolayout-frame`, or frame-scoped `prepare-for-mcp`:

1. Call `mcp__figma__get_metadata` on the exact frame link.
2. Save the response to `/tmp/frame.xml`.
3. Run:

```bash
python3 scripts/analyze_figma_metadata.py /tmp/frame.xml --mode audit-frame --output /tmp/frame-audit.json
```

4. Use the report to isolate only the target subtree.
5. Generate the write scaffold:

```bash
python3 scripts/generate_use_figma_prompt.py /tmp/frame-audit.json --mode autolayout-frame --format js
```

6. Apply the generated JavaScript with `mcp__figma__use_figma`.
7. For decorative rasterization, keep `text/*`, `button/*`, and simple `icon/*` layers editable and flatten only the full decorative region at `4x` PNG.

## Handoff Expectations

The prepared page or frame should satisfy these goals:

- default Figma names are largely removed
- main content containers are readable, semantic, and consistent
- obvious linear groups use Auto Layout
- complex or freeform areas are explicitly called out for manual handling
- developers can hand the cleaned link to Figma MCP and recover a clearer structural skeleton for React or Next.js implementation
- decorative raster assets stay visually sharp because they are exported at a higher source scale and displayed at the original frame size
