#!/usr/bin/env python3
"""
Złożenie instrukcji z docs/manual/*.md w jeden plik PDF.

Wymaga: Pandoc (https://pandoc.org) oraz silnika PDF (np. MiKTeX / TeX Live z xelatex —
zalecane dla polskich znaków).

Uruchom z korzenia repozytorium:
    python scripts/build_manual_pdf.py

Wynik: docs/manual/_build/Cogitomedica-Instrukcje.pdf (tymczasowe pliki w _build/).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "docs" / "manual"
BUILD = MANUAL / "_build"

# Kolejność rozdziałów (bez screenshot-checklist — lista techniczna).
# Po §04-administrator wstawione: procedura papieru + diagram, potem pacjent.
CHAPTERS: tuple[str, ...] = (
    "00-przeglad.md",
    "01-rejestracja.md",
    "02-tablet.md",
    "03-doktor.md",
    "04-administrator.md",
    "04-administrator-paper-intake.md",
    "paper_intake_flow.md",
    "05-pacjent-wyniki.md",
)

# Ścieżki obrazów w MD są pod edytor (od root repo: /docs/manual/...).
# Pandoc potrzebuje ścieżek względem --resource-path (ROOT).
IMG_PREFIX_REPO = "](/docs/manual/assets/screenshots/"
IMG_PREFIX_PANDOC = "](docs/manual/assets/screenshots/"

PAGE_BREAK = "\n\n```{=latex}\n\\newpage\n```\n\n"


def _merge_chapters() -> str:
    parts: list[str] = []
    for name in CHAPTERS:
        path = MANUAL / name
        if not path.is_file():
            raise FileNotFoundError(f"Brak pliku: {path}")
        text = path.read_text(encoding="utf-8")
        text = text.replace(IMG_PREFIX_REPO, IMG_PREFIX_PANDOC)
        parts.append(text.rstrip())
    return PAGE_BREAK.join(parts)


def _find_pandoc() -> str:
    exe = shutil.which("pandoc")
    if not exe:
        sys.stderr.write(
            "Nie znaleziono `pandoc` w PATH. Zainstaluj Pandoc: https://pandoc.org/installing.html\n"
        )
        sys.exit(1)
    return exe


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Buduje jeden PDF z rozdziałów docs/manual/."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=BUILD / "Cogitomedica-Instrukcje.pdf",
        help="Ścieżka pliku PDF (domyślnie docs/manual/_build/Cogitomedica-Instrukcje.pdf)",
    )
    parser.add_argument(
        "--pdf-engine",
        default="xelatex",
        help="Silnik PDF dla Pandoc (domyślnie: xelatex; alternatywy: pdflatex, lualatex)",
    )
    args = parser.parse_args()

    merged = _merge_chapters()
    BUILD.mkdir(parents=True, exist_ok=True)
    combined = BUILD / "_combined.md"
    combined.write_text(merged, encoding="utf-8")

    pandoc = _find_pandoc()
    cmd = [
        pandoc,
        str(combined),
        "-o",
        str(args.output),
        "--from",
        "markdown+smart",
        "--resource-path",
        str(ROOT),
        "--toc",
        "--toc-depth",
        "3",
        "--pdf-engine",
        args.pdf_engine,
        "-V",
        "lang=pl",
        "-V",
        "geometry:margin=2.5cm",
    ]
    print(" ", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, cwd=str(ROOT))
    except subprocess.CalledProcessError as e:
        sys.stderr.write(
            "\nPandoc zakończył się błędem. Upewnij się, że masz zainstalowany LaTeX "
            f"(np. xelatex z TeX Live / MiKTeX). Próbowany silnik: {args.pdf_engine}.\n"
        )
        raise SystemExit(e.returncode) from e

    print(f"Zapisano: {args.output.resolve()}")


if __name__ == "__main__":
    main()
