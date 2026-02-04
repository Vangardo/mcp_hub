"""
Figma layout transformer.

Converts raw Figma JSON tree into a compact, CSS-oriented layout description.
Strips vector paths, plugin data, export settings, and other noise.
Keeps: structure, dimensions, auto-layout, colors, fonts, text, border-radius, images.
"""

from typing import Any, Optional


def _rgba_to_css(color: dict, opacity: float = 1.0) -> str:
    r = round(color.get("r", 0) * 255)
    g = round(color.get("g", 0) * 255)
    b = round(color.get("b", 0) * 255)
    a = round(color.get("a", 1.0) * opacity, 2)
    if a >= 1.0:
        return f"#{r:02x}{g:02x}{b:02x}"
    return f"rgba({r},{g},{b},{a})"


def _extract_fill(fills: list) -> Optional[str]:
    if not fills:
        return None
    for fill in fills:
        if not fill.get("visible", True):
            continue
        fill_type = fill.get("type", "")
        if fill_type == "SOLID":
            return _rgba_to_css(fill["color"], fill.get("opacity", 1.0))
        if fill_type == "IMAGE":
            return "image"
        if "GRADIENT" in fill_type:
            return f"gradient({fill_type.lower()})"
    return None


def _extract_stroke(strokes: list, weight: Any) -> Optional[str]:
    if not strokes or not weight:
        return None
    for stroke in strokes:
        if not stroke.get("visible", True):
            continue
        if stroke.get("type") == "SOLID":
            color = _rgba_to_css(stroke["color"], stroke.get("opacity", 1.0))
            return f"{weight}px {color}"
    return None


def _extract_radius(node: dict) -> Optional[str]:
    radii = node.get("rectangleCornerRadii")
    if radii and any(r > 0 for r in radii):
        if len(set(radii)) == 1:
            return f"{int(radii[0])}px"
        return " ".join(f"{int(r)}px" for r in radii)
    r = node.get("cornerRadius")
    if r and r > 0:
        return f"{int(r)}px"
    return None


def _extract_effects(effects: list) -> list[str]:
    if not effects:
        return []
    result = []
    for eff in effects:
        if not eff.get("visible", True):
            continue
        eff_type = eff.get("type", "")
        if eff_type == "DROP_SHADOW":
            c = eff.get("color", {})
            color = _rgba_to_css(c, c.get("a", 0.25))
            ox = round(eff.get("offset", {}).get("x", 0))
            oy = round(eff.get("offset", {}).get("y", 0))
            blur = round(eff.get("radius", 0))
            result.append(f"shadow({ox} {oy} {blur} {color})")
        elif eff_type == "INNER_SHADOW":
            result.append("inner-shadow")
        elif eff_type in ("LAYER_BLUR", "BACKGROUND_BLUR"):
            blur = round(eff.get("radius", 0))
            result.append(f"blur({blur}px)")
    return result


def _extract_text_style(node: dict) -> Optional[dict]:
    style = node.get("style", {})
    if not style:
        return None
    result = {}
    if style.get("fontFamily"):
        result["font"] = style["fontFamily"]
    if style.get("fontSize"):
        result["size"] = f"{int(style['fontSize'])}px"
    if style.get("fontWeight"):
        result["weight"] = int(style["fontWeight"])
    if style.get("textAlignHorizontal"):
        align = style["textAlignHorizontal"].lower()
        if align != "left":
            result["align"] = align
    if style.get("lineHeightPx") and style.get("fontSize"):
        lh = round(style["lineHeightPx"] / style["fontSize"], 2)
        if lh != 1.0:
            result["lineHeight"] = lh
    if style.get("letterSpacing") and style["letterSpacing"] != 0:
        result["letterSpacing"] = f"{round(style['letterSpacing'], 1)}px"
    return result if result else None


def _extract_auto_layout(node: dict) -> Optional[dict]:
    layout_mode = node.get("layoutMode")
    if not layout_mode or layout_mode == "NONE":
        return None
    result = {"direction": "row" if layout_mode == "HORIZONTAL" else "column"}

    gap = node.get("itemSpacing")
    if gap and gap > 0:
        result["gap"] = int(gap)

    pt = node.get("paddingTop", 0)
    pr = node.get("paddingRight", 0)
    pb = node.get("paddingBottom", 0)
    pl = node.get("paddingLeft", 0)
    if any(p > 0 for p in [pt, pr, pb, pl]):
        if pt == pb and pl == pr:
            if pt == pl:
                result["padding"] = int(pt)
            else:
                result["padding"] = f"{int(pt)} {int(pl)}"
        else:
            result["padding"] = f"{int(pt)} {int(pr)} {int(pb)} {int(pl)}"

    primary = node.get("primaryAxisAlignItems", "")
    counter = node.get("counterAxisAlignItems", "")
    align_map = {"MIN": "start", "MAX": "end", "CENTER": "center", "SPACE_BETWEEN": "space-between"}
    if primary in align_map and primary != "MIN":
        result["justify"] = align_map[primary]
    if counter in align_map and counter != "MIN":
        result["alignItems"] = align_map[counter]

    return result


def _compact_node(node: dict, depth: int = 0, max_depth: int = 50) -> Optional[dict]:
    if depth > max_depth:
        return None

    node_type = node.get("type", "UNKNOWN")
    visible = node.get("visible", True)
    if not visible:
        return None

    # Skip irrelevant types
    skip_types = {"BOOLEAN_OPERATION", "SLICE", "STAMP"}
    if node_type in skip_types:
        return None

    result: dict[str, Any] = {
        "type": node_type,
        "name": node.get("name", ""),
    }

    # Node ID
    node_id = node.get("id")
    if node_id:
        result["id"] = node_id

    # Dimensions
    bbox = node.get("absoluteBoundingBox")
    if bbox:
        result["w"] = round(bbox.get("width", 0))
        result["h"] = round(bbox.get("height", 0))

    # Auto-layout
    auto_layout = _extract_auto_layout(node)
    if auto_layout:
        result["layout"] = auto_layout

    # Background / fill
    fills = node.get("fills", [])
    bg = _extract_fill(fills)
    if bg:
        result["fill"] = bg

    # Stroke
    stroke = _extract_stroke(node.get("strokes", []), node.get("strokeWeight"))
    if stroke:
        result["stroke"] = stroke

    # Border radius
    radius = _extract_radius(node)
    if radius:
        result["radius"] = radius

    # Effects
    effects = _extract_effects(node.get("effects", []))
    if effects:
        result["effects"] = effects

    # Opacity
    opacity = node.get("opacity")
    if opacity is not None and opacity < 1.0:
        result["opacity"] = round(opacity, 2)

    # Text
    if node_type == "TEXT":
        chars = node.get("characters", "")
        result["text"] = chars[:500] if len(chars) > 500 else chars

        text_style = _extract_text_style(node)
        if text_style:
            result["textStyle"] = text_style

        text_fill = _extract_fill(fills)
        if text_fill:
            result["color"] = text_fill
            result.pop("fill", None)

    # Sizing constraints
    constraints_h = node.get("layoutSizingHorizontal")
    constraints_v = node.get("layoutSizingVertical")
    if constraints_h and constraints_h != "FIXED":
        result["sizingH"] = constraints_h.lower()  # "fill" or "hug"
    if constraints_v and constraints_v != "FIXED":
        result["sizingV"] = constraints_v.lower()

    # Component info
    if node_type == "INSTANCE":
        comp_id = node.get("componentId")
        if comp_id:
            result["componentId"] = comp_id

    # Children
    children = node.get("children", [])
    if children:
        compact_children = []
        for child in children:
            compact = _compact_node(child, depth + 1, max_depth)
            if compact:
                compact_children.append(compact)
        if compact_children:
            result["children"] = compact_children

    return result


def transform_to_layout(figma_data: dict, max_depth: int = 50) -> dict:
    """Transform raw Figma file/nodes response into compact layout tree."""
    result: dict[str, Any] = {}

    # File-level info
    if figma_data.get("name"):
        result["name"] = figma_data["name"]
    if figma_data.get("lastModified"):
        result["lastModified"] = figma_data["lastModified"]

    # Global styles summary
    styles = figma_data.get("styles", {})
    if styles:
        style_summary = {}
        for style_id, style_info in styles.items():
            style_type = style_info.get("styleType", "UNKNOWN").lower()
            if style_type not in style_summary:
                style_summary[style_type] = []
            style_summary[style_type].append({
                "id": style_id,
                "name": style_info.get("name", ""),
            })
        result["styles"] = style_summary

    # Process document tree
    document = figma_data.get("document")
    if document:
        children = document.get("children", [])
        pages = []
        for page in children:
            compact = _compact_node(page, max_depth=max_depth)
            if compact:
                pages.append(compact)
        result["pages"] = pages

    # Process nodes response (from get_nodes)
    nodes = figma_data.get("nodes")
    if nodes:
        result["nodes"] = {}
        for node_id, node_data in nodes.items():
            doc = node_data.get("document")
            if doc:
                compact = _compact_node(doc, max_depth=max_depth)
                if compact:
                    result["nodes"][node_id] = compact

    return result


def layout_to_text(layout: dict, indent: int = 0) -> str:
    """Convert compact layout dict to a human-readable text representation."""
    lines = []
    prefix = "  " * indent

    if indent == 0:
        if layout.get("name"):
            lines.append(f"# {layout['name']}")
        if layout.get("styles"):
            lines.append(f"Styles: {', '.join(f'{k}({len(v)})' for k, v in layout['styles'].items())}")
        lines.append("")

        for page in layout.get("pages", []):
            lines.append(_node_to_text(page, 0))

        for node_id, node in layout.get("nodes", {}).items():
            lines.append(_node_to_text(node, 0))

        return "\n".join(lines)

    return _node_to_text(layout, indent)


def _node_to_text(node: dict, indent: int = 0) -> str:
    lines = []
    prefix = "  " * indent

    # Build node descriptor
    node_type = node.get("type", "")
    name = node.get("name", "")
    parts = [f'{node_type} "{name}"']

    # Dimensions
    w, h = node.get("w"), node.get("h")
    if w and h:
        parts.append(f"{w}x{h}")

    # Layout
    layout = node.get("layout")
    if layout:
        layout_parts = [layout["direction"]]
        if "gap" in layout:
            layout_parts.append(f"gap:{layout['gap']}")
        if "padding" in layout:
            layout_parts.append(f"pad:{layout['padding']}")
        if "justify" in layout:
            layout_parts.append(f"justify:{layout['justify']}")
        if "alignItems" in layout:
            layout_parts.append(f"align:{layout['alignItems']}")
        parts.append(", ".join(layout_parts))

    # Fill
    if node.get("fill"):
        parts.append(f"bg:{node['fill']}")

    # Radius
    if node.get("radius"):
        parts.append(f"r:{node['radius']}")

    # Stroke
    if node.get("stroke"):
        parts.append(f"border:{node['stroke']}")

    # Opacity
    if node.get("opacity") is not None:
        parts.append(f"opacity:{node['opacity']}")

    # Effects
    if node.get("effects"):
        parts.extend(node["effects"])

    # Sizing
    if node.get("sizingH"):
        parts.append(f"w:{node['sizingH']}")
    if node.get("sizingV"):
        parts.append(f"h:{node['sizingV']}")

    line = f"{prefix}{' | '.join(parts)}"

    # Text content
    if node.get("text"):
        text_preview = node["text"]
        if len(text_preview) > 80:
            text_preview = text_preview[:80] + "..."
        ts = node.get("textStyle", {})
        ts_parts = []
        if ts.get("font"):
            ts_parts.append(ts["font"])
        if ts.get("weight"):
            ts_parts.append(str(ts["weight"]))
        if ts.get("size"):
            ts_parts.append(ts["size"])
        if node.get("color"):
            ts_parts.append(node["color"])
        if ts.get("align"):
            ts_parts.append(ts["align"])

        font_info = " ".join(ts_parts)
        if font_info:
            line += f" [{font_info}]"
        line += f' "{text_preview}"'

    lines.append(line)

    # Children
    for child in node.get("children", []):
        lines.append(_node_to_text(child, indent + 1))

    return "\n".join(lines)
