#!/usr/bin/env python3
"""
Generador del sitio estático del portafolio de Raúl Pérez Chávez.

Lee el contenido del portafolio (JSON) y produce HTML estático:
    index.html            página principal
    casos/<shortId>.html  un archivo por caso de estudio
    data/content.json     copia depurada del contenido usado (reproducibilidad)

El HTML y el CSS son propios: este script NO reutiliza código, plantillas ni
hojas de estilo de uxfol.io. Solo consume el contenido del portafolio.

Uso:
    python3 build/generate.py [--source RUTA] [--out DIR]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCES = [
    ROOT.parent / "_recon" / "portfolio-data.json",
    ROOT / "data" / "content.json",
]

# Campos internos de la plataforma que no aportan contenido visible.
DROP_SECTION_KEYS = {
    "_id", "index", "deletedAt", "copyStatus", "designSettings",
    "foregroundColorSettings", "sectionImageUrl", "thumbnailData",
}

# Familias tipográficas que puede referenciar el contenido.
FONT_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Bricolage+Grotesque:wght@400;600;700&"
    "family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700;1,300;1,400;1,500;1,600;1,700&"
    "family=Lato:ital,wght@0,400;0,700;1,400&"
    "family=PT+Serif:ital,wght@0,400;0,700;1,400&"
    "family=Roboto:ital,wght@0,300;0,400;0,500;0,700;1,300;1,400;1,500;1,700&"
    "family=Sora:wght@400;500;600;700&"
    "family=Source+Sans+Pro:ital,wght@0,400;0,600;1,400&"
    "display=swap"
)


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)[:60] or "proyecto"


def clean_name(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"\s+(English|Spanish|Español)\s*$", "", value).strip()


def col_span(section: dict) -> int:
    modules = ((section.get("layoutSettings") or {}).get("modules") or [])
    for module in modules:
        grid = (module or {}).get("gridSettings") or {}
        start, end = grid.get("columnStart"), grid.get("columnEnd")
        if isinstance(start, int) and isinstance(end, int) and end > start:
            return max(1, min(12, end - start))
    return 12


def is_full_bleed(section: dict) -> bool:
    modules = ((section.get("layoutSettings") or {}).get("modules") or [])
    return any(bool((m or {}).get("gridSettings", {}).get("isFullBleed")) for m in modules)


def width_class(span: int) -> str:
    if span <= 6:
        return "container container--narrow"
    if span <= 9:
        return "container"
    return "container"


def section_attrs(section: dict) -> str:
    parts = []
    st = section.get("styleSettings") or {}
    if isinstance(st.get("paddingTop"), (int, float)):
        parts.append(f"--pt:{int(st['paddingTop'])}px")
    if isinstance(st.get("paddingBottom"), (int, float)):
        parts.append(f"--pb:{int(st['paddingBottom'])}px")
    bg = section.get("backgroundSettings") or {}
    if bg.get("usingCustomBackground") or bg.get("gradientColor1") or bg.get("backgroundColor"):
        c1 = bg.get("gradientColor1") or bg.get("backgroundColor")
        c2 = bg.get("gradientColor2") or c1
        if bg.get("selectedBackgroundStyleId") == "1" and c2 != c1:
            parts.append(f"--sec-bg:linear-gradient({c1},{c2})")
        else:
            parts.append(f"--sec-bg:{c1}")
    return f' style="{";".join(parts)}"' if parts else ""


def text_of(node) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        return node.get("text") or ""
    return ""


def text_align(node) -> str:
    if isinstance(node, dict):
        a = ((node.get("style") or {}).get("textAlign") or "").lower()
        if a in ("left", "center", "right"):
            return a
    return ""


def image_url(node) -> str:
    if not isinstance(node, dict):
        return ""
    return node.get("url") or node.get("croppedImageUrl") or ""


def is_meaningful_url(url: str) -> bool:
    return bool(url) and not url.startswith("/example_project_images/")


class Assets:
    def __init__(self, img_dir: Path, prefix: str):
        self.img_dir = img_dir
        self.prefix = prefix
        self.available = {p.name for p in img_dir.iterdir()} if img_dir.is_dir() else set()
        self.missing: set[str] = set()

    def path(self, url: str) -> str:
        if not is_meaningful_url(url):
            return ""
        if url.startswith("/"):
            return ""
        name = url.split("?")[0].rstrip("/").split("/")[-1]
        if "." not in name:
            return ""
        if name not in self.available:
            self.missing.add(name)
            return ""
        return f"{self.prefix}assets/img/{name}"


def mockup_class(media: dict) -> str:
    """Determina si la imagen va dentro de un marco de dispositivo."""
    if not isinstance(media, dict):
        return ""
    ms = media.get("mockupSettings") or {}
    device = (ms.get("deviceType") or "").lower()
    if device in ("mobile", "phone"):
        return "mockup mockup--mobile"
    if device in ("laptop", "desktop", "tablet"):
        return "mockup mockup--laptop"
    frame = media.get("frame") or ""
    if frame.startswith("mobile"):
        return "mockup mockup--mobile"
    if frame.startswith("laptop"):
        return "mockup mockup--laptop"
    return ""


def media_html(media: dict, assets: Assets) -> str:
    if not isinstance(media, dict):
        return ""
    url = image_url(media)
    caption = media.get("caption") or ""
    kind = (media.get("type") or "").lower()
    display = media.get("displayMode") or "default"
    mclass = mockup_class(media)

    if kind == "video" and url:
        if re.search(r"(youtube\.com/embed|player\.vimeo\.com)", url):
            inner = (
                f'<div class="embed"><iframe src="{html.escape(url)}" title="Vídeo" '
                'loading="lazy" allowfullscreen></iframe></div>'
            )
        else:
            inner = f'<video controls preload="metadata" src="{html.escape(url)}"></video>'
    else:
        local = assets.path(url)
        if not local:
            inner = ""
        elif mclass:
            inner = f'<div class="{mclass}"><img src="{local}" alt="" loading="lazy"></div>'
        else:
            inner = f'<img src="{local}" alt="" loading="lazy">'

    if not inner and not caption:
        return ""
    cap = f"<figcaption>{caption}</figcaption>" if caption else ""
    return f'<figure class="media media--{display}">{inner}{cap}</figure>'


def cta_html(cta) -> str:
    if not isinstance(cta, dict) or not cta.get("show") or not cta.get("title"):
        return ""
    url = cta.get("url") or "#"
    label = html.escape(str(cta["title"]))
    return f'<p><a class="button" href="{html.escape(url)}">{label}</a></p>'


def section_shell(section: dict, body: str, extra_class: str = "") -> str:
    cls = f"sec {extra_class}".strip()
    if is_full_bleed(section):
        return f'<section class="{cls}"{section_attrs(section)}>{body}</section>'
    return (
        f'<section class="{cls}"{section_attrs(section)}>'
        f'<div class="{width_class(col_span(section))}">{body}</div>'
        f"</section>"
    )


# --------------------------------------------------------------------------
# Renderizado por tipo de sección
# --------------------------------------------------------------------------


def r_header(s, a, ctx):
    node = s.get("title") or {"text": text_of(s.get("sectionTitle"))}
    align = text_align(node)
    cls = f"prose align-{align}" if align else "prose"
    return f'<div class="{cls}">{text_of(node)}</div>'


def r_text(s, a, ctx):
    node = s.get("text") or {}
    align = text_align(node)
    cls = f"prose align-{align}" if align else "prose"
    return f'<div class="{cls}">{text_of(node)}</div>'


def r_divider(s, a, ctx):
    settings = s.get("settings") or {}
    title = s.get("title") or {}
    color = settings.get("color") or "#0d0d0d"
    text = text_of(title) or text_of(s.get("sectionTitle"))
    font_color = (title.get("style") or {}).get("fontColor")
    weight = (settings.get("weight") or "weight-medium").replace("weight-", "")
    align = settings.get("text_alignment") or "left"
    style = f"background:{html.escape(color)}"
    text_style = f' style="color:{html.escape(font_color)}"' if font_color else ""

    line = f'<span class="divider__line divider__line--{weight}" style="{style}"></span>'
    if settings.get("text_position") == "no_text":
        return f'<div class="divider divider--{align}">{line}</div>'
    if not text:
        return f'<div class="divider divider--{align}">{line}</div>'
    return (
        f'<div class="divider divider--{align}">'
        f'{line}<span class="divider__text"{text_style}>{text}</span></div>'
    )


def r_media(s, a, ctx):
    return media_html(s.get("media") or {}, a)


def r_textmedia(s, a, ctx):
    settings = s.get("contentSettings") or {}
    text = text_of(s.get("text"))
    media = s.get("media") or {}
    flipped = bool(settings.get("flipped", False))
    show_text = settings.get("showText")
    show_media = settings.get("showMedia")
    if show_text is None:
        show_text = True
    if show_media is None:
        show_media = True
    align = text_align(s.get("text"))

    cls = "textmedia"
    if not flipped:
        cls += " textmedia--media-first"
    if show_media and not show_text:
        cls += " textmedia--text-only"
    if show_text and not show_media:
        cls += " textmedia--text-only"

    parts = []
    extra = cta_html(s.get("cta"))
    text_cls = f"textmedia__text prose align-{align}" if align else "textmedia__text prose"
    if show_text and (text or extra):
        parts.append(f'<div class="{text_cls}">{text}{extra}</div>')
    elif extra:
        parts.append(f'<div class="textmedia__cta">{extra}</div>')
    if show_media:
        m = media_html(media, a)
        if m:
            parts.append(f'<div class="textmedia__media">{m}</div>')
    return f'<div class="{cls}">{"".join(parts)}</div>'


def r_columns(s, a, ctx):
    cols = s.get("columns") or []
    if not cols:
        return ""
    n = max(1, min(3, len(cols)))
    items = []
    for col in cols:
        text = text_of((col or {}).get("text"))
        media = media_html((col or {}).get("media") or {}, a)
        align = text_align((col or {}).get("text"))
        cls = f"prose align-{align}" if align else "prose"
        inner = f'<div class="{cls}">{text}</div>' if text else ""
        items.append(f'<div class="columns__col">{media}{inner}</div>')
    return f'<div class="columns columns--{n}">{"".join(items)}</div>'


def r_stat(s, a, ctx):
    items = s.get("statItems") or []
    if not items:
        return ""
    out = []
    for it in items:
        data_node = (it or {}).get("data") or {}
        desc_node = (it or {}).get("description") or {}
        value = text_of(data_node)
        desc = text_of(desc_node)
        vsize = (data_node.get("style") or {}).get("fontSize")
        dsize = (desc_node.get("style") or {}).get("fontSize")
        vstyle = f' style="--stat-value:{vsize}px"' if isinstance(vsize, (int, float)) else ""
        dstyle = f' style="--stat-label:{dsize}px"' if isinstance(dsize, (int, float)) else ""
        out.append(
            f'<div class="stat"><div class="stat__value"{vstyle}>{value}</div>'
            f'<div class="stat__label"{dstyle}>{desc}</div></div>'
        )
    return f'<div class="stats stats--{min(4, len(out))}">{"".join(out)}</div>'


def r_gallery(s, a, ctx):
    items = s.get("galleryItems") or []
    cols = s.get("columns") or 2
    try:
        cols = int(cols)
    except (TypeError, ValueError):
        cols = 2
    cols = max(1, min(4, cols))
    out = []
    for it in items:
        media = (it or {}).get("media") or {}
        m = media_html(media, a)
        if m:
            out.append(f'<div class="gallery__item">{m}</div>')
    if not out:
        return ""
    return f'<div class="gallery gallery--{cols}">{"".join(out)}</div>'


def r_accordion(s, a, ctx):
    parts = []
    intro = text_of(s.get("text"))
    if intro:
        align = text_align(s.get("text"))
        cls = f"prose align-{align}" if align else "prose"
        parts.append(f'<div class="{cls}">{intro}</div>')
    m = media_html(s.get("media") or {}, a)
    if m:
        parts.append(m)
    items = s.get("accordionItems") or []
    if items:
        rows = []
        for i, it in enumerate(items):
            title = text_of((it or {}).get("title"))
            content = text_of((it or {}).get("content"))
            open_attr = " open" if i == 0 else ""
            rows.append(
                f"<details{open_attr}><summary>{title}</summary>"
                f'<div class="accordion__body prose">{content}</div></details>'
            )
        parts.append(f'<div class="accordion">{"".join(rows)}</div>')
    return "".join(parts)


def r_process(s, a, ctx):
    items = s.get("processItems") or []
    if not items:
        return ""
    rows = []
    for it in items:
        name = html.escape(str((it or {}).get("name") or ""))
        rows.append(f'<div class="process__step"><h3>{name}</h3></div>')
    return f'<div class="process">{"".join(rows)}</div>'


def r_cards(s, a, ctx):
    cards = s.get("cards") or []
    if not cards:
        return ""
    out = []
    for c in cards:
        text = text_of((c or {}).get("text"))
        out.append(f'<div class="card"><div class="prose">{text}</div></div>')
    return f'<div class="cards">{"".join(out)}</div>'


def r_logowall(s, a, ctx):
    logos = s.get("logos") or []
    imgs = []
    for logo in logos:
        local = a.path(image_url(logo))
        if local:
            imgs.append(f'<img src="{local}" alt="Logo" loading="lazy">')
    if not imgs:
        return ""
    # Carrusel continuo: se duplica la fila para el bucle de animación.
    track = "".join(imgs)
    return (
        f'<div class="logo-wall" aria-label="Logotipos">'
        f'<div class="logo-wall__track">{track}{track}</div>'
        f"</div>"
    )


def r_mainheader(s, a, ctx):
    title = text_of(s.get("title"))
    subtitle = text_of(s.get("subtitle"))
    settings = s.get("contentSettings") or {}
    media = s.get("media") or {}
    pattern = image_url(s.get("image") or {})

    # El color de fondo (amarillo #FFD65C) y el velo blanco del JSON no se
    # aplican: en el render real el hero es blanco con el patrón (marca de
    # agua) repetido sutilmente.
    style_parts = []
    local_pat = a.path(pattern)
    if local_pat:
        style_parts.append(f"--hero-pattern:url({local_pat})")
    style = f' style="{";".join(style_parts)}"' if style_parts else ""

    media_block = ""
    show_media = settings.get("showMedia")
    if show_media is None:
        show_media = True
    if show_media:
        local = a.path(image_url(media))
        if local:
            media_block = (
                f'<img class="case-hero__avatar" src="{local}" alt="" loading="lazy">'
            )

    return (
        f'<div class="case-hero"{style}><div class="container">'
        f'<div class="case-summary-grid"><div>'
        f'<div class="case-hero__title-block">{title}</div>'
        f'<div class="case-hero__role">{subtitle}</div>'
        f"</div>{media_block}</div></div></div>"
    )


def r_projectgrid(s, a, ctx):
    projects = ctx["projects"]
    cards = []
    for p in projects:
        thumb = a.path(p.get("thumbnail") or "")
        img = (
            f'<div class="project-card__thumb"><img src="{thumb}" alt="" loading="lazy"></div>'
            if thumb
            else ""
        )
        labels = "".join(
            f'<span class="pill">{html.escape(str(l))}</span>' for l in p.get("labels") or []
        )
        cards.append(
            f'<a class="project-card" href="{ctx["prefix"]}casos/{p["shortId"]}.html">'
            f'<div class="project-card__labels">{labels}</div>'
            f'<h3 class="project-card__title">{html.escape(p["name"])}</h3>'
            f'<p class="project-card__subtitle">{html.escape(p.get("subtitle") or "")}</p>'
            f"{img}</a>"
        )
    return f'<div class="project-grid">{"".join(cards)}</div>'


RENDERERS = {
    "Header": r_header,
    "Text": r_text,
    "DividerLine": r_divider,
    "Media": r_media,
    "TextAndMedia": r_textmedia,
    "Columns": r_columns,
    "Stat": r_stat,
    "Gallery": r_gallery,
    "Accordion": r_accordion,
    "Process": r_process,
    "Cards": r_cards,
    "LogoWall": r_logowall,
    "MainHeader": r_mainheader,
    "ProjectGrid": r_projectgrid,
}


def render_section(section, assets, ctx):
    stype = section.get("type") or ""
    renderer = RENDERERS.get(stype)
    if renderer is None:
        ctx["unknown"].add(stype)
        return ""
    body = renderer(section, assets, ctx)
    if not body.strip():
        return ""
    if stype == "MainHeader":
        return body
    extra = "sec--tight" if ctx.get("in_case") and stype in ("Process",) else ""
    return section_shell(section, body, extra)


# --------------------------------------------------------------------------
# Tipografía por rol
# --------------------------------------------------------------------------


def font_vars(font_styles: dict) -> str:
    """Emite variables CSS --f/<s>/<w>/<lh>/<st> por cada rol tipográfico."""
    if not font_styles:
        return ""
    lines = [":root{"]
    for role, v in font_styles.items():
        if not isinstance(v, dict):
            continue
        key = re.sub(r"[^a-zA-Z0-9]", "", role)
        family = v.get("font")
        size = v.get("size")
        weight = v.get("fontWeight")
        lh = v.get("lineHeight")
        style = v.get("fontStyle")
        if family:
            lines.append(f"--f-{key}:{family};")
        if isinstance(size, (int, float)):
            lines.append(f"--s-{key}:{size}px;")
        if weight:
            lines.append(f"--w-{key}:{weight};")
        if isinstance(lh, (int, float)):
            lines.append(f"--lh-{key}:{lh}px;")
        if style and style != "normal":
            lines.append(f"--st-{key}:{style};")
    lines.append("}")
    return "".join(lines)


# --------------------------------------------------------------------------
# Páginas
# --------------------------------------------------------------------------


def page_shell(title: str, prefix: str, body: str, description: str = "",
               font_css: str = "") -> str:
    desc = html.escape(description) if description else ""
    style = f"<style>{font_css}</style>" if font_css else ""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
{f'<meta name="description" content="{desc}">' if desc else ''}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONT_URL}" rel="stylesheet">
<link rel="stylesheet" href="{prefix}assets/css/style.css">
{style}
</head>
<body>
{body}
</body>
</html>
"""


def nav_html(pages, prefix, current="home"):
    items = []
    for pg in sorted(pages, key=lambda p: p.get("order", 0)):
        name = pg.get("name") or ""
        if not name:
            continue
        href = None
        if pg.get("type") == "home":
            href = f"{prefix}index.html"
        elif pg.get("type") in ("file", "link"):
            href = pg.get("url")
        if href:
            cur = ' aria-current="page"' if pg.get("type") == current else ""
            target = ' target="_blank" rel="noopener"' if pg.get("type") == "file" else ""
            items.append(f'<li><a href="{html.escape(href)}"{cur}{target}>{html.escape(name)}</a></li>')
        else:
            items.append(f"<li><span>{html.escape(name)}</span></li>")
    return f'<nav class="site-nav"><div class="container"><ul>{"".join(items)}</ul></div></nav>'


def footer_html(portfolio, prefix):
    footer = portfolio.get("portfolioFooter") or {}
    text = text_of(footer)
    social = portfolio.get("socialLinks") or []
    links = "".join(
        f'<a href="{html.escape(s.get("url",""))}">{html.escape(str(s.get("type","")).title())}</a>'
        for s in social
        if s.get("url")
    )
    return (
        f'<footer class="site-footer"><div class="container">'
        f'<div class="footer-grid"><div class="prose">{text}</div>'
        f'<div class="footer-links">{links}</div></div>'
        f'<p class="footer-note">Reconstrucción estática del portafolio original de '
        f'Raúl Pérez Chávez, publicada con su autorización. Contenido e imágenes: '
        f'Raúl Pérez Chávez. Sitio original: '
        f'<a href="https://uxfol.io/raul.perez.chz">uxfol.io/raul.perez.chz</a>.</p>'
        f"</div></footer>"
    )


def related_html(projects, current_short, prefix, portfolio):
    block = portfolio.get("relatedCaseStudyFooter") or {}
    title = text_of(block.get("title")) or "<h3>Más casos de estudio</h3>"
    others = [p for p in projects if p["shortId"] != current_short][:4]
    if not others:
        return ""
    cards = []
    for p in others:
        thumb = p.get("localThumb") or ""
        img = (
            f'<div class="project-card__thumb"><img src="{thumb}" alt="" loading="lazy"></div>'
            if thumb
            else ""
        )
        cards.append(
            f'<a class="project-card" href="{prefix}casos/{p["shortId"]}.html">'
            f'<h3 class="project-card__title">{html.escape(p["name"])}</h3>'
            f'<p class="project-card__subtitle">{html.escape(p.get("subtitle") or "")}</p>'
            f"{img}</a>"
        )
    return (
        f'<section class="sec sec--alt"><div class="container">'
        f'<div class="prose center">{title}</div>'
        f'<div class="project-grid">{"".join(cards)}</div>'
        f"</div></section>"
    )


# --------------------------------------------------------------------------
# Depuración del contenido
# --------------------------------------------------------------------------


def slim_background(value):
    if not isinstance(value, dict):
        return None
    out = {}
    for k in ("backgroundColor", "gradientColor1", "gradientColor2",
              "selectedBackgroundStyleId", "usingCustomBackground"):
        if value.get(k) is not None:
            out[k] = value[k]
    return out or None


def slim_overlay(value):
    if not isinstance(value, dict):
        return None
    ov = value.get("overlay")
    if isinstance(ov, dict) and isinstance(ov.get("r"), (int, float)):
        return {"overlay": {"r": ov["r"], "g": ov["g"], "b": ov["b"], "a": ov["a"]}}
    return None


def trim_section(section: dict) -> dict:
    out = {}
    for key, value in section.items():
        if key in DROP_SECTION_KEYS:
            continue
        if key == "image":
            url = (value or {}).get("url")
            if is_meaningful_url(url):
                out["image"] = {"url": url}
            continue
        if key == "accordionItems":
            out[key] = [
                {"title": i.get("title"), "content": i.get("content")}
                for i in (value or [])
            ]
            continue
        # En Columns es una lista; en Gallery es un entero (nº de columnas).
        if key == "columns" and isinstance(value, list):
            out[key] = [
                {"text": (c or {}).get("text"), "media": (c or {}).get("media")}
                for c in value
            ]
            continue
        if key == "statItems":
            out[key] = [
                {"data": (i or {}).get("data"), "description": (i or {}).get("description")}
                for i in (value or [])
            ]
            continue
        if key == "galleryItems":
            out[key] = [
                {"media": (i or {}).get("media")} for i in (value or [])
                if image_url((i or {}).get("media") or {})
            ]
            continue
        if key == "cards":
            out[key] = [{"text": (c or {}).get("text")} for c in (value or [])]
            continue
        if key == "logos":
            out[key] = [
                {"url": image_url(l), "croppedImageUrl": (l or {}).get("croppedImageUrl")}
                for l in (value or [])
                if image_url(l)
            ]
            continue
        if key == "processItems":
            out[key] = [{"name": (i or {}).get("name")} for i in (value or [])]
            continue
        if key == "backgroundSettings":
            sb = slim_background(value)
            if sb:
                out[key] = sb
            continue
        if key == "overlaySettings":
            so = slim_overlay(value)
            if so:
                out[key] = so
            continue
        if key == "moduleBackgroundSettings":
            if value:
                out[key] = value
            continue
        if key == "settings" and isinstance(value, dict) and "text_position" in value:
            out[key] = value
            continue
        out[key] = value
    return out


def find_url(obj, depth=0):
    if depth > 4:
        return None
    if isinstance(obj, str):
        return obj if obj.startswith("http") else None
    if isinstance(obj, dict):
        for key in ("url", "fileUrl", "link", "href", "value"):
            if isinstance(obj.get(key), str) and obj[key].startswith("http"):
                return obj[key]
        for value in obj.values():
            found = find_url(value, depth + 1)
            if found:
                return found
    if isinstance(obj, list):
        for value in obj:
            found = find_url(value, depth + 1)
            if found:
                return found
    return None


def prepare(raw: dict) -> dict:
    portfolio = raw.get("portfolio") or {}
    user = raw.get("user") or {}

    pages = []
    for pg in raw.get("portfolioPages") or []:
        entry = {
            "shortId": pg.get("shortId"),
            "type": pg.get("type"),
            "name": pg.get("name"),
            "order": pg.get("order", 0),
            "sections": [trim_section(s) for s in pg.get("sections") or []],
            "fontStyles": (pg.get("designSettings") or {}).get("fontStyles") or {},
        }
        if pg.get("type") in ("file", "link"):
            entry["url"] = find_url(pg.get("settings") or {}) or find_url(pg)
        pages.append(entry)

    projects = []
    for cs in raw.get("caseStudies") or []:
        projects.append(
            {
                "shortId": cs.get("shortId"),
                "order": cs.get("order", 0),
                "name": cs.get("name") or "",
                "subtitle": cs.get("subtitle") or "",
                "labels": [
                    (l.get("text") if isinstance(l, dict) else l)
                    for l in cs.get("labels") or []
                ],
                "thumbnail": image_url(cs.get("image") or {}),
                "draft": bool(cs.get("draft")),
                "sections": [trim_section(s) for s in cs.get("sections") or []],
                "fontStyles": (cs.get("designSettings") or {}).get("fontStyles") or {},
            }
        )
    projects.sort(key=lambda p: p.get("order", 0))

    return {
        "portfolio": {
            "shortId": portfolio.get("shortId"),
            "name": clean_name(portfolio.get("name")),
            "socialLinks": portfolio.get("socialLinks") or [],
            "logo": portfolio.get("logo") or {},
            "heroImage": image_url((portfolio.get("portfolioHero") or {}).get("image") or {}),
            "portfolioFooter": {
                "text": {"text": text_of(portfolio.get("portfolioFooter"))}
            },
            "relatedCaseStudyFooter": {
                "title": {
                    "text": text_of((portfolio.get("relatedCaseStudyFooter") or {}).get("title"))
                }
            },
            "user": {
                "name": user.get("name") or "",
                "image": {"url": image_url(user.get("image") or {})},
            },
        },
        "portfolioPages": pages,
        "caseStudies": projects,
    }


# --------------------------------------------------------------------------
# Programa principal
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="JSON de contenido del portafolio")
    parser.add_argument("--out", type=Path, default=ROOT, help="directorio de salida")
    parser.add_argument("--dump-content", action="store_true",
                        help="solo escribir data/content.json y salir")
    args = parser.parse_args()

    source = args.source
    if source is None:
        for candidate in DEFAULT_SOURCES:
            if candidate.is_file():
                source = candidate
                break
    if source is None or not source.is_file():
        print("ERROR: no se encontró el JSON de contenido.", file=sys.stderr)
        return 1

    raw = json.loads(source.read_text(encoding="utf-8"))
    content = prepare(raw)
    out_dir = args.out
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "content.json").write_text(
        json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"contenido depurado -> {data_dir / 'content.json'}")
    if args.dump_content:
        return 0

    img_dir = out_dir / "assets" / "img"
    assets = Assets(img_dir, prefix="")
    case_dir = out_dir / "casos"
    case_dir.mkdir(parents=True, exist_ok=True)
    assets_case = Assets(img_dir, prefix="../")

    pages = content["portfolioPages"]
    projects = content["caseStudies"]
    portfolio = content["portfolio"]

    # Resolver a local los archivos del menú (p. ej. el PDF del currículum).
    for page in pages:
        if page.get("url"):
            local = assets.path(page["url"])
            if local:
                page["url"] = local

    unknown: set[str] = set()
    unknown_case: set[str] = set()
    missing: set[str] = set()

    # --- portada -----------------------------------------------------------
    home = next((p for p in pages if p["type"] == "home"), None)
    if home is None:
        print("ERROR: no hay página home.", file=sys.stderr)
        return 1

    ctx = {"projects": projects, "prefix": "", "unknown": unknown, "in_case": False}
    body_parts = [nav_html(pages, "", current="home")]
    hero_local = assets.path(portfolio.get("heroImage") or "")
    if hero_local:
        body_parts.append(
            f'<section class="hero"><div class="container">'
            f'<img src="{hero_local}" alt="Portafolio de diseño de interacción de Raúl Pérez" '
            f'fetchpriority="high"></div></section>'
        )
    for section in home["sections"]:
        body_parts.append(render_section(section, assets, ctx))
    body_parts.append(footer_html(portfolio, ""))
    (out_dir / "index.html").write_text(
        page_shell(
            portfolio.get("name") or "Portafolio",
            "",
            "\n".join(p for p in body_parts if p),
            "Portafolio de Raúl Pérez Chávez — Senior Product & Interaction Designer.",
            font_css=font_vars(home.get("fontStyles") or {}),
        ),
        encoding="utf-8",
    )
    print("escrito -> index.html")
    missing |= assets.missing

    # --- casos de estudio --------------------------------------------------
    for project in projects:
        ctx_case = {"projects": projects, "prefix": "../", "unknown": unknown_case,
                    "in_case": True}
        avatar = assets_case.path(image_url(portfolio["user"]["image"]))
        header = (
            f'<header class="case-header"><div class="container">'
            f'<div class="case-header__inner">'
            + (f'<img class="case-header__avatar" src="{avatar}" alt="">' if avatar else "")
            + f'<div><div class="case-header__name">{html.escape(portfolio["user"]["name"])}</div>'
            f'<div class="case-header__role">Senior Product &amp; Interaction Designer</div>'
            f"</div></div></div></header>"
        )
        parts = [header]
        first_is_main = bool(project["sections"]) and project["sections"][0].get("type") == "MainHeader"
        if first_is_main:
            parts.append(render_section(project["sections"][0], assets_case, ctx_case))
            rest = project["sections"][1:]
        else:
            parts.append(
                f'<section class="sec"><div class="container"><div class="prose">'
                f'<h1>{html.escape(project["name"])}</h1>'
                f'<p class="lead">{html.escape(project["subtitle"])}</p>'
                f"</div></div></section>"
            )
            rest = project["sections"]
        for section in rest:
            parts.append(render_section(section, assets_case, ctx_case))
        parts.append(related_html(projects, project["shortId"], "../", portfolio))
        parts.append(footer_html(portfolio, "../"))
        (case_dir / f"{project['shortId']}.html").write_text(
            page_shell(
                f'{project["name"]} — Raúl Pérez Chávez',
                "../",
                "\n".join(p for p in parts if p),
                project.get("subtitle") or "",
                font_css=font_vars(project.get("fontStyles") or {}),
            ),
            encoding="utf-8",
        )
        print(f"escrito -> casos/{project['shortId']}.html")
    missing |= assets_case.missing

    print()
    print(f"proyectos: {len(projects)}")
    if unknown:
        print(f"AVISO tipos sin renderizador (home): {sorted(unknown)}")
    if unknown_case:
        print(f"AVISO tipos sin renderizador (casos): {sorted(unknown_case)}")
    if missing:
        print(f"AVISO imágenes no encontradas localmente: {len(missing)}")
        for name in sorted(missing)[:10]:
            print(f"   - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
