#!/usr/bin/env python3
"""Render SPEC.md into the static site at web/index.html.

SPEC.md mirrors the live Claude Doc "Agent Containment Toolkit — Pitch & Spec"
(https://claude.ai/artifact/BSX9u1fwmS66CQSKqMwTku). Re-export it into SPEC.md
when the doc changes, then run this script (deploy.sh does it for you).
"""
import html
import re
import struct
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "SPEC.md"
OUT = ROOT / "web" / "index.html"
DOC_URL = "https://claude.ai/artifact/BSX9u1fwmS66CQSKqMwTku"
REPO_URL = "https://github.com/Lib13Inc/kavach"


def _sized_img(m: re.Match) -> str:
    # Width/height from the PNG header so the page doesn't shift (and break #anchors) as images load.
    w, h = struct.unpack(">II", (ROOT / "web" / m.group(2)).read_bytes()[16:24])
    return f'<img {m.group(1)}src="{m.group(2)}" width="{w}" height="{h}" loading="lazy" />'


def render(md_text: str) -> tuple[str, str, str]:
    # Title comes from the first H1; drop it (the header renders it) and the repo-local note under it.
    title = re.search(r"^# (.+)$", md_text, re.M).group(1).strip()
    body = re.sub(r"^# .+\n", "", md_text, count=1)
    body = re.sub(r"^> Hackathon starter code.*\n", "", body, flags=re.M)
    body = body.replace("](docs/", "](assets/")

    md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists", "toc"],
                           extension_configs={"toc": {"toc_depth": "2"}})
    content = md.convert(body)
    # GitHub-style task lists.
    content = re.sub(r"<li>\[ \]\s*", '<li class="task"><input type="checkbox" disabled> ', content)
    content = re.sub(r"<li>\[[xX]\]\s*", '<li class="task"><input type="checkbox" checked disabled> ', content)
    content = content.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
    content = re.sub(r'<a href="(https?://[^"]+)"', r'<a href="\1" rel="noopener"', content)
    content = re.sub(r'<img ([^>]*)src="(assets/[^"]+\.png)" />', _sized_img, content)
    return title, md.toc, content


def main() -> None:
    title, toc, content = render(SPEC.read_text(encoding="utf-8"))
    page = TEMPLATE.format(title=html.escape(title), toc=toc, content=content,
                           doc_url=DOC_URL, repo_url=REPO_URL)
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(page):,} bytes)")


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kavach — Agent Containment Toolkit</title>
<meta name="description" content="Kavach wraps any AI agent in a sandbox, policy gateway, secrets vault, eval harness and goal tracker — from one config file and one command.">
<meta property="og:title" content="Kavach — Agent Containment Toolkit">
<meta property="og:description" content="Pitch and spec for a drop-in containment runtime for customer-facing AI agents.">
<meta property="og:url" content="https://kavach.lib13.com/">
<meta property="og:image" content="https://kavach.lib13.com/assets/architecture.png">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Cpath d='M16 2 4 7v8c0 7.5 5.1 13.4 12 15 6.9-1.6 12-7.5 12-15V7z' fill='%23c2410c'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --bg: #fbfaf7; --surface: #ffffff; --text: #1c1917; --muted: #57534e; --border: #e7e5e4;
  --accent: #c2410c; --accent-soft: #fff1e8; --code-bg: #f5f5f4; --row: #fafaf9;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #12110f; --surface: #1c1a17; --text: #ece9e4; --muted: #a8a29e; --border: #2e2b27;
    --accent: #fb923c; --accent-soft: #2a1a10; --code-bg: #1f1d1a; --row: #181614;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #12110f; --surface: #1c1a17; --text: #ece9e4; --muted: #a8a29e; --border: #2e2b27;
  --accent: #fb923c; --accent-soft: #2a1a10; --code-bg: #1f1d1a; --row: #181614;
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; scroll-padding-top: 16px; }}
body {{ margin: 0; background: var(--bg); color: var(--text);
  font: 16px/1.65 Inter, system-ui, -apple-system, sans-serif; -webkit-font-smoothing: antialiased; }}
a {{ color: var(--accent); text-underline-offset: 2px; }}
.hero {{ border-bottom: 1px solid var(--border); background: var(--surface); }}
.hero-inner {{ max-width: 1120px; margin: 0 auto; padding: 56px 16px 40px; }}
.eyebrow {{ display: inline-flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600;
  letter-spacing: .08em; text-transform: uppercase; color: var(--accent); }}
.hero h1 {{ font-size: clamp(30px, 5vw, 48px); line-height: 1.1; letter-spacing: -.02em; margin: 12px 0 16px; }}
.hero p {{ max-width: 680px; color: var(--muted); font-size: 18px; margin: 0 0 24px; }}
.actions {{ display: flex; flex-wrap: wrap; gap: 12px; }}
.btn {{ display: inline-block; padding: 10px 16px; border-radius: 8px; font-weight: 600; font-size: 15px;
  text-decoration: none; border: 1px solid var(--border); color: var(--text); background: var(--bg); }}
.btn.primary {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
.layout {{ max-width: 1120px; margin: 0 auto; padding: 32px 16px 80px; display: grid;
  grid-template-columns: 220px minmax(0, 1fr); gap: 48px; }}
nav.toc {{ position: sticky; top: 24px; align-self: start; font-size: 14px; }}
nav.toc .label {{ font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-bottom: 8px; }}
nav.toc ul {{ list-style: none; margin: 0; padding: 0; }}
nav.toc li {{ margin: 0; }}
nav.toc a {{ display: block; padding: 5px 0 5px 12px; border-left: 2px solid var(--border); color: var(--muted); text-decoration: none; }}
nav.toc a:hover {{ color: var(--text); border-left-color: var(--accent); }}
article {{ min-width: 0; max-width: 760px; }}
article h2 {{ font-size: 28px; letter-spacing: -.01em; line-height: 1.25; margin: 56px 0 16px; padding-top: 24px; border-top: 1px solid var(--border); }}
article h2:first-child {{ margin-top: 0; padding-top: 0; border-top: 0; }}
article h3 {{ font-size: 20px; margin: 36px 0 12px; }}
article p, article ul, article ol {{ margin: 0 0 16px; }}
article li {{ margin: 4px 0; }}
article li.task {{ list-style: none; margin-left: -22px; }}
article img {{ display: block; max-width: 100%; height: auto; margin: 8px 0 16px; border-radius: 10px;
  border: 1px solid var(--border); background: #fff; padding: 8px; }}
code {{ font: 0.88em/1.5 "JetBrains Mono", ui-monospace, monospace; background: var(--code-bg); padding: 2px 5px; border-radius: 4px; }}
pre {{ background: var(--code-bg); border: 1px solid var(--border); border-radius: 10px; padding: 16px; overflow-x: auto; margin: 0 0 20px; }}
pre code {{ background: none; padding: 0; font-size: 13.5px; }}
.table-wrap {{ overflow-x: auto; margin: 0 0 24px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }}
table {{ border-collapse: collapse; width: 100%; font-size: 14.5px; }}
th, td {{ text-align: left; vertical-align: top; padding: 10px 14px; border-bottom: 1px solid var(--border); }}
th {{ font-weight: 600; background: var(--row); white-space: nowrap; }}
tr:last-child td {{ border-bottom: 0; }}
footer {{ border-top: 1px solid var(--border); color: var(--muted); font-size: 14px; }}
footer .inner {{ max-width: 1120px; margin: 0 auto; padding: 24px 16px; display: flex; flex-wrap: wrap; gap: 8px 24px; justify-content: space-between; }}
@media (max-width: 860px) {{
  .layout {{ grid-template-columns: 1fr; gap: 24px; }}
  nav.toc {{ position: static; }}
  .hero-inner {{ padding-top: 40px; }}
}}
</style>
</head>
<body>
<header class="hero">
  <div class="hero-inner">
    <span class="eyebrow">Kavach · Pitch &amp; Spec</span>
    <h1>{title}</h1>
    <p>A drop-in runtime that wraps any agent in a sandbox, a policy gateway, a secrets vault, an eval harness and a goal tracker. You get all five from one config file and one command.</p>
    <div class="actions">
      <a class="btn primary" href="{repo_url}" rel="noopener">View on GitHub</a>
      <a class="btn" href="{doc_url}" rel="noopener">Open the live doc</a>
    </div>
  </div>
</header>
<div class="layout">
  <nav class="toc" aria-label="Contents"><div class="label">Contents</div>{toc}</nav>
  <article>
{content}
  </article>
</div>
<footer><div class="inner"><span>Kavach · Lib13</span><a href="{repo_url}" rel="noopener">github.com/Lib13Inc/kavach</a></div></footer>
</body>
</html>
"""

if __name__ == "__main__":
    main()
