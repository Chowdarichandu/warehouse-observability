"""Package original Playwright screenshots without modifying their image data."""

import html
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "output/screenshots"
SCREENS = [
    (
        "overview",
        "Pipeline overview",
        "Tenant health, KPIs, durations, failures, and live activity.",
    ),
    (
        "tenants",
        "Tenants",
        "Client health, pipeline states, freshness, and service levels.",
    ),
    (
        "tenant-detail",
        "Tenant investigation",
        "Acme's CDC incident, timeline, metrics, and configuration.",
    ),
    ("runs", "Pipeline runs", "Filtered run explorer with pagination and CSV export."),
    (
        "run-detail",
        "Run investigation",
        "Classified error, recommended fix, and redacted log.",
    ),
    (
        "errors",
        "Error intelligence",
        "Root-cause groups, failure heatmap, and recovery metrics.",
    ),
    (
        "freshness",
        "Freshness & volume",
        "Source SLAs, Orbit's volume drop, and schema drift.",
    ),
    (
        "dependencies",
        "Pipeline dependencies",
        "Configured routes, observed execution links, and potential downstream impact.",
    ),
    (
        "quality",
        "Data quality",
        "Sample-based checks, aggregate evidence, and result history.",
    ),
    (
        "activity",
        "Activity",
        "A chronological view of run, alert, onboarding, action, and quality events.",
    ),
    (
        "comparison",
        "Run comparison",
        "Side-by-side run metrics and per-stream record differences.",
    ),
    (
        "orchestration",
        "Pipeline orchestration",
        "Seven configured DAGs and their source branches.",
    ),
    (
        "access",
        "Access & roles",
        "Effective permissions, role guide, and account management.",
    ),
    ("account", "Account settings", "Sign-in settings and secure password change."),
    ("alerts", "Alerts", "Alert lifecycle, notification channels, and built-in rules."),
    ("onboarding", "Onboarding", "The guided setup flow and CDC pre-flight checks."),
    (
        "platform",
        "Platform",
        "Component history, Airflow pools, collectors, and database health.",
    ),
    (
        "admin",
        "Administration",
        "Users, roles, operation outcomes, notification deliveries, and audit history.",
    ),
    (
        "search",
        "Global search",
        "Full-text search over classified errors and redacted logs.",
    ),
    ("tv-mode", "TV mode", "Overview without navigation, for a shared office screen."),
    ("overview-dark", "Dark theme", "The overview in dark mode."),
    ("mobile", "Mobile", "Tenant health and service levels on a narrow viewport."),
    ("login", "Sign in", "Local demo accounts with Viewer, Operator, and Admin roles."),
]


def main() -> None:
    cards = []
    for slug, title, description in SCREENS:
        path = DIRECTORY / f"{slug}.png"
        if not path.exists():
            raise FileNotFoundError(path)
        cards.append(
            f'<a class="card" href="{slug}.png" target="_blank" rel="noopener">'
            f'<div class="preview"><img src="{slug}.png" alt="{html.escape(title)}" loading="lazy"></div>'
            f'<div class="copy"><h2>{html.escape(title)} <span>↗</span></h2>'
            f"<p>{html.escape(description)}</p></div></a>"
        )
    document = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pravah — Screen gallery</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f7f9;color:#213447;font-family:system-ui,-apple-system,sans-serif}
main{max-width:1450px;margin:auto;padding:48px 32px}header{margin-bottom:34px}.label{font-size:11px;letter-spacing:1.8px;color:#16836b;font-weight:700}
h1{font-size:36px;letter-spacing:-1.3px;margin:14px 0 12px}header p{color:#718494;max-width:760px;font-size:14px;line-height:1.7}
.status{display:inline-block;border:1px solid #c7e0d5;color:#258567;background:#ebf5ee;border-radius:5px;font-size:11px;padding:7px 10px;margin:10px 0}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px}.card{display:block;border:1px solid #dfe7ed;border-radius:10px;background:white;overflow:hidden;color:inherit;text-decoration:none;box-shadow:0 4px 15px #21344706}
.card:hover{border-color:#73b69f;box-shadow:0 6px 25px #21344710}.card:focus-visible{outline:3px solid #16836b;outline-offset:4px}
.preview{height:240px;overflow:hidden;background:#e7edf1;border-bottom:1px solid #e4ebf0}.preview img{width:100%;display:block;min-height:100%;object-fit:cover;object-position:top}
.copy{padding:20px}h2{font-size:16px;letter-spacing:-.2px;margin:0 0 10px}h2 span{float:right;color:#7f9aab}.copy p{font-size:12px;line-height:1.7;color:#81909d;margin:0}
footer{font-size:11px;color:#81909d;border-top:1px solid #dfe7ed;margin-top:35px;padding-top:20px;line-height:1.7}
@media(max-width:1050px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:640px){main{padding:30px 18px}h1{font-size:28px}.grid{grid-template-columns:1fr}.preview{height:260px}}
</style></head><body><main><header><div class="label">WAREHOUSE OBSERVABILITY · SCREEN GALLERY</div>
<h1>Every screen, at a glance.</h1><p>Original screenshots captured from the running offline demo with Playwright. Select a screen to open its full-resolution image.</p>
<div class="status">Offline walkthrough verified · EC2/EKS deployment candidate</div></header><div class="grid">"""
    document += "\n".join(cards)
    document += """</div><footer>All tenants and data are fictional. Retry, onboarding, and notification actions are simulated.
Live integration, OIDC, and deployment code is included in the repository; AWS staging acceptance remains pending. These screens show offline demo data. Images preserve the original Playwright captures.</footer></main></body></html>"""
    (DIRECTORY / "index.html").write_text(document)
    markdown = "# Pravah screens\n\nOriginal Playwright captures of the offline demo. Live integration and EC2/EKS deployment code is included; real staging acceptance remains pending.\n\n"
    markdown += "\n\n".join(
        f"## {title}\n\n{description}\n\n[![{title}]({slug}.png)]({slug}.png)"
        for slug, title, description in SCREENS
    )
    (DIRECTORY / "README.md").write_text(markdown + "\n")
    archive = ROOT / "output/console-screens.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
        bundle.write(DIRECTORY / "index.html", "index.html")
        bundle.write(DIRECTORY / "README.md", "README.md")
        for slug, _, _ in SCREENS:
            bundle.write(DIRECTORY / f"{slug}.png", f"{slug}.png")
        bundle.write(ROOT / "output/verification.json", "verification.json")
    print(
        json.dumps(
            {
                "screens": len(SCREENS),
                "gallery": str(DIRECTORY / "index.html"),
                "archive": str(archive),
            }
        )
    )


if __name__ == "__main__":
    main()
