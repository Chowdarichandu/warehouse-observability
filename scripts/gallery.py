"""Package original Playwright screenshots without modifying their image data."""

import html
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/screenshots"
SCREENS = [
    (
        "overview",
        "Pipeline overview",
        "Workspace health, pipeline performance, and live activity.",
    ),
    (
        "tenants",
        "Tenants",
        "Tenant health, pipeline states, freshness, and service levels.",
    ),
    (
        "tenant-detail",
        "Tenant investigation",
        "Workflow status, source history, metrics, and maintenance.",
    ),
    (
        "orchestration",
        "Pipeline orchestration",
        "DAG catalog, dependencies, and gated workflow actions.",
    ),
    ("runs", "Pipeline runs", "Filtered run explorer with pagination and CSV export."),
    (
        "run-detail",
        "Run investigation",
        "Classified errors, recommendations, and redacted logs.",
    ),
    ("dependencies", "Pipeline dependencies", "Observed links and downstream impact."),
    ("quality", "Data quality", "Checks, evidence, and result history."),
    (
        "warehouse",
        "Warehouse catalog",
        "Table freshness, volume, schema history, and health.",
    ),
    (
        "activity",
        "Administration activity",
        "Recent workspace actions and account changes.",
    ),
    (
        "comparison",
        "Run comparison",
        "Side-by-side run metrics and stream differences.",
    ),
    (
        "errors",
        "Error intelligence",
        "Root-cause groups, failure heatmap, and recovery metrics.",
    ),
    (
        "freshness",
        "Freshness and volume",
        "Source SLAs, volume changes, and schema drift.",
    ),
    ("alerts", "Alerts", "Alert lifecycle, notification channels, and rules."),
    ("incidents", "Incidents", "Grouped alerts, notes, assignment, and resolution."),
    (
        "onboarding",
        "Onboarding",
        "Tenant setup, source validation, and initial workflow.",
    ),
    ("platform", "Platform", "Airflow, Airbyte, collectors, and database health."),
    ("access", "Access and roles", "Effective permissions, role guide, and sessions."),
    ("account", "Account settings", "Profile and secure password change."),
    ("dev-mailbox", "Dev mailbox", "Captured password reset and invite messages."),
    ("admin", "Administration", "Users, access, operations, and audit history."),
    (
        "admin-roles",
        "Role administration",
        "Custom roles and the built-in access matrix.",
    ),
    (
        "admin-operations",
        "Operations and delivery",
        "Durable actions and notification deliveries.",
    ),
    (
        "admin-activity",
        "Administration activity",
        "Recent identity and configuration actions.",
    ),
    ("admin-audit", "Audit history", "Recorded access and configuration changes."),
    ("search", "Global search", "Search over tenants, errors, and redacted logs."),
    ("styleguide", "Design system", "Pravah tokens and component states."),
    ("tv-mode", "TV mode", "Overview for a shared workspace display."),
    (
        "metrics-only",
        "Metrics-only access",
        "Aggregate data shown to a least-privilege role.",
    ),
    ("login", "Sign in", "Pravah sign-in at desktop and mobile sizes."),
]
VARIANTS = [
    ("light", 1440, "Light · 1440 px"),
    ("dark", 1440, "Dark · 1440 px"),
    ("light", 390, "Light · 390 px"),
    ("dark", 390, "Dark · 390 px"),
]


def main() -> None:
    cards = []
    expected: set[str] = set()
    for slug, title, description in SCREENS:
        previews = []
        for theme, width, label in VARIANTS:
            filename = f"{slug}-{theme}-{width}.png"
            path = DIRECTORY / filename
            if not path.exists():
                raise FileNotFoundError(path)
            expected.add(filename)
            previews.append(
                f'<a class="variant" href="{filename}" target="_blank" rel="noopener">'
                f'<img src="{filename}" alt="{html.escape(title)} · {html.escape(label)}" loading="lazy">'
                f"<span>{html.escape(label)}</span></a>"
            )
        cards.append(
            f'<article class="card"><header><h2>{html.escape(title)}</h2>'
            f'<p>{html.escape(description)}</p></header><div class="variants">'
            f"{''.join(previews)}</div></article>"
        )
    for image in DIRECTORY.glob("*.png"):
        if image.name not in expected:
            image.unlink()
    document = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pravah — Screen gallery</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f3f5f4;color:#13201d;font-family:system-ui,-apple-system,sans-serif}
main{max-width:1600px;margin:auto;padding:40px 28px}h1{font-size:34px;letter-spacing:-1px;margin:0 0 10px}
.intro{max-width:760px;color:#5c6a66;font-size:14px;line-height:1.6;margin-bottom:26px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.card{border:1px solid #dde3e0;border-radius:10px;background:white;padding:18px;box-shadow:0 2px 10px #13201d08}
.card h2{font-size:16px;margin:0 0 5px}.card header p{font-size:12px;color:#5c6a66;margin:0 0 14px;line-height:1.5}
.variants{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px}.variant{color:inherit;text-decoration:none;min-width:0}
.variant img{display:block;width:100%;height:125px;object-fit:cover;object-position:top;border:1px solid #dde3e0;border-radius:5px;background:#eef2f0}
.variant span{display:block;margin-top:6px;font-size:10px;color:#465450}.variant:focus-visible{outline:3px solid #0b6b75;outline-offset:3px}
footer{font-size:11px;color:#5c6a66;border-top:1px solid #dde3e0;margin-top:28px;padding-top:16px}
@media(max-width:900px){main{padding:24px 16px}.grid{grid-template-columns:1fr}.variant img{height:110px}}@media(max-width:480px){.variants{grid-template-columns:repeat(2,minmax(0,1fr))}.variant img{height:140px}h1{font-size:28px}}
</style></head><body><main><h1>Pravah screen gallery</h1>
<p class="intro">Every screen is captured with seeded demo data in light and dark themes at 1440 px and 390 px. Select a preview to open its full-resolution capture.</p>
<div class="grid">"""
    document += "\n".join(cards)
    document += """</div><footer>All tenant names and data are fictional. Demo actions use local simulated data.</footer></main></body></html>"""
    (DIRECTORY / "index.html").write_text(document)

    markdown = (
        "# Pravah screen captures\n\n"
        "Each screen has four fresh captures: light and dark at 1440 px and 390 px. "
        "All tenant names and data are fictional.\n"
    )
    for slug, title, description in SCREENS:
        markdown += f"\n## {title}\n\n{description}\n\n"
        for theme, width, label in VARIANTS:
            filename = f"{slug}-{theme}-{width}.png"
            markdown += (
                f"**{label}**\n\n[![{title} · {label}]({filename})]({filename})\n\n"
            )
    (DIRECTORY / "README.md").write_text(markdown)
    archive = ROOT / "output/console-screens.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
        bundle.write(DIRECTORY / "index.html", "index.html")
        bundle.write(DIRECTORY / "README.md", "README.md")
        for slug, _, _ in SCREENS:
            for theme, width, _ in VARIANTS:
                filename = f"{slug}-{theme}-{width}.png"
                bundle.write(DIRECTORY / filename, filename)
    print(
        json.dumps(
            {
                "screens": len(SCREENS),
                "variants_per_screen": len(VARIANTS),
                "gallery": str(DIRECTORY / "index.html"),
                "archive": str(archive),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
