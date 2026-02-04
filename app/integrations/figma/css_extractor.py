"""
Figma → CSS-ready extractor.

One-shot tool that fetches a Figma page/frame, resolves images,
extracts design tokens, and returns CSS-ready output that AI can
directly use for HTML/CSS coding.

Output sections:
1. DESIGN TOKENS — CSS variables for colors, fonts, spacing
2. IMAGES — resolved URLs for all image fills and exported SVG icons
3. COMPONENT TREE — HTML-like hierarchy with CSS properties per node
"""

import asyncio
import math
from collections import Counter
from typing import Any, Optional

from app.integrations.figma.client import FigmaClient


MAX_NODES = 500
MAX_IMAGE_EXPORTS = 50


def _rgba_to_css(color: dict, opacity: float = 1.0) -> str:
    r = round(color.get("r", 0) * 255)
    g = round(color.get("g", 0) * 255)
    b = round(color.get("b", 0) * 255)
    a = round(color.get("a", 1.0) * opacity, 2)
    if a >= 1.0:
        return f"#{r:02x}{g:02x}{b:02x}"
    return f"rgba({r}, {g}, {b}, {a})"


def _gradient_to_css(fill: dict) -> Optional[str]:
    fill_type = fill.get("type", "GRADIENT_LINEAR")
    stops = fill.get("gradientStops", [])
    if not stops:
        return None

    stop_strs = []
    for stop in stops:
        color = _rgba_to_css(stop.get("color", {}))
        pos = round(stop.get("position", 0) * 100)
        stop_strs.append(f"{color} {pos}%")
    stops_css = ", ".join(stop_strs)

    if "LINEAR" in fill_type:
        handles = fill.get("gradientHandlePositions", [])
        if len(handles) >= 2:
            dx = handles[1].get("x", 0) - handles[0].get("x", 0)
            dy = handles[1].get("y", 0) - handles[0].get("y", 0)
            angle = round(math.degrees(math.atan2(dy, dx)) + 90) % 360
            return f"linear-gradient({angle}deg, {stops_css})"
        return f"linear-gradient({stops_css})"
    elif "RADIAL" in fill_type:
        return f"radial-gradient(circle, {stops_css})"
    elif "ANGULAR" in fill_type:
        return f"conic-gradient({stops_css})"
    return f"linear-gradient({stops_css})"


def _extract_css_background(fills: list, image_urls: dict) -> Optional[str]:
    if not fills:
        return None
    for fill in fills:
        if not fill.get("visible", True):
            continue
        t = fill.get("type", "")
        if t == "SOLID":
            return _rgba_to_css(fill["color"], fill.get("opacity", 1.0))
        if t == "IMAGE":
            ref = fill.get("imageRef", "")
            url = image_urls.get(ref, "")
            mode = fill.get("scaleMode", "FILL")
            size = "cover" if mode == "FILL" else "contain" if mode == "FIT" else "auto"
            if url:
                return f"url({url}) center / {size} no-repeat"
            return f"url(IMAGE_{ref}) center / {size} no-repeat"
        if "GRADIENT" in t:
            return _gradient_to_css(fill)
    return None


def _extract_css_shadow(effects: list) -> Optional[str]:
    parts = []
    for eff in effects:
        if not eff.get("visible", True):
            continue
        t = eff.get("type", "")
        if t in ("DROP_SHADOW", "INNER_SHADOW"):
            c = eff.get("color", {})
            color = _rgba_to_css(c, c.get("a", 0.25))
            ox = round(eff.get("offset", {}).get("x", 0))
            oy = round(eff.get("offset", {}).get("y", 0))
            blur = round(eff.get("radius", 0))
            spread = round(eff.get("spread", 0))
            inset = "inset " if t == "INNER_SHADOW" else ""
            parts.append(f"{inset}{ox}px {oy}px {blur}px {spread}px {color}")
    return ", ".join(parts) if parts else None


def _extract_css_filter(effects: list) -> Optional[str]:
    parts = []
    for eff in effects:
        if not eff.get("visible", True):
            continue
        if eff.get("type") == "LAYER_BLUR":
            parts.append(f"blur({round(eff.get('radius', 0))}px)")
    return " ".join(parts) if parts else None


def _extract_css_backdrop_filter(effects: list) -> Optional[str]:
    parts = []
    for eff in effects:
        if not eff.get("visible", True):
            continue
        if eff.get("type") == "BACKGROUND_BLUR":
            parts.append(f"blur({round(eff.get('radius', 0))}px)")
    return " ".join(parts) if parts else None


def _node_css(node: dict, image_urls: dict) -> dict[str, str]:
    """Extract CSS properties from a Figma node."""
    css: dict[str, str] = {}
    node_type = node.get("type", "")

    # Dimensions
    bbox = node.get("absoluteBoundingBox", {})
    w = round(bbox.get("width", 0))
    h = round(bbox.get("height", 0))
    if w:
        css["width"] = f"{w}px"
    if h:
        css["height"] = f"{h}px"

    # Sizing overrides
    sh = node.get("layoutSizingHorizontal", "")
    sv = node.get("layoutSizingVertical", "")
    if sh == "FILL":
        css["width"] = "100%"
    elif sh == "HUG":
        css["width"] = "auto"
    if sv == "FILL":
        css["height"] = "100%"
    elif sv == "HUG":
        css["height"] = "auto"

    # Auto-layout → Flexbox
    layout_mode = node.get("layoutMode")
    if layout_mode and layout_mode != "NONE":
        css["display"] = "flex"
        css["flex-direction"] = "row" if layout_mode == "HORIZONTAL" else "column"

        gap = node.get("itemSpacing", 0)
        if gap > 0:
            css["gap"] = f"{int(gap)}px"

        pt = int(node.get("paddingTop", 0))
        pr = int(node.get("paddingRight", 0))
        pb = int(node.get("paddingBottom", 0))
        pl = int(node.get("paddingLeft", 0))
        if any([pt, pr, pb, pl]):
            if pt == pb and pl == pr and pt == pl:
                css["padding"] = f"{pt}px"
            elif pt == pb and pl == pr:
                css["padding"] = f"{pt}px {pl}px"
            else:
                css["padding"] = f"{pt}px {pr}px {pb}px {pl}px"

        align_map = {
            "MIN": "flex-start", "MAX": "flex-end",
            "CENTER": "center", "SPACE_BETWEEN": "space-between",
        }
        primary = node.get("primaryAxisAlignItems", "")
        counter = node.get("counterAxisAlignItems", "")
        if primary in align_map:
            css["justify-content"] = align_map[primary]
        if counter in align_map:
            css["align-items"] = align_map[counter]

        if node.get("layoutWrap") == "WRAP":
            css["flex-wrap"] = "wrap"

    # Background
    fills = node.get("fills", [])
    bg = _extract_css_background(fills, image_urls)
    if bg and node_type != "TEXT":
        if bg.startswith("url(") or bg.startswith("linear-") or bg.startswith("radial-") or bg.startswith("conic-"):
            css["background"] = bg
        else:
            css["background-color"] = bg

    # Border
    strokes = node.get("strokes", [])
    stroke_weight = node.get("strokeWeight")
    if strokes and stroke_weight:
        for stroke in strokes:
            if not stroke.get("visible", True):
                continue
            if stroke.get("type") == "SOLID":
                color = _rgba_to_css(stroke["color"], stroke.get("opacity", 1.0))
                css["border"] = f"{stroke_weight}px solid {color}"
                break

    # Border radius
    radii = node.get("rectangleCornerRadii")
    if radii and any(r > 0 for r in radii):
        if len(set(radii)) == 1:
            css["border-radius"] = f"{int(radii[0])}px"
        else:
            css["border-radius"] = " ".join(f"{int(r)}px" for r in radii)
    elif node.get("cornerRadius", 0) > 0:
        css["border-radius"] = f"{int(node['cornerRadius'])}px"

    # Shadow
    shadow = _extract_css_shadow(node.get("effects", []))
    if shadow:
        css["box-shadow"] = shadow

    # Filter
    flt = _extract_css_filter(node.get("effects", []))
    if flt:
        css["filter"] = flt

    # Backdrop filter
    bdf = _extract_css_backdrop_filter(node.get("effects", []))
    if bdf:
        css["backdrop-filter"] = bdf

    # Opacity
    opacity = node.get("opacity")
    if opacity is not None and opacity < 1.0:
        css["opacity"] = str(round(opacity, 2))

    # Overflow
    if node.get("clipsContent"):
        css["overflow"] = "hidden"

    # Text styles
    if node_type == "TEXT":
        style = node.get("style", {})
        if style.get("fontFamily"):
            css["font-family"] = f"'{style['fontFamily']}', sans-serif"
        if style.get("fontSize"):
            css["font-size"] = f"{int(style['fontSize'])}px"
        if style.get("fontWeight"):
            css["font-weight"] = str(int(style["fontWeight"]))
        if style.get("lineHeightPx"):
            css["line-height"] = f"{round(style['lineHeightPx'], 1)}px"
        if style.get("letterSpacing") and style["letterSpacing"] != 0:
            css["letter-spacing"] = f"{round(style['letterSpacing'], 1)}px"
        if style.get("textAlignHorizontal"):
            align = style["textAlignHorizontal"].lower()
            if align != "left":
                css["text-align"] = align
        if style.get("textDecoration"):
            dec = style["textDecoration"].lower()
            if dec not in ("none", ""):
                css["text-decoration"] = dec
        if style.get("textCase"):
            case_map = {
                "UPPER": "uppercase", "LOWER": "lowercase",
                "TITLE": "capitalize", "SMALL_CAPS": "small-caps",
            }
            tc = case_map.get(style["textCase"])
            if tc:
                css["text-transform"] = tc

        # Text color
        text_bg = _extract_css_background(fills, image_urls)
        if text_bg and not text_bg.startswith("url("):
            css["color"] = text_bg

    return css


class _Counter:
    def __init__(self, max_n: int):
        self.n = 0
        self.max_n = max_n
        self.truncated = False

    def tick(self) -> bool:
        self.n += 1
        if self.n > self.max_n:
            self.truncated = True
            return False
        return True


def _collect_assets(node: dict, image_refs: set, vector_ids: list, depth: int = 0):
    """Walk tree and collect image references and vector node IDs for export."""
    if depth > 50:
        return
    if not node.get("visible", True):
        return

    for fill in node.get("fills", []):
        if fill.get("type") == "IMAGE" and fill.get("imageRef"):
            image_refs.add(fill["imageRef"])

    if node.get("type") == "VECTOR" and len(vector_ids) < MAX_IMAGE_EXPORTS:
        node_id = node.get("id")
        if node_id:
            vector_ids.append(node_id)

    for child in node.get("children", []):
        _collect_assets(child, image_refs, vector_ids, depth + 1)


def _css_to_str(css: dict[str, str]) -> str:
    if not css:
        return ""
    # Order CSS properties logically
    order = [
        "display", "flex-direction", "flex-wrap", "justify-content", "align-items",
        "gap", "width", "height", "padding", "margin",
        "background-color", "background", "color",
        "font-family", "font-size", "font-weight", "line-height",
        "letter-spacing", "text-align", "text-decoration", "text-transform",
        "border", "border-radius", "box-shadow",
        "opacity", "overflow", "filter", "backdrop-filter",
    ]
    ordered = []
    for prop in order:
        if prop in css:
            ordered.append(f"{prop}: {css[prop]}")
    # Any remaining
    for prop, val in css.items():
        if prop not in order:
            ordered.append(f"{prop}: {val}")
    return "; ".join(ordered)


def _html_tag(node_type: str) -> str:
    """Suggest HTML tag based on Figma node type and semantics."""
    tag_map = {
        "TEXT": "span",
        "FRAME": "div",
        "GROUP": "div",
        "COMPONENT": "div",
        "COMPONENT_SET": "div",
        "INSTANCE": "div",
        "RECTANGLE": "div",
        "ELLIPSE": "div",
        "LINE": "hr",
        "VECTOR": "svg",
        "CANVAS": "section",
    }
    return tag_map.get(node_type, "div")


def _render_node(
    node: dict,
    image_urls: dict,
    counter: _Counter,
    indent: int = 0,
) -> list[str]:
    """Render a node as HTML-like structure with CSS."""
    if not counter.tick():
        return []
    if not node.get("visible", True):
        return []

    node_type = node.get("type", "")
    skip = {"BOOLEAN_OPERATION", "SLICE", "STAMP"}
    if node_type in skip:
        return []

    prefix = "  " * indent
    name = node.get("name", "")
    node_id = node.get("id", "")
    tag = _html_tag(node_type)
    lines = []

    # Vector — just a reference
    if node_type == "VECTOR":
        bbox = node.get("absoluteBoundingBox", {})
        w = round(bbox.get("width", 0))
        h = round(bbox.get("height", 0))
        lines.append(f'{prefix}<svg name="{name}" id="{node_id}" width="{w}" height="{h}">')
        lines.append(f'{prefix}  <!-- export via figma.images.export id="{node_id}" format="svg" -->')
        lines.append(f'{prefix}</svg>')
        return lines

    css = _node_css(node, image_urls)
    css_str = _css_to_str(css)
    style_attr = f' style="{css_str}"' if css_str else ""
    text = node.get("characters", "")

    children = node.get("children", [])

    if node_type == "TEXT":
        text_preview = text[:200] + ("..." if len(text) > 200 else "")
        lines.append(f'{prefix}<{tag} name="{name}" id="{node_id}"{style_attr}>{text_preview}</{tag}>')
    elif not children:
        lines.append(f'{prefix}<{tag} name="{name}" id="{node_id}"{style_attr} />')
    else:
        lines.append(f'{prefix}<{tag} name="{name}" id="{node_id}"{style_attr}>')
        for child in children:
            if counter.truncated:
                lines.append(f'{prefix}  <!-- TRUNCATED: use node_id="{node_id}" to get this section -->')
                break
            lines.extend(_render_node(child, image_urls, counter, indent + 1))
        lines.append(f'{prefix}</{tag}>')

    return lines


def _extract_tokens(root_nodes: list, image_urls: dict) -> str:
    """Extract design tokens from the node tree."""
    colors: Counter = Counter()
    fonts: Counter = Counter()
    font_sizes: set = set()

    def _walk(node: dict):
        if not node.get("visible", True):
            return

        # Collect colors
        for fill in node.get("fills", []):
            if fill.get("type") == "SOLID" and fill.get("visible", True):
                c = _rgba_to_css(fill["color"], fill.get("opacity", 1.0))
                colors[c] += 1

        for stroke in node.get("strokes", []):
            if stroke.get("type") == "SOLID" and stroke.get("visible", True):
                c = _rgba_to_css(stroke["color"], stroke.get("opacity", 1.0))
                colors[c] += 1

        # Collect fonts
        style = node.get("style", {})
        if style.get("fontFamily"):
            fonts[style["fontFamily"]] += 1
        if style.get("fontSize"):
            font_sizes.add(int(style["fontSize"]))

        for child in node.get("children", []):
            _walk(child)

    for n in root_nodes:
        _walk(n)

    lines = [":root {"]

    # Colors — most used first, auto-name
    color_names = {}
    for i, (color, count) in enumerate(colors.most_common(30)):
        var_name = f"--color-{i + 1}"
        color_names[color] = var_name
        lines.append(f"  {var_name}: {color}; /* used {count}x */")

    # Fonts
    if fonts:
        lines.append("")
        for i, (font, count) in enumerate(fonts.most_common(10)):
            lines.append(f"  --font-{i + 1}: '{font}', sans-serif; /* used {count}x */")

    # Font sizes
    if font_sizes:
        lines.append("")
        for size in sorted(font_sizes):
            lines.append(f"  --text-{size}: {size}px;")

    lines.append("}")
    return "\n".join(lines)


def _count_children(node: dict, depth: int = 0, max_depth: int = 3) -> int:
    """Estimate total child count for a node."""
    if depth > max_depth:
        return 0
    count = 0
    for child in node.get("children", []):
        count += 1
        count += _count_children(child, depth + 1, max_depth)
    return count


def _build_overview(raw: dict, file_key: str) -> str:
    """
    Build a lightweight overview of the file structure.
    Shows pages → top-level frames with IDs, dimensions, and child counts.
    Used when no node_id is specified — helps the bot pick the right nodes.
    """
    lines = []
    file_name = raw.get("name", file_key)
    lines.append(f"# {file_name}")
    lines.append("")
    lines.append("## Pages & Frames")
    lines.append("Use the node IDs below with this same tool (node_id parameter) to get full CSS output.")
    lines.append("Pass multiple IDs comma-separated to batch: node_id=\"1:2,3:4,5:6\"")
    lines.append("")

    document = raw.get("document", {})
    for page in document.get("children", []):
        page_name = page.get("name", "Page")
        page_id = page.get("id", "")
        lines.append(f"### {page_name} [{page_id}]")

        for frame in page.get("children", []):
            frame_name = frame.get("name", "")
            frame_id = frame.get("id", "")
            frame_type = frame.get("type", "")
            bbox = frame.get("absoluteBoundingBox", {})
            w = round(bbox.get("width", 0))
            h = round(bbox.get("height", 0))
            child_count = _count_children(frame, max_depth=10)

            size_str = f"{w}x{h}" if w and h else ""
            lines.append(f"  - {frame_type} \"{frame_name}\" [{frame_id}] {size_str} ({child_count} elements)")

            # Show second-level children too for context
            for sub in frame.get("children", [])[:10]:
                sub_name = sub.get("name", "")
                sub_id = sub.get("id", "")
                sub_type = sub.get("type", "")
                sub_bbox = sub.get("absoluteBoundingBox", {})
                sw = round(sub_bbox.get("width", 0))
                sh = round(sub_bbox.get("height", 0))
                sub_children = _count_children(sub, max_depth=8)
                sub_size = f"{sw}x{sh}" if sw and sh else ""
                lines.append(f"      {sub_type} \"{sub_name}\" [{sub_id}] {sub_size} ({sub_children} elements)")

            remaining = len(frame.get("children", [])) - 10
            if remaining > 0:
                lines.append(f"      ... and {remaining} more")

        lines.append("")

    lines.append("## Next step")
    lines.append("Call this tool again with node_id set to the frame IDs you want to code.")
    lines.append("Example: figma.dev.get_page(file_key=\"...\", node_id=\"1:2,3:4\")")

    return "\n".join(lines)


async def extract_page_css(
    client: FigmaClient,
    file_key: str,
    node_id: Optional[str] = None,
    depth: Optional[int] = None,
    max_nodes: int = MAX_NODES,
    resolve_images: bool = True,
) -> str:
    """
    Main entry point. Two modes:

    1. OVERVIEW MODE (no node_id):
       Fetches file at depth=2, returns a map of all pages/frames with
       their IDs, dimensions, and child counts. The bot then picks
       which frames to code and calls again with node_id.

    2. CSS MODE (with node_id):
       Fetches specific nodes, resolves images, extracts tokens,
       returns full CSS-ready HTML tree. Supports batching multiple
       node IDs comma-separated in a single call.
    """

    # =========================================
    # MODE 1: Overview — no node_id
    # =========================================
    if not node_id:
        raw = await client.get_file(file_key=file_key, depth=depth or 2)
        return _build_overview(raw, file_key)

    # =========================================
    # MODE 2: Full CSS — with node_id(s)
    # =========================================
    ids = [n.strip() for n in node_id.split(",")]
    raw = await client.get_file_nodes(file_key=file_key, ids=ids, depth=depth)

    # Collect image refs and vector IDs
    image_refs: set = set()
    vector_ids: list = []
    root_nodes: list = []

    nodes_data = raw.get("nodes", {})
    for nid, ndata in nodes_data.items():
        doc = ndata.get("document")
        if doc:
            root_nodes.append(doc)
            _collect_assets(doc, image_refs, vector_ids)

    # Resolve image fill URLs (with delay to avoid rate limits)
    image_urls: dict = {}
    vector_urls: dict = {}

    if resolve_images:
        if image_refs:
            await asyncio.sleep(1)
            try:
                fills_resp = await client.get_image_fills(file_key)
                meta = fills_resp.get("meta", {})
                images_map = meta.get("images", {})
                image_urls.update(images_map)
            except Exception:
                pass

        # Export vectors as SVG (batch, up to limit, with delay)
        if vector_ids:
            await asyncio.sleep(1)
            try:
                batch = vector_ids[:MAX_IMAGE_EXPORTS]
                export_resp = await client.get_images(
                    file_key=file_key,
                    ids=batch,
                    format="svg",
                    scale=1.0,
                )
                vector_urls = export_resp.get("images", {})
            except Exception:
                pass

    # Build output
    output_parts = []

    # File name
    file_name = raw.get("name", file_key)
    output_parts.append(f"# {file_name}")
    output_parts.append(f"# Sections: {', '.join(ids)}")
    output_parts.append("")

    # Design tokens
    if root_nodes:
        output_parts.append("/* === DESIGN TOKENS === */")
        output_parts.append(_extract_tokens(root_nodes, image_urls))
        output_parts.append("")

    # Image & icon inventory — always show what was found
    if image_refs or vector_ids:
        output_parts.append("/* === ASSETS === */")

        if image_urls or vector_urls:
            # Resolved mode — show URLs
            for ref, url in image_urls.items():
                output_parts.append(f"/* image {ref}: {url} */")
            for vid, url in vector_urls.items():
                output_parts.append(f"/* icon {vid}: {url} */")
        else:
            # Inventory mode — list refs for the bot to decide
            output_parts.append(f"/* {len(image_refs)} background images found (not resolved): */")
            for ref in sorted(image_refs):
                output_parts.append(f"/*   image_ref: {ref} */")

            if vector_ids:
                output_parts.append(f"/* {len(vector_ids)} vector icons found: */")
                for vid in vector_ids[:20]:
                    output_parts.append(f"/*   vector node_id: {vid} */")
                if len(vector_ids) > 20:
                    output_parts.append(f"/*   ... and {len(vector_ids) - 20} more */")

            output_parts.append("/*")
            output_parts.append(" * Images were NOT fetched (saves API quota).")
            output_parts.append(" * To get image URLs: figma.images.get_fills(file_key)")
            output_parts.append(f" * To export icons as SVG: figma.images.export(file_key, ids=[...], format=\"svg\")")
            output_parts.append(" * Or re-call this tool with resolve_images=true")
            output_parts.append(" */")

        output_parts.append("")

    # Component tree
    output_parts.append("<!-- === COMPONENT TREE === -->")
    counter = _Counter(max_nodes)

    for node in root_nodes:
        lines = _render_node(node, image_urls, counter, indent=0)
        output_parts.extend(lines)

    # Stats
    output_parts.append("")
    output_parts.append(f"<!-- {counter.n} nodes processed -->")
    if counter.truncated:
        output_parts.append(
            f"<!-- WARNING: Truncated at {max_nodes} nodes. "
            f"Split into smaller sections using individual node_ids. -->"
        )

    return "\n".join(output_parts)
