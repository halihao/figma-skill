# figma-skill

This repository contains the current `figma-mcp-layout-prep` skill package used to prepare Figma designs for cleaner MCP and AI handoff.

## What It Does

- audits a page or a single frame
- suggests semantic layer names
- suggests safe Auto Layout candidates
- scores decorative regions for:
  - `full_raster_candidate`
  - `shell_raster_candidate`
  - `partial_raster_candidate`
  - `keep_structured`
- supports the marketing-card override for promo tiles that are better shipped as full-card PNG assets

## Repository Layout

- `figma-mcp-layout-prep/SKILL.md`
  The main skill entry and workflow guide.
- `figma-mcp-layout-prep/scripts/analyze_figma_metadata.py`
  The metadata audit and scoring engine.
- `figma-mcp-layout-prep/scripts/generate_use_figma_prompt.py`
  Generates conservative `use_figma` scaffolds from audit output.
- `figma-mcp-layout-prep/references/`
  Naming, Auto Layout, rasterization, and workflow rules.

## Current Status

This repository currently packages the skill as a Codex skill bundle.

It is not yet a standalone Figma plugin package.

## Typical Workflow

1. Run the skill against a Figma page or frame.
2. Review rename and rasterization candidates.
3. Apply low-risk structure cleanup.
4. Keep semantic layers for maintainable UI.
5. Rasterize complex decorative regions or full marketing cards when appropriate.

## Notes

- This repo intentionally keeps the rule system and audit scripts together.
- Temporary audit outputs are not committed.
- If we want broader team adoption later, the next natural step is adding a Figma plugin wrapper on top of this skill package.
