"""FastAPI application factory."""

import re
from contextlib import asynccontextmanager
from pathlib import Path

from markupsafe import Markup

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates

from ai_visibility.config import settings
from ai_visibility.report.html import _score_color, _score_label
from ai_visibility.stages.scorer import get_benchmark
from ai_visibility.web.db import close_pool, init_pool


TEMPLATES_DIR = Path(__file__).parent / "templates"


def _highlight(html: str, name: str, css_class: str) -> Markup:
    """Replace name occurrences in already-rendered HTML with <mark> tags.

    Only replaces text that is NOT already inside an HTML tag attribute
    or tag body (i.e. skips content within < ... >).
    """
    import html as html_mod

    plain = str(html)
    escaped_name = html_mod.escape(name)
    mark_tag = f'<mark class="{css_class}">{escaped_name}</mark>'

    # Split on HTML tags, only replace in text segments (even indices)
    parts = re.split(r'(<[^>]+>)', plain)
    for i in range(0, len(parts), 2):  # text nodes only
        parts[i] = parts[i].replace(escaped_name, mark_tag)
    return Markup(''.join(parts))


def _render_md(text: str) -> Markup:
    """Convert basic markdown (bold, links) to HTML. Returns safe markup."""
    import html as html_mod

    text = html_mod.escape(text)
    # Bold+link: **[text](url)**
    text = re.sub(
        r"\*\*\[([^\]]+)\]\(([^)]+)\)\*\*",
        r'<a href="\2" target="_blank" class="font-semibold text-blue-600 hover:underline">\1</a>',
        text,
    )
    # Plain links: [text](url)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" target="_blank" class="text-blue-600 hover:underline">\1</a>',
        text,
    )
    # Bold: **text**
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # Italic: _text_
    text = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"<em>\1</em>", text)
    return Markup(text)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool(settings.database_url)
    yield
    close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="AI Visibility", lifespan=lifespan)

    # CORS for Next.js frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://frontend:3000",
            "https://app.visibilitydemo.quintanilha.site",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["score_color"] = _score_color
    templates.env.filters["score_label"] = _score_label
    templates.env.filters["get_benchmark"] = get_benchmark
    templates.env.filters["render_md"] = _render_md
    templates.env.filters["highlight"] = _highlight
    app.state.templates = templates

    from ai_visibility.web.routes import router

    app.include_router(router)

    from ai_visibility.web.api_routes import api_router

    app.include_router(api_router)

    return app
