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
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "docs" / "manual"
BUILD = MANUAL / "_build"

# Kolejność rozdziałów (bez screenshot-checklist — lista techniczna).
# Po §04-administrator: procedura papieru + diagram; na końcu FAQ (scenariusze).
CHAPTERS: tuple[str, ...] = (
    "00-przeglad.md",
    "01-rejestracja.md",
    "06-zmiana-danych-pacjenta.md",
    "02-tablet.md",
    "03-doktor.md",
    "04-administrator.md",
    "04-administrator-paper-intake.md",
    "paper_intake_flow.md",
    "07-wgranie-zewnetrznego-badania.md",
    "08-ksiegowosc-raport.md",
    "05-pacjent-wyniki.md",
    "scenariusze.md",
)

# Ścieżki obrazów w MD są pod edytor (od root repo: /docs/manual/...).
# Pandoc potrzebuje ścieżek względem --resource-path (ROOT).
IMG_PREFIX_REPO = "](/docs/manual/assets/screenshots/"
IMG_PREFIX_PANDOC = "](docs/manual/assets/screenshots/"

PAGE_BREAK = "\n\n```{=latex}\n\\newpage\n```\n\n"

# Znaki spoza Latin Modern (domyślna czcionka xelatex) — zamiana ASCII.
_UNICODE_SAFE = str.maketrans(
    {
        "\u2032": "'",  # ′ (prime, np. T1′)
        "\u2264": "<=",  # ≤
        "\u2265": ">=",  # ≥
        "\u2260": "!=",  # ≠
    }
)

# Kotwice HTML ze scenariuszy → atrybuty Pandoc przy nagłówku (działające linki PDF).
_ANCHOR_BEFORE_HEADING = re.compile(
    r'<a\s+id="([^"]+)"\s*></a>\s*\n(#{2,6}\s+[^\n]+)',
    re.MULTILINE,
)


def _prepare_chapter(text: str) -> str:
    text = text.replace(IMG_PREFIX_REPO, IMG_PREFIX_PANDOC)
    text = text.translate(_UNICODE_SAFE)

    def _attach_anchor(match: re.Match[str]) -> str:
        anchor, heading = match.group(1), match.group(2)
        if "{#" in heading:
            return f"{heading}\n"
        return f"{heading} {{#{anchor}}}\n"

    return _ANCHOR_BEFORE_HEADING.sub(_attach_anchor, text)


def _merge_chapters() -> str:
    parts: list[str] = []
    for name in CHAPTERS:
        path = MANUAL / name
        if not path.is_file():
            raise FileNotFoundError(f"Brak pliku: {path}")
        text = _prepare_chapter(path.read_text(encoding="utf-8"))
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
