"""
Nagrywa film instruktażowy: „Po imporcie widać tylko jednego pacjenta”.

Scenariusz odpowiada zgłoszeniu klienta — weryfikacja kolejki, historii importu
oraz ręczne dopisanie brakującego pacjenta do kolejki na dziś.

Usage:
  python scripts/record_import_troubleshooting_video.py --base-url http://127.0.0.1:8000

Na hoście Windows (bez WeasyPrint): seed w Dockerze, potem nagranie bez Django:
  docker compose exec web python scripts/manual_demo/seed_import_troubleshooting.py
  $env:SCREENSHOT_SKIP_DJANGO='1'
  python scripts/record_import_troubleshooting_video.py --base-url http://127.0.0.1:8000 --slow-mo 500
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.manual_demo import login_reception, setup_django
from scripts.manual_demo.cursor_overlay import (
    ensure_cursor_alive,
    human_click,
    human_fill,
    human_hover,
    human_select_option,
    install_cursor,
)
from scripts.manual_demo.seed_import_troubleshooting import (
    seed_import_troubleshooting_demo,
)

DEFAULT_OUT = REPO_ROOT / "docs" / "manual" / "assets" / "videos" / "reception"
DEFAULT_CTX = (
    REPO_ROOT / "docs" / "manual" / "_build" / "import-troubleshooting-ctx.json"
)


def _pause(page, ms: int = 1200) -> None:
    page.wait_for_timeout(ms)


def _expand_queue_details(page) -> None:
    summary = page.locator("details summary").first
    if summary.count():
        human_click(page, summary, pause_after_ms=600)


def record_import_troubleshooting_video(
    base: str,
    ctx: dict,
    out_dir: Path,
    *,
    slow_mo: int = 500,
    width: int = 1280,
    height: int = 720,
) -> Path | None:
    from playwright.sync_api import sync_playwright

    pwd = ctx["password"]
    folder = out_dir
    folder.mkdir(parents=True, exist_ok=True)
    for p in folder.glob("import-troubleshooting*.webm"):
        p.unlink(missing_ok=True)

    queue_date = ctx["queue_date"]
    batch_id = ctx["import_batch_id"]
    missing_last = ctx["patient_missing_last_name"]
    queue_id = ctx.get("queue_id") or str(ctx["queue"].id)
    missing_patient_id = ctx["patient_missing_id"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=slow_mo)
        context = browser.new_context(
            viewport={"width": width, "height": height},
            record_video_dir=str(folder),
            record_video_size={"width": width, "height": height},
        )
        page = context.new_page()
        install_cursor(page)

        # 1. Logowanie
        login_reception(page, base, pwd)
        _pause(page, 800)

        # 2. Master-detail — tylko jeden pacjent na dziś
        page.goto(
            f"{base}/admin/reception/dailyqueue/master-detail/?queue_date={queue_date}",
            wait_until="networkidle",
        )
        ensure_cursor_alive(page)
        _pause(page, 1800)
        _expand_queue_details(page)
        _pause(page, 2200)

        # 3. Dashboard recepcji — ostatni import (1 dodany)
        page.goto(f"{base}/admin/reception-dashboard/", wait_until="networkidle")
        ensure_cursor_alive(page)
        _pause(page, 2200)

        # 4. Szczegóły ostatniego importu — total_rows = 1
        page.goto(
            f"{base}/admin/reception/patientimportbatch/{batch_id}/change/",
            wait_until="networkidle",
        )
        ensure_cursor_alive(page)
        _pause(page, 2500)

        # 5. Lista importów
        page.goto(
            f"{base}/admin/reception/patientimportbatch/",
            wait_until="networkidle",
        )
        ensure_cursor_alive(page)
        _pause(page, 1500)

        # 6. Pacjent istnieje w systemie, ale nie ma go w kolejce
        page.goto(f"{base}/admin/reception/patient/", wait_until="networkidle")
        ensure_cursor_alive(page)
        search = page.locator("#searchbar")
        human_fill(page, search, missing_last)
        search.press("Enter")
        page.wait_for_load_state("networkidle")
        _pause(page, 2000)

        # 7. Ręczne dodanie wpisu do kolejki
        add_url = f"{base}/admin/reception/queueentry/add/"
        page.goto(add_url, wait_until="networkidle")
        ensure_cursor_alive(page)
        _pause(page, 800)
        human_select_option(page, page.locator('select[name="daily_queue"]'), queue_id)
        human_select_option(
            page, page.locator('select[name="patient"]'), missing_patient_id
        )
        human_select_option(
            page, page.locator('select[name="entry_status"]'), "WAITING"
        )
        human_fill(page, page.locator('input[name="position_no"]'), "2")
        _pause(page, 1000)
        human_click(page, page.locator('[name="_save"]').first, wait_network=True)
        _pause(page, 1500)

        # 8. Weryfikacja — dwóch pacjentów w kolejce
        page.goto(
            f"{base}/admin/reception/dailyqueue/master-detail/?queue_date={queue_date}",
            wait_until="networkidle",
        )
        ensure_cursor_alive(page)
        _expand_queue_details(page)
        _pause(page, 2500)

        # 9. Wpisy kolejki (lista filtrowana)
        page.goto(
            f"{base}/admin/reception/queueentry/?daily_queue__id__exact={queue_id}",
            wait_until="networkidle",
        )
        ensure_cursor_alive(page)
        human_hover(page, page.locator("table").first, pause_ms=900)
        _pause(page, 2000)

        context.close()
        browser.close()

    webms = list(folder.glob("*.webm"))
    if not webms:
        return None
    target = folder / "import-troubleshooting.webm"
    latest = max(webms, key=lambda p: p.stat().st_mtime)
    if target.exists() and target.resolve() != latest.resolve():
        target.unlink(missing_ok=True)
    if latest != target:
        latest.rename(target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Nagrywa WebM: brakujący pacjent po imporcie XLSX."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SCREENSHOT_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--slow-mo", type=int, default=500)
    parser.add_argument("--video-width", type=int, default=1280)
    parser.add_argument("--video-height", type=int, default=720)
    parser.add_argument(
        "--ctx-file",
        type=Path,
        default=DEFAULT_CTX,
        help="JSON z ID demo (tryb bez Django na hoście)",
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    skip_django = os.environ.get("SCREENSHOT_SKIP_DJANGO", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        print(
            "Install: pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return 1

    ctx: dict
    if skip_django:
        ctx_path = args.ctx_file.resolve()
        if not ctx_path.is_file():
            print(
                f"Brak {ctx_path} — uruchom seed w Dockerze:\n"
                "  docker compose exec web python scripts/manual_demo/seed_import_troubleshooting.py",
                file=sys.stderr,
            )
            return 1
        ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
    else:
        setup_django()
        ctx = {}
        seed_import_troubleshooting_demo(ctx)

    path = record_import_troubleshooting_video(
        base,
        ctx,
        args.out_dir.resolve(),
        slow_mo=args.slow_mo,
        width=args.video_width,
        height=args.video_height,
    )
    if path:
        print(f"OK: {path}")
        return 0
    print("ERROR: brak pliku .webm", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
