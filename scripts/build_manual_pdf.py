#!/usr/bin/env python3
"""
Złożenie instrukcji z docs/manual/*.md w jeden plik PDF.

Wymaga: Pandoc (https://pandoc.org) oraz silnika PDF (np. MiKTeX / TeX Live z xelatex —
zalecane dla polskich znaków).

Uruchom z korzenia repozytorium:
    python scripts/build_manual_pdf.py

Wynik: docs/manual/_build/Cogitomedica-Instrukcje.pdf (tymczasowe pliki w _build/).

PDF to wersja dla użytkownika końcowego: przy merge filtr usuwa treść maintainerską
(scenariusze: szablony, backlog filmów, Docelowo/Film, linki .ai/ itd.). Źródła w
docs/manual/ pozostają pełne dla autorów.
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

# Linki / ścieżki maintainerskie — nie dla PDF użytkownika.
_MAINTAINER_REF = re.compile(
    r"(?:"
    r"\.ai/"
    r"|TODO\.md"
    r"|scripts/"
    r"|assets/videos"
    r"|runbooks?/"
    r"|INTEGRATION_ERROR"
    r"|OUTBOX_BACKLOG"
    r"|runbook-patient-"
    r"|\.webm"
    r"|gitignore"
    r"|kotwic"
    r")",
    re.IGNORECASE,
)

_SCENARIO_META_ROW = re.compile(
    r"^\|\s*\*\*(?:Film|Docelowo)\*\*\s*\|[^\n]*\|[ \t]*\n?",
    re.MULTILINE,
)

_SECTION_JAK_DOPISYWAC = re.compile(
    r"^## Jak dopisywać nowy scenariusz\n.*?(?=^## |\Z)",
    re.MULTILINE | re.DOTALL,
)

_SECTION_BACKLOG_FILMOW = re.compile(
    r"^## Backlog filmów\n.*\Z",
    re.MULTILINE | re.DOTALL,
)

_INDEX_FILM_NOTE = re.compile(
    r"^>\s*Kolumna \*\*Film\*\*.*\n?",
    re.MULTILINE,
)

_INDEX_KOTWICE_NOTE = re.compile(
    r"^Kotwice w indeksie.*\n?",
    re.MULTILINE,
)

_POWIĄZANE_INTRO = re.compile(
    r"^Powiązane:\s*.*$",
    re.MULTILINE,
)

_FILM_SENTENCE = re.compile(
    r"\s*Film:\s*`[^`]*\.webm`\.?",
    re.IGNORECASE,
)

_LINE_WITH_MAINTAINER = re.compile(
    r"^.*(?:\.ai/|TODO\.md|scripts/).*$",
    re.MULTILINE,
)


def _drop_table_column(table_md: str, col_index: int) -> str:
    """Usuń kolumnę o podanym indeksie (0-based) z tabeli Markdown."""
    lines_out: list[str] = []
    for line in table_md.strip("\n").splitlines():
        if not line.strip().startswith("|"):
            lines_out.append(line)
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if col_index < 0 or col_index >= len(cells):
            lines_out.append(line)
            continue
        del cells[col_index]
        lines_out.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines_out)


def _filter_powiazane_cell(cell: str) -> str | None:
    """Zostaw odnośniki do rozdziałów manuala / SC-NNN; usuń maintainerskie."""
    parts = [p.strip() for p in cell.split(",")]
    kept: list[str] = []
    for part in parts:
        if not part:
            continue
        if _MAINTAINER_REF.search(part):
            continue
        kept.append(part)
    if not kept:
        return None
    return ", ".join(kept)


def _filter_powiazane_rows(text: str) -> str:
    def _repl(match: re.Match[str]) -> str:
        cell = match.group(1)
        filtered = _filter_powiazane_cell(cell)
        if filtered is None:
            return ""
        return f"| **Powiązane** | {filtered} |\n"

    return re.sub(
        r"^\|\s*\*\*Powiązane\*\*\s*\|\s*(.*?)\s*\|[ \t]*\n?",
        _repl,
        text,
        flags=re.MULTILINE,
    )


def _simplify_scenariusze_intro(text: str) -> str:
    text = re.sub(
        r"^# Scenariusze operacyjne — FAQ i materiały wideo\s*$",
        "# Scenariusze operacyjne — FAQ",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"(Zbiór \*\*codziennych sytuacji\*\* z pracy placówki, opisanych tak, "
        r"żeby recepcja, lekarz i manager szybko znaleźli rozwiązanie\.)"
        r"\s*Przy wielu scenariuszach jest też krótki filmik \(WebM\)\.",
        r"\1",
        text,
        count=1,
    )
    text = _POWIĄZANE_INTRO.sub("", text, count=1)
    # Usuń osierocone puste linie po wycięciu „Powiązane: …”.
    text = re.sub(r"\n{3,}", "\n\n", text, count=1)
    return text


def _filter_scenariusze_index(text: str) -> str:
    def _repl(match: re.Match[str]) -> str:
        table = match.group(0)
        # Kolumna Film jest ostatnia (indeks 3).
        simplified = _drop_table_column(table, 3)
        return simplified

    return re.sub(
        r"(?m)^\| ID \| Tytuł \| Role \| Film \|.*?^(?=\n|>|Kotwice|---|## |\Z)",
        _repl,
        text,
        count=1,
        flags=re.DOTALL,
    )


def filter_scenariusze_for_user_pdf(text: str) -> str:
    """Usuń treść maintainerską ze scenariuszy — tylko FAQ operacyjne dla PDF."""
    text = _simplify_scenariusze_intro(text)
    text = _SECTION_JAK_DOPISYWAC.sub("", text)
    text = _SECTION_BACKLOG_FILMOW.sub("", text)
    text = _filter_scenariusze_index(text)
    text = _INDEX_FILM_NOTE.sub("", text)
    text = _INDEX_KOTWICE_NOTE.sub("", text)
    text = _SCENARIO_META_ROW.sub("", text)
    text = _filter_powiazane_rows(text)
    # Kotwice HTML: _prepare_chapter przeniesie je na nagłówki; tu zostawiamy.
    # Posprzątaj wielokrotne puste linie powstałe po wycięciach.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def filter_chapter_maintainer_refs(text: str) -> str:
    """Usuń oczywiste odniesienia IT/agent (.ai/, .webm, scripts/) z innych rozdziałów."""
    text = _FILM_SENTENCE.sub("", text)
    text = _LINE_WITH_MAINTAINER.sub("", text)
    # Puste sekcje typu „## 10. Dokumentacja techniczna” + same --- / puste linie.
    text = re.sub(
        r"(?m)^(#{2,6}\s+[^\n]+)\n+(?:---\n+)*(?=#{2,6}\s|\Z)",
        "",
        text,
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _prepare_chapter(name: str, text: str) -> str:
    if name == "scenariusze.md":
        text = filter_scenariusze_for_user_pdf(text)
    else:
        text = filter_chapter_maintainer_refs(text)

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
        text = _prepare_chapter(name, path.read_text(encoding="utf-8"))
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
        description="Buduje jeden PDF z rozdziałów docs/manual/ (wersja użytkownika)."
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

    # Szybka asercja: po filtrze nie powinno być typowej treści maintainerskiej.
    forbidden = (
        "TODO.md",
        "Jak dopisywać",
        ".webm",
        "gitignore",
        "kotwic",
        "Backlog filmów",
        ".ai/",
    )
    lower = merged.lower()
    hits = [f for f in forbidden if f.lower() in lower]
    if hits:
        sys.stderr.write(
            "Ostrzeżenie: w złączonym Markdown nadal widać treść maintainerską: "
            + ", ".join(hits)
            + f"\nSprawdź {combined}\n"
        )

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
