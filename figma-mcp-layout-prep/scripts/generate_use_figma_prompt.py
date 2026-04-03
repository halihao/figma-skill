#!/usr/bin/env python3
"""Render a conservative use_figma scaffold from an audit report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def render_js(report: dict[str, Any], mode: str) -> str:
    allow_rename = mode in {"rename-page", "prepare-for-mcp"}
    allow_layout = mode in {"autolayout-frame", "prepare-for-mcp"}

    rename_ops = [
        {
            "id": item["id"],
            "currentName": item["current_name"],
            "suggestedName": item["suggested_name"],
            "confidence": item["confidence"],
        }
        for item in report.get("rename_candidates", [])
        if allow_rename and item.get("confidence", 0) >= 0.6
    ]
    layout_ops = [
        {
            "id": item["id"],
            "layoutMode": item["layoutMode"],
            "itemSpacing": item["itemSpacing"],
            "padding": item["padding"],
            "counterAxisAlignItems": item["counterAxisAlignItems"],
            "primaryAxisSizingMode": item["primaryAxisSizingMode"],
            "counterAxisSizingMode": item["counterAxisSizingMode"],
            "children": item["children"],
            "confidence": item["confidence"],
        }
        for item in report.get("autolayout_candidates", [])
        if allow_layout and item.get("can_apply_directly") and item.get("confidence", 0) >= 0.68
    ]
    group_candidates = report.get("group_conversion_candidates", [])
    rasterization_candidates = [
        item
        for item in report.get("rasterization_candidates", [])
        if item.get("decision") != "keep_structured"
    ]

    return f"""const renameOps = {json.dumps(rename_ops, ensure_ascii=False, indent=2)};
const layoutOps = {json.dumps(layout_ops, ensure_ascii=False, indent=2)};
const groupConversionCandidates = {json.dumps(group_candidates, ensure_ascii=False, indent=2)};
const rasterizationCandidates = {json.dumps(rasterization_candidates, ensure_ascii=False, indent=2)};

async function requireNode(id) {{
  const node = await figma.getNodeByIdAsync(id);
  if (!node) throw new Error(`Node not found: ${{id}}`);
  return node;
}}

function getAbsolutePosition(node) {{
  if (!("absoluteTransform" in node)) {{
    throw new Error(`Node does not expose absoluteTransform: ${{node.id}}`);
  }}
  return {{
    x: node.absoluteTransform[0][2],
    y: node.absoluteTransform[1][2],
  }};
}}

function unionBounds(a, b) {{
  if (!a) return b;
  if (!b) return a;
  return {{
    minX: Math.min(a.minX, b.minX),
    minY: Math.min(a.minY, b.minY),
    maxX: Math.max(a.maxX, b.maxX),
    maxY: Math.max(a.maxY, b.maxY),
  }};
}}

function getNodeBounds(node) {{
  if (!node.visible || !("width" in node) || !("height" in node) || !("absoluteTransform" in node)) {{
    return null;
  }}

  if ("absoluteRenderBounds" in node && node.absoluteRenderBounds) {{
    return {{
      minX: node.absoluteRenderBounds.x,
      minY: node.absoluteRenderBounds.y,
      maxX: node.absoluteRenderBounds.x + node.absoluteRenderBounds.width,
      maxY: node.absoluteRenderBounds.y + node.absoluteRenderBounds.height,
    }};
  }}

  const abs = getAbsolutePosition(node);
  return {{
    minX: abs.x,
    minY: abs.y,
    maxX: abs.x + node.width,
    maxY: abs.y + node.height,
  }};
}}

function getVisualBounds(node) {{
  let bounds = getNodeBounds(node);
  if ("findAll" in node) {{
    const descendants = node.findAll(child => child.visible && "width" in child && "height" in child);
    for (const child of descendants) {{
      bounds = unionBounds(bounds, getNodeBounds(child));
    }}
  }}
  if (!bounds) throw new Error(`Could not compute visual bounds: ${{node.id}}`);
  return bounds;
}}

function toParentCoordinates(parent, absoluteX, absoluteY) {{
  if (parent.type === "GROUP") {{
    return {{ x: absoluteX, y: absoluteY }};
  }}
  if ("absoluteTransform" in parent) {{
    const parentAbs = getAbsolutePosition(parent);
    return {{
      x: absoluteX - parentAbs.x,
      y: absoluteY - parentAbs.y,
    }};
  }}
  return {{ x: absoluteX, y: absoluteY }};
}}

async function flattenDecorativeGroupToImage(nodeId, outputName, scale = 4) {{
  const node = await requireNode(nodeId);
  if (!("exportAsync" in node) || !node.parent || !("insertChild" in node.parent)) {{
    throw new Error(`Node cannot be flattened safely: ${{nodeId}}`);
  }}

  const visualBounds = getVisualBounds(node);
  const nodeAbs = getAbsolutePosition(node);
  const parent = node.parent;
  const index = parent.children.findIndex(child => child.id === node.id);
  const tempFrame = figma.createFrame();
  tempFrame.name = `temp-export/${{outputName}}`;
  tempFrame.fills = [];
  tempFrame.strokes = [];
  tempFrame.clipsContent = false;
  tempFrame.resizeWithoutConstraints(
    visualBounds.maxX - visualBounds.minX,
    visualBounds.maxY - visualBounds.minY,
  );
  tempFrame.x = visualBounds.minX;
  tempFrame.y = visualBounds.minY;
  figma.currentPage.appendChild(tempFrame);

  const clone = node.clone();
  tempFrame.appendChild(clone);
  clone.x = nodeAbs.x - visualBounds.minX;
  clone.y = nodeAbs.y - visualBounds.minY;

  const exportBytes = await tempFrame.exportAsync({{
    format: "PNG",
    constraint: {{ type: "SCALE", value: scale }},
  }});
  tempFrame.remove();
  const image = figma.createImage(exportBytes);
  const imageNode = figma.createRectangle();
  imageNode.name = outputName;
  imageNode.resizeWithoutConstraints(
    visualBounds.maxX - visualBounds.minX,
    visualBounds.maxY - visualBounds.minY,
  );
  const local = toParentCoordinates(parent, visualBounds.minX, visualBounds.minY);
  imageNode.x = local.x;
  imageNode.y = local.y;
  imageNode.fills = [{{
    type: "IMAGE",
    imageHash: image.hash,
    scaleMode: "FILL",
  }}];
  imageNode.strokes = [];
  parent.insertChild(index, imageNode);
  node.remove();
  return imageNode;
}}

function isLayoutCapable(node) {{
  return "layoutMode" in node && "paddingLeft" in node;
}}

async function applyRenameOps() {{
  for (const op of renameOps) {{
    const node = await requireNode(op.id);
    if (node.name === op.currentName || /^(frame|group|rectangle|text|line|vector|ellipse|polygon|star|section|component|instance)\\s+\\d+$/i.test(node.name)) {{
      node.name = op.suggestedName;
    }}
  }}
}}

async function applyLayoutOps() {{
  for (const op of layoutOps) {{
    const node = await requireNode(op.id);
    if (!isLayoutCapable(node)) continue;
    node.layoutMode = op.layoutMode;
    node.primaryAxisSizingMode = op.primaryAxisSizingMode;
    node.counterAxisSizingMode = op.counterAxisSizingMode;
    node.primaryAxisAlignItems = "MIN";
    node.counterAxisAlignItems = op.counterAxisAlignItems;
    node.itemSpacing = op.itemSpacing;
    node.paddingLeft = op.padding.left;
    node.paddingRight = op.padding.right;
    node.paddingTop = op.padding.top;
    node.paddingBottom = op.padding.bottom;

    for (const childOp of op.children) {{
      const child = await requireNode(childOp.id);
      if ("layoutPositioning" in child && childOp.layoutPositioning) {{
        child.layoutPositioning = childOp.layoutPositioning;
        continue;
      }}
      if ("layoutAlign" in child && childOp.layoutAlign) {{
        child.layoutAlign = childOp.layoutAlign;
      }}
      if ("layoutGrow" in child && typeof childOp.layoutGrow === "number") {{
        child.layoutGrow = childOp.layoutGrow;
      }}
    }}
  }}
}}

async function main() {{
  await applyRenameOps();
  await applyLayoutOps();

  if (groupConversionCandidates.length) {{
    console.log("Group conversion candidates require manual review:", groupConversionCandidates);
  }}
  if (rasterizationCandidates.length) {{
    console.log("Rasterization candidates to review before writing:", rasterizationCandidates);
  }}

  console.log(
    "Tip: when flattening decorative groups into image assets, prefer flattenDecorativeGroupToImage(nodeId, name, 4) so the exported PNG stays sharp at the original display size."
  );

  figma.closePlugin(`Applied ${{renameOps.length}} rename ops and ${{layoutOps.length}} Auto Layout ops.`);
}}

await main();
"""


def render_markdown(report: dict[str, Any], mode: str) -> str:
    summary = report.get("summary", {})
    js = render_js(report, mode)
    manual = report.get("manual_review", [])
    group_candidates = report.get("group_conversion_candidates", [])
    rasterization_candidates = [
        item
        for item in report.get("rasterization_candidates", [])
        if item.get("decision") != "keep_structured"
    ]
    lines = [
        f"# {report.get('scope', {}).get('mode', mode)} scaffold",
        "",
        "## Summary",
        f"- Root: `{report.get('scope', {}).get('root_name', 'unknown')}` ({report.get('scope', {}).get('root_type', 'unknown')})",
        f"- Rename candidates: `{summary.get('rename_candidates', 0)}`",
        f"- Auto Layout candidates: `{summary.get('autolayout_candidates', 0)}`",
        f"- Group conversion candidates: `{summary.get('group_conversion_candidates', 0)}`",
        f"- Full raster candidates: `{summary.get('full_raster_candidates', 0)}`",
        f"- Shell raster candidates: `{summary.get('shell_raster_candidates', 0)}`",
        f"- Partial raster candidates: `{summary.get('partial_raster_candidates', 0)}`",
        f"- Manual review items: `{summary.get('manual_review', 0)}`",
        "",
        "## Suggested `use_figma` description",
        "Prepare the requested Figma subtree for MCP handoff by applying conservative semantic renames and safe Auto Layout updates only.",
        "",
        "## JavaScript scaffold",
        "```javascript",
        js.rstrip(),
        "```",
    ]
    if manual:
        lines.extend(["", "## Manual Review", ""])
        for item in manual[:10]:
            lines.append(f"- `{item['name']}` (`{item['id']}`): {item['reason']}")
    if group_candidates:
        lines.extend(["", "## Group Conversion Candidates", ""])
        for item in group_candidates[:10]:
            lines.append(f"- `{item['name']}` (`{item['id']}`): {item['reason']}")
    if rasterization_candidates:
        lines.extend(["", "## Rasterization Candidates", ""])
        for item in rasterization_candidates[:10]:
            reasons = ", ".join(item.get("reasons", [])[:4])
            lines.append(
                f"- `{item['name']}` (`{item['id']}`): `{item['decision']}` score `{item.get('score', 0)}`"
                + (f" — {reasons}" if reasons else "")
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_path", type=Path, help="Path to audit JSON")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["audit-page", "audit-frame", "rename-page", "autolayout-frame", "prepare-for-mcp"],
        help="Skill mode that controls which operations are rendered",
    )
    parser.add_argument(
        "--format",
        default="markdown",
        choices=["markdown", "js"],
        help="Output format",
    )
    args = parser.parse_args()

    report = load_report(args.report_path)
    if args.format == "js":
        print(render_js(report, args.mode))
    else:
        print(render_markdown(report, args.mode), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
