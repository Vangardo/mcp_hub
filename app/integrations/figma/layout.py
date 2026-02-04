"""
Figma layout transformer.

Converts raw Figma JSON tree into a compact, CSS-oriented layout description.
Strips vector paths, plugin data, export settings, and other noise.
Keeps: structure, dimensions, auto-layout, colors, fonts, text, border-radius,
gradients, image refs, shadows.

Safety: enforces max node count to prevent token explosion.
"""

from typing import Any, Optional


# Hard limit: if the tree has more nodes than this, truncate and warn
MAX_NODES = 500


def _rgba_to_css(color: dict, opacity: float = 1.0) -> str:
    r = round(color.get("r", 0) * 255)
    g = round(color.get("g", 0) * 255)
    b = round(color.get("b", 0) * 255)
    a = round(color.get("a", 1.0) * opacity, 2)
    if a >= 1.0:
        return f"#{r:02x}{g:02x}{b:02x}"
    return f"rgba({r},{g},{b},{a})"


def _gradient_to_css(fill: dict) -> str:
    fill_type = fill.get("type", "GRADIENT_LINEAR")
    stops = fill.get("gradientStops", [])
    if not stops:
        return "gradient"

    stop_strs = []
    for stop in stops:
        color = _rgba_to_css(stop.get("color", {}))
        pos = round(stop.get("position", 0) * 100)
        stop_strs.append(f"{color} {pos}%")

    stops_css = ", ".join(stop_strs)

    if "LINEAR" in fill_type:
        # Extract angle from gradient handle positions
        handles = fill.get("gradientHandlePositions", [])
        if len(handles) >= 2:
            import math
            dx = handles[1].get("x", 0) - handles[0].get("x", 0)
            dy = handles[1].get("y", 0) - handles[0].get("y", 0)
            angle = round(math.degrees(math.atan2(dy, dx)) + 90) % 360
            return f"linear-gradient({angle}deg, {stops_css})"
        return f"linear-gradient({stops_css})"
    elif "RADIAL" in fill_type:
        return f"radial-gradient({stops_css})"
    elif "ANGULAR" in fill_type:
        return f"conic-gradient({stops_css})"
    elif "DIAMOND" in fill_type:
        return f"diamond-gradient({stops_css})"
    return f"gradient({stops_css})"


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
            image_ref = fill.get("imageRef", "")
            scale_mode = fill.get("scaleMode", "FILL").lower()
            if image_ref:
                return f"image({image_ref}, {scale_mode})"
            return f"image({scale_mode})"
        if "GRADIENT" in fill_type:
            return _gradient_to_css(fill)
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
            spread = round(eff.get("spread", 0))
            if spread:
                result.append(f"shadow({ox} {oy} {blur} {spread} {color})")
            else:
                result.append(f"shadow({ox} {oy} {blur} {color})")
        elif eff_type == "INNER_SHADOW":
            c = eff.get("color", {})
            color = _rgba_to_css(c, c.get("a", 0.25))
            ox = round(eff.get("offset", {}).get("x", 0))
            oy = round(eff.get("offset", {}).get("y", 0))
            blur = round(eff.get("radius", 0))
            result.append(f"inner-shadow({ox} {oy} {blur} {color})")
        elif eff_type == "LAYER_BLUR":
            result.append(f"blur({round(eff.get('radius', 0))}px)")
        elif eff_type == "BACKGROUND_BLUR":
            result.append(f"backdrop-blur({round(eff.get('radius', 0))}px)")
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
    if style.get("textAlignVertical"):
        valign = style["textAlignVertical"].lower()
        if valign != "top":
            result["valign"] = valign
    if style.get("lineHeightPx") and style.get("fontSize"):
        lh_px = round(style["lineHeightPx"], 1)
        result["lineHeight"] = f"{lh_px}px"
    if style.get("letterSpacing") and style["letterSpacing"] != 0:
        result["letterSpacing"] = f"{round(style['letterSpacing'], 1)}px"
    if style.get("textDecoration"):
        dec = style["textDecoration"].lower()
        if dec != "none":
            result["decoration"] = dec
    if style.get("textCase"):
        case = style["textCase"].lower()
        if case not in ("original", "none"):
            result["textTransform"] = case
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

    if node.get("layoutWrap") == "WRAP":
        result["wrap"] = True

    return result


class _NodeCounter:
    def __init__(self, max_nodes: int):
        self.count = 0
        self.max_nodes = max_nodes
        self.truncated = False

    def increment(self) -> bool:
        self.count += 1
        if self.count > self.max_nodes:
            self.truncated = True
            return False
        return True


def _compact_node(
    node: dict,
    depth: int = 0,
    max_depth: int = 50,
    counter: Optional[_NodeCounter] = None,
) -> Optional[dict]:
    if depth > max_depth:
        return None

    if counter and not counter.increment():
        return None

    node_type = node.get("type", "UNKNOWN")
    visible = node.get("visible", True)
    if not visible:
        return None

    # Skip irrelevant types
    skip_types = {"BOOLEAN_OPERATION", "SLICE", "STAMP"}
    if node_type in skip_types:
        return None

    # Skip pure vectors (icons etc.) — they add noise, better exported as SVG
    if node_type == "VECTOR":
        bbox = node.get("absoluteBoundingBox", {})
        w = bbox.get("width", 0)
        h = bbox.get("height", 0)
        fill = _extract_fill(node.get("fills", []))
        return {
            "type": "VECTOR",
            "name": node.get("name", ""),
            "id": node.get("id", ""),
            "w": round(w),
            "h": round(h),
            "fill": fill,
            "note": "export as SVG via figma.images.export",
        }

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

    # Overflow / clip
    if node.get("clipsContent"):
        result["overflow"] = "hidden"

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
        result["sizingH"] = constraints_h.lower()
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
            if counter and counter.truncated:
                break
            compact = _compact_node(child, depth + 1, max_depth, counter)
            if compact:
                compact_children.append(compact)
        if compact_children:
            result["children"] = compact_children

    return result


def transform_to_layout(
    figma_data: dict,
    max_depth: int = 50,
    max_nodes: int = MAX_NODES,
) -> dict:
    """Transform raw Figma file/nodes response into compact layout tree."""
    counter = _NodeCounter(max_nodes)
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
            if counter.truncated:
                break
            compact = _compact_node(page, max_depth=max_depth, counter=counter)
            if compact:
                pages.append(compact)
        result["pages"] = pages

    # Process nodes response (from get_nodes)
    nodes = figma_data.get("nodes")
    if nodes:
        result["nodes"] = {}
        for node_id, node_data in nodes.items():
            if counter.truncated:
                break
            doc = node_data.get("document")
            if doc:
                compact = _compact_node(doc, max_depth=max_depth, counter=counter)
                if compact:
                    result["nodes"][node_id] = compact

    # Stats and warnings
    result["_stats"] = {
        "nodes_processed": counter.count,
        "truncated": counter.truncated,
        "max_nodes": max_nodes,
    }
    if counter.truncated:
        result["_warning"] = (
            f"Output truncated at {max_nodes} nodes. "
            f"Use node_id parameter to target specific sections, "
            f"or use depth parameter to limit tree depth."
        )

    return result


def layout_to_text(layout: dict, indent: int = 0) -> str:
    """Convert compact layout dict to a human-readable text representation."""
    lines = []

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

        # Stats
        stats = layout.get("_stats", {})
        if stats:
            lines.append("")
            lines.append(f"--- {stats.get('nodes_processed', 0)} nodes processed ---")
        if layout.get("_warning"):
            lines.append(f"WARNING: {layout['_warning']}")

        return "\n".join(lines)

    return _node_to_text(layout, indent)


def _node_to_text(node: dict, indent: int = 0) -> str:
    lines = []
    prefix = "  " * indent

    # Build node descriptor
    node_type = node.get("type", "")
    name = node.get("name", "")
    node_id = node.get("id", "")
    parts = [f'{node_type} "{name}" [{node_id}]']

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
        if layout.get("wrap"):
            layout_parts.append("wrap")
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

    # Overflow
    if node.get("overflow"):
        parts.append(f"overflow:{node['overflow']}")

    # Sizing
    if node.get("sizingH"):
        parts.append(f"w:{node['sizingH']}")
    if node.get("sizingV"):
        parts.append(f"h:{node['sizingV']}")

    # Vector note
    if node.get("note"):
        parts.append(node["note"])

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
        if ts.get("lineHeight"):
            ts_parts.append(f"lh:{ts['lineHeight']}")
        if ts.get("letterSpacing"):
            ts_parts.append(f"ls:{ts['letterSpacing']}")
        if ts.get("decoration"):
            ts_parts.append(ts["decoration"])
        if ts.get("textTransform"):
            ts_parts.append(ts["textTransform"])

        font_info = " ".join(ts_parts)
        if font_info:
            line += f" [{font_info}]"
        line += f' "{text_preview}"'

    lines.append(line)

    # Children
    for child in node.get("children", []):
        lines.append(_node_to_text(child, indent + 1))

    return "\n".join(lines)
