#!/usr/bin/env python3
"""Analyze Figma metadata and suggest safe naming and Auto Layout operations."""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_NAME_RE = re.compile(
    r"^(frame|group|rectangle|text|line|vector|ellipse|polygon|star|section|component|instance)\s+\d+$",
    re.IGNORECASE,
)
TEXT_TYPES = {"TEXT"}
CONTAINER_TYPES = {"FRAME", "GROUP", "SECTION", "COMPONENT", "INSTANCE"}
SHAPE_TYPES = {
    "RECTANGLE",
    "LINE",
    "VECTOR",
    "ELLIPSE",
    "POLYGON",
    "STAR",
    "BOOLEAN_OPERATION",
}
IMAGE_TYPES = {"IMAGE", "SLICE"}
SIZE_TOLERANCE = 6.0
ALIGNMENT_TOLERANCE = 12.0
BUTTON_LIKE_RE = re.compile(r"(?:^|[/_\-\s])(button|cta|action)(?:$|[/_\-\s])", re.IGNORECASE)
INTERACTIVE_LIKE_RE = re.compile(
    r"(?:^|[/_\-\s])(button|cta|action|input|switch|toggle|nav)(?:$|[/_\-\s])",
    re.IGNORECASE,
)
INTERACTIVE_CONTROL_RE = re.compile(
    r"(?:^|[/_\-\s])(input|switch|toggle|nav|tab|slider|picker|checkbox|radio)(?:$|[/_\-\s])",
    re.IGNORECASE,
)
SEMANTIC_DYNAMIC_RE = re.compile(
    r"(?:^|[/_\-\s])(status|count|value|label|badge|tag|price|score|metric)(?:$|[/_\-\s])",
    re.IGNORECASE,
)
MASK_LIKE_RE = re.compile(r"mask", re.IGNORECASE)
PROMO_TEXT_RE = re.compile(r"(模式|new|hot|pro|pk|vip)", re.IGNORECASE)
DISPLAY_TEXT_NAME_RE = re.compile(r"(title|headline|hero|promo|lockup|slogan)", re.IGNORECASE)
PROMO_PUNCT_RE = re.compile(r"[!！?？]")


@dataclass
class Node:
    id: str
    name: str
    type: str
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    children: list["Node"] = field(default_factory=list)
    parent_id: str | None = None

    @property
    def area(self) -> float:
        return max(self.width, 0.0) * max(self.height, 0.0)

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2.0

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2.0


def descendants(node: Node) -> list[Node]:
    items: list[Node] = []
    for child in node.children:
        items.append(child)
        items.extend(descendants(child))
    return items


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def slugify(value: str, fallback: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[/_]+", "-", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or fallback


def load_metadata(path: Path) -> Node:
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(f"{path} is empty")
    if raw[0] in "[{":
        payload = json.loads(raw)
        return parse_json_node(payload)
    root = ET.fromstring(raw)
    return parse_xml_node(root)


def parse_json_node(payload: Any, parent_id: str | None = None) -> Node:
    if isinstance(payload, dict) and "children" not in payload and len(payload) == 1:
        only_value = next(iter(payload.values()))
        if isinstance(only_value, dict):
            payload = only_value
    if not isinstance(payload, dict):
        raise ValueError("Expected JSON object for metadata input")

    node_id = str(payload.get("id") or payload.get("nodeId") or payload.get("key") or "root")
    node_type = str(payload.get("type") or payload.get("tag") or "FRAME").upper()
    node = Node(
        id=node_id,
        name=str(payload.get("name") or node_type.lower()),
        type=node_type,
        x=safe_float(payload.get("x")),
        y=safe_float(payload.get("y")),
        width=safe_float(payload.get("width")),
        height=safe_float(payload.get("height")),
        parent_id=parent_id,
    )
    for child in payload.get("children", []):
        node.children.append(parse_json_node(child, parent_id=node.id))
    return node


def parse_xml_node(element: ET.Element, parent_id: str | None = None) -> Node:
    node_type = str(element.attrib.get("type") or element.tag).upper()
    node_id = str(element.attrib.get("id") or element.attrib.get("nodeId") or element.tag)
    node = Node(
        id=node_id,
        name=str(element.attrib.get("name") or node_type.lower()),
        type=node_type,
        x=safe_float(element.attrib.get("x")),
        y=safe_float(element.attrib.get("y")),
        width=safe_float(element.attrib.get("width")),
        height=safe_float(element.attrib.get("height")),
        parent_id=parent_id,
    )
    for child in list(element):
        if isinstance(child.tag, str):
            node.children.append(parse_xml_node(child, parent_id=node.id))
    return node


def flatten(node: Node) -> list[Node]:
    nodes = [node]
    for child in node.children:
        nodes.extend(flatten(child))
    return nodes


def is_default_name(node: Node) -> bool:
    return bool(DEFAULT_NAME_RE.match(node.name.strip()))


def is_background(node: Node, parent: Node | None) -> bool:
    if parent is None or node.type not in SHAPE_TYPES:
        return False
    if not parent.children:
        return False
    first_child = parent.children[0].id == node.id
    width_close = abs(node.width - parent.width) <= SIZE_TOLERANCE
    height_close = abs(node.height - parent.height) <= SIZE_TOLERANCE
    return first_child and width_close and height_close


def is_divider(node: Node) -> bool:
    if node.type == "LINE":
        return True
    if node.type != "RECTANGLE":
        return False
    thin_side = min(node.width, node.height)
    long_side = max(node.width, node.height)
    return thin_side <= 2.0 and long_side >= 16.0


def is_icon_like(node: Node) -> bool:
    return node.type in SHAPE_TYPES and node.width <= 32.0 and node.height <= 32.0


def is_image_like(node: Node) -> bool:
    if node.type in IMAGE_TYPES:
        return True
    return node.type == "RECTANGLE" and node.width >= 48.0 and node.height >= 48.0


def name_has_pattern(node: Node, pattern: re.Pattern[str]) -> bool:
    return bool(pattern.search(node.name))


def overlapping_text_clone_count(nodes: list[Node]) -> int:
    text_nodes = [node for node in nodes if node.type in TEXT_TYPES]
    clones = 0
    for idx, node in enumerate(text_nodes):
        for other in text_nodes[idx + 1 :]:
            same_position = abs(node.x - other.x) <= 4.0 and abs(node.y - other.y) <= 4.0
            similar_dimensions = abs(node.width - other.width) <= 6.0 and abs(node.height - other.height) <= 6.0
            if same_position and similar_dimensions and max(node.height, other.height) >= 18.0:
                clones += 1
    return clones


def count_descendants_of_types(node: Node, types: set[str]) -> int:
    return sum(1 for item in descendants(node) if item.type in types)


def count_mask_like(node: Node) -> int:
    return sum(1 for item in descendants(node) if name_has_pattern(item, MASK_LIKE_RE))


def collect_keep_layers(node: Node) -> list[dict[str, str]]:
    keep: list[dict[str, str]] = []
    for child in node.children:
        if child.type in TEXT_TYPES:
            keep.append({"id": child.id, "name": child.name, "reason": "direct-text"})
            continue
        if child.type in CONTAINER_TYPES and name_has_pattern(child, INTERACTIVE_LIKE_RE):
            keep.append({"id": child.id, "name": child.name, "reason": "interactive-layer"})
            continue
        if child.type in {"INSTANCE", "COMPONENT"}:
            keep.append({"id": child.id, "name": child.name, "reason": "component-layer"})
    return keep


def collect_partial_flatten_layers(node: Node, keep_layer_ids: set[str]) -> list[dict[str, str]]:
    flatten_layers: list[dict[str, str]] = []
    parent_area = max(node.area, 1.0)
    for child in node.children:
        if child.id in keep_layer_ids:
            continue
        child_descendants = descendants(child)
        shape_count = sum(1 for item in child_descendants if item.type in SHAPE_TYPES)
        mask_count = count_mask_like(child)
        clone_count = overlapping_text_clone_count([child] + child_descendants)
        if child.type in CONTAINER_TYPES and (mask_count > 0 or shape_count >= 8 or clone_count > 0):
            flatten_layers.append({"id": child.id, "name": child.name, "reason": "decorative-subtree"})
            continue
        if child.type in SHAPE_TYPES and child.area >= parent_area * 0.12 and not is_background(child, node):
            flatten_layers.append({"id": child.id, "name": child.name, "reason": "large-decorative-shape"})
    return flatten_layers


def decorative_child_ratio(node: Node) -> float:
    if not node.children:
        return 0.0
    decorative = 0
    for child in node.children:
        if child.type in TEXT_TYPES:
            continue
        if child.type in {"INSTANCE", "COMPONENT"}:
            continue
        if child.type in CONTAINER_TYPES or child.type in SHAPE_TYPES or count_mask_like(child) > 0:
            decorative += 1
    return decorative / max(len(node.children), 1)


def build_rasterization_candidate(node: Node, parent: Node | None) -> dict[str, Any] | None:
    if node.type not in CONTAINER_TYPES:
        return None
    if parent is None:
        return None
    if name_has_pattern(node, MASK_LIKE_RE):
        return None
    if node.area < 12_000 or len(node.children) < 2:
        return None

    all_descendants = descendants(node)
    all_nodes = [node] + all_descendants
    direct_text_nodes = [child for child in node.children if child.type in TEXT_TYPES]
    all_text_nodes = [item for item in all_nodes if item.type in TEXT_TYPES]
    direct_visual_children = [
        child for child in node.children if child.type not in TEXT_TYPES and not is_background(child, node)
    ]

    mask_count = count_mask_like(node)
    boolean_count = sum(1 for item in all_descendants if item.type == "BOOLEAN_OPERATION")
    vector_count = sum(1 for item in all_descendants if item.type in {"VECTOR", "BOOLEAN_OPERATION", "LINE", "POLYGON", "STAR"})
    overlap_axis, overlap_reasons, _ = detect_orientation(node.children)
    overlapping_children = overlap_axis is None and "children-overlap" in overlap_reasons
    text_clone_count = overlapping_text_clone_count(all_text_nodes)
    prominent_text_count = sum(1 for item in all_text_nodes if item.height >= 24.0)
    oversized_text_count = sum(1 for item in all_text_nodes if item.height >= 40.0)
    promo_text_count = sum(1 for item in all_text_nodes if name_has_pattern(item, PROMO_TEXT_RE))
    emphatic_text_count = sum(1 for item in all_text_nodes if PROMO_PUNCT_RE.search(item.name))
    marketing_title_present = any(item.height >= 18 for item in direct_text_nodes)
    large_decorative_children = []
    for child in direct_visual_children:
        if child.area < node.area * 0.12:
            continue
        child_descendants = descendants(child)
        child_shape_count = count_descendants_of_types(child, SHAPE_TYPES)
        child_clone_count = overlapping_text_clone_count([child] + child_descendants)
        child_is_large_visual = (
            child.type in CONTAINER_TYPES
            or child_shape_count >= 8
            or count_mask_like(child) > 0
            or child_clone_count > 0
            or child.width >= node.width * 0.26
            or child.height >= node.height * 0.48
        )
        if child_is_large_visual:
            large_decorative_children.append(child)
    left_side_decoratives = [
        child for child in large_decorative_children if child.center_x <= (node.x + node.width * 0.58)
    ]

    visual_score = 0
    visual_reasons: list[str] = []
    if mask_count > 0:
        visual_score += 8
        visual_reasons.append("has-mask")
    if boolean_count > 0:
        visual_score += 8
        visual_reasons.append("has-boolean")
    if vector_count >= 80:
        visual_score += 8
        visual_reasons.append("very-dense-vectors")
    elif vector_count >= 30:
        visual_score += 6
        visual_reasons.append("dense-vectors")
    elif vector_count >= 10:
        visual_score += 3
        visual_reasons.append("some-vectors")
    if overlapping_children:
        visual_score += 5
        visual_reasons.append("freeform-overlap")
    visual_score = min(35, visual_score)

    art_text_score = 0
    art_text_reasons: list[str] = []
    if text_clone_count > 0:
        art_text_score += 10
        art_text_reasons.append("layered-art-text")
    if oversized_text_count >= 1:
        art_text_score += 10
        art_text_reasons.append("oversized-display-text")
    if prominent_text_count >= 1:
        art_text_score += 6
        art_text_reasons.append("prominent-display-text")
    if promo_text_count >= 1:
        art_text_score += 6
        art_text_reasons.append("promo-badge-text")
    if emphatic_text_count >= 1:
        art_text_score += 4
        art_text_reasons.append("exclamatory-promo-copy")
    art_text_score = min(20, art_text_score)

    ip_score = 0
    ip_reasons: list[str] = []
    if left_side_decoratives:
        ip_score += 8
        ip_reasons.append("left-side-decorative-cluster")
    if any(child.area >= node.area * 0.22 for child in large_decorative_children):
        ip_score += 6
        ip_reasons.append("large-illustration-region")
    if any(count_descendants_of_types(child, SHAPE_TYPES) >= 20 for child in large_decorative_children):
        ip_score += 6
        ip_reasons.append("shape-heavy-illustration")
    ip_score = min(20, ip_score)

    node_area = max(node.area, 1.0)
    keep_layers = collect_keep_layers(node)
    keep_layer_ids = {item["id"] for item in keep_layers}
    flatten_layers = collect_partial_flatten_layers(node, keep_layer_ids)
    button_like_layers = [item for item in all_descendants if name_has_pattern(item, BUTTON_LIKE_RE)]
    has_dynamic_semantics = any(name_has_pattern(item, SEMANTIC_DYNAMIC_RE) for item in all_descendants)
    has_control_like_subtree = any(
        item.type in CONTAINER_TYPES and name_has_pattern(item, INTERACTIVE_CONTROL_RE) for item in all_descendants
    )
    shell_score = 0
    shell_reasons: list[str] = []
    decorative_ratio = decorative_child_ratio(node)
    if mask_count > 0:
        shell_score += 10
        shell_reasons.append("shell-has-mask")
    if decorative_ratio >= 0.75:
        shell_score += 8
        shell_reasons.append("shell-mostly-decorative")
    elif decorative_ratio >= 0.5:
        shell_score += 5
        shell_reasons.append("shell-decorative-majority")
    if any(child.area >= node.area * 0.45 for child in large_decorative_children):
        shell_score += 8
        shell_reasons.append("shell-large-background-region")
    if len(flatten_layers) == 1 and flatten_layers[0]["id"] in {node.id, *(child.id for child in node.children)}:
        shell_score += 5
        shell_reasons.append("shell-single-raster-target")
    shell_score = min(25, shell_score)

    decorative_cta = False
    if button_like_layers:
        max_button_area_ratio = max(child.area / node_area for child in button_like_layers)
        decorative_cta = (
            len(button_like_layers) <= 2
            and max_button_area_ratio <= 0.22
            and node.width <= 220
            and node.height <= 240
            and not has_dynamic_semantics
            and (art_text_score >= 10 or ip_score >= 8)
        )

    marketing_card_score = 0
    marketing_reasons: list[str] = []
    if node.width <= 220 and node.height <= 240 and node.area >= 9_000:
        marketing_card_score += 4
        marketing_reasons.append("small-entry-tile")
    if art_text_score >= 10:
        marketing_card_score += 8
        marketing_reasons.append("marketing-art-text")
    if ip_score >= 8:
        marketing_card_score += 8
        marketing_reasons.append("marketing-illustration")
    if 1 <= len(direct_text_nodes) <= 3 and not has_dynamic_semantics:
        marketing_card_score += 4
        marketing_reasons.append("static-copy-card")
    if marketing_title_present and len(direct_text_nodes) <= 3:
        marketing_card_score += 6
        marketing_reasons.append("promo-entry-title")
    if decorative_cta:
        marketing_card_score += 6
        marketing_reasons.append("decorative-cta")
    if not has_dynamic_semantics:
        marketing_card_score += 6
        marketing_reasons.append("no-dynamic-business-data")
    if not has_control_like_subtree:
        marketing_card_score += 4
        marketing_reasons.append("no-stateful-control")
    if visual_score >= 8 and decorative_ratio >= 0.5:
        marketing_card_score += 4
        marketing_reasons.append("promo-composition-card")
    marketing_card_score = min(40, marketing_card_score)

    semantic_penalty = 0
    penalty_reasons: list[str] = []
    if direct_text_nodes:
        marketing_text_lockup = (
            len(direct_text_nodes) <= 2
            and prominent_text_count >= 1
            and (text_clone_count > 0 or promo_text_count >= 1 or ip_score >= 8 or visual_score >= 14)
        )
        if marketing_text_lockup:
            semantic_penalty -= 6 if len(direct_text_nodes) >= 2 else 4
            penalty_reasons.append("static-marketing-text-lockup")
        elif len(direct_text_nodes) >= 2:
            semantic_penalty -= 14
            penalty_reasons.append("multiple-editable-text-layers")
        else:
            semantic_penalty -= 8
            penalty_reasons.append("editable-text-layer")
    if has_dynamic_semantics:
        semantic_penalty -= 8
        penalty_reasons.append("dynamic-semantic-layer")
    semantic_penalty = max(-30, semantic_penalty)

    interaction_penalty = 0
    if button_like_layers:
        if decorative_cta:
            interaction_penalty -= 3
            penalty_reasons.append("decorative-cta-layer")
        else:
            interaction_penalty -= 15
            penalty_reasons.append("explicit-cta-layer")
    elif any(child.type in CONTAINER_TYPES and name_has_pattern(child, INTERACTIVE_LIKE_RE) for child in node.children):
        interaction_penalty -= 6
        penalty_reasons.append("interactive-subtree")

    score = visual_score + art_text_score + ip_score + semantic_penalty + interaction_penalty
    score = max(0, min(100, score))

    decision = "keep_structured"
    if (
        marketing_card_score >= 24
        and decorative_cta
        and not has_dynamic_semantics
        and (art_text_score >= 10 or marketing_title_present)
        and ip_score >= 8
        and not has_control_like_subtree
    ):
        decision = "full_raster_candidate"
    elif score >= 65 and interaction_penalty == 0:
        decision = "full_raster_candidate"
    elif (
        score >= 46
        and interaction_penalty == 0
        and visual_score >= 10
        and art_text_score >= 12
        and ip_score >= 14
        and len(keep_layers) <= 2
    ):
        decision = "full_raster_candidate"
    elif (
        interaction_penalty == 0
        and not direct_text_nodes
        and not keep_layers
        and flatten_layers
        and shell_score >= 18
    ):
        decision = "shell_raster_candidate"
    elif (
        interaction_penalty == 0
        and not direct_text_nodes
        and flatten_layers
        and shell_score >= 14
        and score >= 22
    ):
        decision = "shell_raster_candidate"
    elif score >= 40 and flatten_layers:
        decision = "partial_raster_candidate"

    if decision == "keep_structured" and score < 25 and not flatten_layers:
        return None

    return {
        "id": node.id,
        "name": node.name,
        "node_type": node.type,
        "score": score,
        "decision": decision,
        "feature_scores": {
            "visual_complexity": visual_score,
            "art_text_strength": art_text_score,
            "illustration_strength": ip_score,
            "shell_complexity": shell_score,
            "marketing_card_score": marketing_card_score,
            "semantic_penalty": semantic_penalty,
            "interaction_penalty": interaction_penalty,
        },
        "reasons": visual_reasons + art_text_reasons + ip_reasons + shell_reasons + marketing_reasons + penalty_reasons,
        "keep_layers": [] if decision in {"full_raster_candidate", "shell_raster_candidate"} else keep_layers,
        "flatten_layers": (
            [{"id": node.id, "name": node.name, "reason": "full-card-raster"}]
            if decision == "full_raster_candidate"
            else [{"id": node.id, "name": node.name, "reason": "shell-raster"}]
            if decision == "shell_raster_candidate"
            else flatten_layers
        ),
    }


def build_art_text_raster_candidate(node: Node, parent: Node | None) -> dict[str, Any] | None:
    if node.type not in TEXT_TYPES:
        return None
    if parent is None:
        return None
    if node.height < 28 or node.width < 80:
        return None

    sibling_clone_count = overlapping_text_clone_count([node] + [child for child in parent.children if child.id != node.id])
    if sibling_clone_count > 0:
        return None

    score = 0
    reasons: list[str] = []
    if node.height >= 48:
        score += 14
        reasons.append("oversized-display-text")
    elif node.height >= 36:
        score += 10
        reasons.append("large-display-text")
    if node.width >= 140:
        score += 6
        reasons.append("wide-display-copy")
    if PROMO_PUNCT_RE.search(node.name):
        score += 8
        reasons.append("exclamatory-promo-copy")
    if name_has_pattern(node, DISPLAY_TEXT_NAME_RE):
        score += 8
        reasons.append("display-text-name-signal")
    if parent.type in CONTAINER_TYPES and (
        count_mask_like(parent) > 0 or decorative_child_ratio(parent) >= 0.5 or parent.area >= node.area * 8
    ):
        score += 8
        reasons.append("decor-heavy-context")

    if score < 18:
        return None

    return {
        "id": node.id,
        "name": node.name,
        "node_type": node.type,
        "score": min(score, 100),
        "decision": "partial_raster_candidate",
        "feature_scores": {
            "visual_complexity": 0,
            "art_text_strength": min(score, 20),
            "illustration_strength": 0,
            "shell_complexity": 0,
            "semantic_penalty": 0,
            "interaction_penalty": 0,
        },
        "reasons": reasons + ["font-portability-risk-unknown"],
        "keep_layers": [],
        "flatten_layers": [{"id": node.id, "name": node.name, "reason": "art-text-raster"}],
    }


def similar_size(a: Node, b: Node) -> bool:
    return abs(a.width - b.width) <= SIZE_TOLERANCE and abs(a.height - b.height) <= SIZE_TOLERANCE


def sibling_index(node: Node, siblings: list[Node]) -> int:
    ordered = sorted(siblings, key=lambda item: (item.y, item.x, item.id))
    for idx, sibling in enumerate(ordered, start=1):
        if sibling.id == node.id:
            return idx
    return 1


def detect_repeated_siblings(node: Node, parent: Node | None) -> bool:
    if parent is None:
        return False
    similar = [sibling for sibling in parent.children if sibling.type == node.type and similar_size(node, sibling)]
    return len(similar) >= 3


def infer_text_role(node: Node, parent: Node | None) -> str:
    if parent is None:
        return "text/body"
    text_siblings = [child for child in parent.children if child.type in TEXT_TYPES]
    if len(text_siblings) >= 2:
        by_height = sorted(text_siblings, key=lambda item: (-item.height, item.y, item.x))
        rank = {item.id: index for index, item in enumerate(by_height, start=1)}
        if rank.get(node.id) == 1 and node.height >= 24:
            return "text/title"
        if rank.get(node.id) == 2 and node.height >= 18:
            return "text/subtitle"
        if node.height <= 14:
            return "text/helper"
    if node.height >= 28:
        return "text/title"
    if node.height >= 20:
        return "text/subtitle"
    if node.height <= 14:
        return "text/helper"
    return "text/body"


def infer_name(node: Node, parent: Node | None, page_scope: bool) -> tuple[str, str]:
    base_slug = slugify(node.name, "item")
    if parent is None:
        return f"page/{base_slug}", "top-level page node"

    if page_scope and parent.parent_id is None and node.type in CONTAINER_TYPES:
        return f"screen/{slugify(node.name, f'screen-{sibling_index(node, parent.children)}')}", "top-level frame on page"

    if node.type in TEXT_TYPES:
        return infer_text_role(node, parent), "text hierarchy heuristic"

    if is_background(node, parent):
        return f"bg/{slugify(parent.name, 'surface')}", "background shape"

    if is_divider(node):
        orientation = "horizontal" if node.width >= node.height else "vertical"
        return f"divider/{orientation}", "thin separator shape"

    if is_icon_like(node):
        return f"icon/{slugify(parent.name, 'decorative')}", "small decorative shape"

    if is_image_like(node):
        return f"image/{base_slug}", "image-like layer"

    if detect_repeated_siblings(node, parent):
        suffix = sibling_index(node, parent.children)
        if node.type in CONTAINER_TYPES:
            return f"card/item-{suffix}", "repeated sibling container"
        return f"list/item-{suffix}", "repeated sibling element"

    if node.type in CONTAINER_TYPES:
        if node.children:
            return f"layout/{slugify(node.name, 'stack')}", "container node"
        return f"group/{slugify(node.name, 'group')}", "empty container"

    return f"group/{base_slug}", "fallback semantic grouping"


def sorted_children(children: list[Node], axis: str) -> list[Node]:
    if axis == "VERTICAL":
        return sorted(children, key=lambda child: (child.y, child.x, child.id))
    return sorted(children, key=lambda child: (child.x, child.y, child.id))


def compute_gaps(children: list[Node], axis: str) -> list[float]:
    ordered = sorted_children(children, axis)
    gaps: list[float] = []
    for current, nxt in zip(ordered, ordered[1:]):
        if axis == "VERTICAL":
            gaps.append(nxt.y - (current.y + current.height))
        else:
            gaps.append(nxt.x - (current.x + current.width))
    return gaps


def has_overlaps(children: list[Node], axis: str) -> bool:
    return any(gap < -ALIGNMENT_TOLERANCE for gap in compute_gaps(children, axis))


def gap_consistency(gaps: list[float]) -> bool:
    positive = [gap for gap in gaps if gap >= 0]
    if len(positive) <= 1:
        return True
    return (max(positive) - min(positive)) <= 12.0


def axis_alignment_score(children: list[Node], axis: str) -> float:
    if len(children) < 2:
        return 0.0
    if axis == "VERTICAL":
        values = [child.x for child in children]
        centers = [child.center_x for child in children]
    else:
        values = [child.y for child in children]
        centers = [child.center_y for child in children]
    spread = min(statistics.pstdev(values), statistics.pstdev(centers))
    return max(0.0, 1.0 - min(spread / 40.0, 1.0))


def detect_orientation(children: list[Node]) -> tuple[str | None, list[str], float]:
    if len(children) < 2:
        return None, ["not-enough-children"], 0.0

    reasons: list[str] = []
    vertical_gaps = compute_gaps(children, "VERTICAL")
    horizontal_gaps = compute_gaps(children, "HORIZONTAL")
    vertical_overlap = has_overlaps(children, "VERTICAL")
    horizontal_overlap = has_overlaps(children, "HORIZONTAL")
    vertical_alignment = axis_alignment_score(children, "VERTICAL")
    horizontal_alignment = axis_alignment_score(children, "HORIZONTAL")

    vertical_score = 0.0
    horizontal_score = 0.0

    if not vertical_overlap:
        vertical_score += 0.45
    if not horizontal_overlap:
        horizontal_score += 0.45
    if gap_consistency(vertical_gaps):
        vertical_score += 0.25
    if gap_consistency(horizontal_gaps):
        horizontal_score += 0.25
    vertical_score += vertical_alignment * 0.3
    horizontal_score += horizontal_alignment * 0.3

    if vertical_overlap and horizontal_overlap:
        return None, ["children-overlap"], 0.0

    best_axis = "VERTICAL" if vertical_score >= horizontal_score else "HORIZONTAL"
    best_score = max(vertical_score, horizontal_score)

    if best_score < 0.65:
        if not vertical_overlap and not horizontal_overlap:
            reasons.append("grid-or-freeform-distribution")
        else:
            reasons.append("weak-linear-pattern")
        return None, reasons, best_score

    if best_axis == "VERTICAL" and not gap_consistency(vertical_gaps):
        reasons.append("uneven-vertical-gaps")
    if best_axis == "HORIZONTAL" and not gap_consistency(horizontal_gaps):
        reasons.append("uneven-horizontal-gaps")
    reasons.append("clear-linear-stack")
    return best_axis, reasons, best_score


def median_gap(children: list[Node], axis: str) -> int:
    positive = [gap for gap in compute_gaps(children, axis) if gap >= 0]
    if not positive:
        return 0
    return int(round(statistics.median(positive)))


def infer_padding(parent: Node, children: list[Node]) -> dict[str, int]:
    min_x = min(child.x for child in children)
    min_y = min(child.y for child in children)
    max_x = max(child.x + child.width for child in children)
    max_y = max(child.y + child.height for child in children)
    return {
        "left": int(round(max(0.0, min_x - parent.x))),
        "right": int(round(max(0.0, (parent.x + parent.width) - max_x))),
        "top": int(round(max(0.0, min_y - parent.y))),
        "bottom": int(round(max(0.0, (parent.y + parent.height) - max_y))),
    }


def infer_counter_alignment(parent: Node, children: list[Node], axis: str) -> str:
    if axis == "VERTICAL":
        deltas = [child.x - parent.x for child in children]
        centers = [child.center_x - parent.center_x for child in children]
        right_deltas = [(parent.x + parent.width) - (child.x + child.width) for child in children]
    else:
        deltas = [child.y - parent.y for child in children]
        centers = [child.center_y - parent.center_y for child in children]
        right_deltas = [(parent.y + parent.height) - (child.y + child.height) for child in children]

    leftish = statistics.pstdev(deltas) <= ALIGNMENT_TOLERANCE
    centered = statistics.pstdev(centers) <= ALIGNMENT_TOLERANCE
    rightish = statistics.pstdev(right_deltas) <= ALIGNMENT_TOLERANCE
    if centered:
        return "CENTER"
    if rightish and not leftish:
        return "MAX"
    return "MIN"


def infer_child_layout(parent: Node, child: Node, axis: str, padding: dict[str, int]) -> dict[str, Any]:
    overlay = False
    if axis == "VERTICAL":
        inner_width = max(parent.width - padding["left"] - padding["right"], 0.0)
        cross_fill = abs(child.width - inner_width) <= SIZE_TOLERANCE
    else:
        inner_height = max(parent.height - padding["top"] - padding["bottom"], 0.0)
        cross_fill = abs(child.height - inner_height) <= SIZE_TOLERANCE

    if child.type in SHAPE_TYPES and child.width <= 24.0 and child.height <= 24.0:
        edge_touch_x = abs((child.x + child.width) - (parent.x + parent.width)) <= ALIGNMENT_TOLERANCE
        edge_touch_y = abs(child.y - parent.y) <= ALIGNMENT_TOLERANCE
        overlay = edge_touch_x and edge_touch_y

    result: dict[str, Any] = {"id": child.id}
    if overlay:
        result["layoutPositioning"] = "ABSOLUTE"
        return result
    if cross_fill:
        result["layoutAlign"] = "STRETCH"
        result["layoutGrow"] = 1
    return result


def build_autolayout_candidate(node: Node) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if node.type not in CONTAINER_TYPES:
        return None, None
    if len(node.children) < 2:
        return None, None

    axis, reasons, confidence = detect_orientation(node.children)
    if axis is None:
        if node.type == "GROUP" and "children-overlap" not in reasons:
            return None, {
                "id": node.id,
                "name": node.name,
                "reason": ", ".join(reasons),
                "confidence": round(confidence, 2),
            }
        return None, None

    padding = infer_padding(node, node.children)
    candidate = {
        "id": node.id,
        "name": node.name,
        "node_type": node.type,
        "layoutMode": axis,
        "itemSpacing": median_gap(node.children, axis),
        "padding": padding,
        "counterAxisAlignItems": infer_counter_alignment(node, node.children, axis),
        "primaryAxisSizingMode": "AUTO",
        "counterAxisSizingMode": "AUTO",
        "children": [infer_child_layout(node, child, axis, padding) for child in node.children],
        "confidence": round(confidence, 2),
        "reasons": reasons,
        "can_apply_directly": node.type != "GROUP",
        "requires_group_conversion": node.type == "GROUP",
    }
    if node.type == "GROUP":
        return None, {
            "id": node.id,
            "name": node.name,
            "reason": "clear-linear-stack but source node is GROUP",
            "confidence": round(confidence, 2),
            "suggested_layout": candidate,
        }
    return candidate, None


def analyze(root: Node, mode: str, figma_url: str | None) -> dict[str, Any]:
    nodes = flatten(root)
    page_scope = mode in {"audit-page", "rename-page", "prepare-for-mcp"}
    rename_candidates: list[dict[str, Any]] = []
    autolayout_candidates: list[dict[str, Any]] = []
    group_conversion_candidates: list[dict[str, Any]] = []
    rasterization_candidates: list[dict[str, Any]] = []
    manual_review: list[dict[str, Any]] = []
    duplicate_names = [name for name, count in Counter(node.name for node in nodes).items() if count > 1]

    by_id = {node.id: node for node in nodes}
    for node in nodes:
        parent = by_id.get(node.parent_id) if node.parent_id else None
        if is_default_name(node):
            suggested_name, reason = infer_name(node, parent, page_scope=page_scope)
            confidence = 0.85 if node.type in TEXT_TYPES | CONTAINER_TYPES else 0.72
            rename_candidates.append(
                {
                    "id": node.id,
                    "current_name": node.name,
                    "suggested_name": suggested_name,
                    "reason": reason,
                    "confidence": round(confidence, 2),
                }
            )
        elif node.name in duplicate_names and node.type in CONTAINER_TYPES:
            suggested_name, reason = infer_name(node, parent, page_scope=page_scope)
            rename_candidates.append(
                {
                    "id": node.id,
                    "current_name": node.name,
                    "suggested_name": suggested_name,
                    "reason": f"duplicate name; {reason}",
                    "confidence": 0.61,
                }
            )

        candidate, group_candidate = build_autolayout_candidate(node)
        if candidate:
            autolayout_candidates.append(candidate)
        if group_candidate:
            group_conversion_candidates.append(group_candidate)

        raster_candidate = build_rasterization_candidate(node, parent)
        if raster_candidate:
            rasterization_candidates.append(raster_candidate)
            continue

        art_text_candidate = build_art_text_raster_candidate(node, parent)
        if art_text_candidate:
            rasterization_candidates.append(art_text_candidate)

        if node.type in CONTAINER_TYPES and len(node.children) >= 4:
            overlap_axis, overlap_reasons, overlap_conf = detect_orientation(node.children)
            if overlap_axis is None and overlap_conf < 0.65:
                manual_review.append(
                    {
                        "id": node.id,
                        "name": node.name,
                        "reason": ", ".join(overlap_reasons),
                        "severity": "medium",
                    }
                )

    summary = {
        "mode": mode,
        "total_nodes": len(nodes),
        "rename_candidates": len(rename_candidates),
        "autolayout_candidates": len(autolayout_candidates),
        "group_conversion_candidates": len(group_conversion_candidates),
        "rasterization_candidates": len(rasterization_candidates),
        "full_raster_candidates": sum(
            1 for item in rasterization_candidates if item["decision"] == "full_raster_candidate"
        ),
        "shell_raster_candidates": sum(
            1 for item in rasterization_candidates if item["decision"] == "shell_raster_candidate"
        ),
        "partial_raster_candidates": sum(
            1 for item in rasterization_candidates if item["decision"] == "partial_raster_candidate"
        ),
        "manual_review": len(manual_review),
    }
    return {
        "figma_url": figma_url,
        "scope": {
            "root_id": root.id,
            "root_name": root.name,
            "root_type": root.type,
            "mode": mode,
        },
        "summary": summary,
        "rename_candidates": rename_candidates,
        "autolayout_candidates": autolayout_candidates,
        "group_conversion_candidates": group_conversion_candidates,
        "rasterization_candidates": rasterization_candidates,
        "manual_review": manual_review,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata_path", type=Path, help="Path to metadata XML or JSON")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["audit-page", "audit-frame", "rename-page", "autolayout-frame", "prepare-for-mcp"],
        help="Skill mode that determines scope assumptions",
    )
    parser.add_argument("--figma-url", default=None, help="Original Figma link for traceability")
    parser.add_argument("--output", type=Path, default=None, help="Write JSON report to this path")
    args = parser.parse_args()

    try:
        root = load_metadata(args.metadata_path)
        report = analyze(root, args.mode, args.figma_url)
    except Exception as exc:  # pragma: no cover - CLI safety
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
