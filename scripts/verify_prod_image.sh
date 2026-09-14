#!/bin/sh
# Smoke the production runtime image: no build toolchain, psycopg + WeasyPrint, sample PDF.
# Intentionally does not run `manage.py check`: that command's database checks need
# Postgres + DB_* (see the pytest CI job). This script is mounted in CI, not baked into prod.
set -eu

fail() {
    printf '%s\n' "$*" >&2
    exit 1
}

for pkg in build-essential libpq-dev; do
    if dpkg-query -W -f='${Status}\n' "$pkg" 2>/dev/null | grep -q 'install ok installed'; then
        fail "FAIL: $pkg is installed in the runtime image"
    fi
done

if command -v gcc >/dev/null 2>&1; then
    fail "FAIL: gcc is present in the runtime image"
fi

dpkg-query -W -f='${Status}\n' libpq5 2>/dev/null | grep -q 'install ok installed' \
    || fail "FAIL: libpq5 missing (psycopg runtime)"

python -c "import psycopg, weasyprint; print('imports ok', psycopg.__version__, weasyprint.__version__)"

python -c "from pathlib import Path; from weasyprint import HTML; p = Path('/tmp/weasyprint-smoke.pdf'); HTML(string='<h1>CogitoMedica</h1>').write_pdf(p); assert p.stat().st_size > 0; print('pdf ok', p.stat().st_size)"

echo "verify_prod_image: OK"
