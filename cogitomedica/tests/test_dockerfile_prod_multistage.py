"""Contract: production image is multi-stage and keeps WeasyPrint/psycopg runtime libs."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOCKERFILE_PROD = _REPO_ROOT / "Dockerfile.prod"


def _dockerfile() -> str:
    return _DOCKERFILE_PROD.read_text(encoding="utf-8")


def _builder_section(text: str) -> str:
    marker = "FROM python:3.13-slim AS runtime"
    idx = text.index(marker)
    return text[:idx]


def _runtime_section(text: str) -> str:
    marker = "FROM python:3.13-slim AS runtime"
    idx = text.index(marker)
    return text[idx:]


def test_prod_dockerfile_is_multistage() -> None:
    text = _dockerfile()
    assert "FROM python:3.13-slim AS builder" in text
    assert "FROM python:3.13-slim AS runtime" in text


def test_toolchain_stays_in_builder() -> None:
    builder = _builder_section(_dockerfile())
    runtime = _runtime_section(_dockerfile())
    assert "build-essential" in builder
    assert "libpq-dev" in builder
    assert "gettext" in builder
    assert "build-essential" not in runtime
    assert "libpq-dev" not in runtime
    assert "libcairo2" in builder
    assert "libglib2.0-0" in builder


def test_runtime_keeps_psycopg_and_weasyprint_libs() -> None:
    runtime = _runtime_section(_dockerfile())
    for pkg in (
        "libpq5",
        "libcairo2",
        "libglib2.0-0",
        "libpango-1.0-0",
        "libpangocairo-1.0-0",
        "libpangoft2-1.0-0",
        "libgdk-pixbuf-2.0-0",
        "libffi8",
        "shared-mime-info",
        "fonts-dejavu-core",
    ):
        assert pkg in runtime, pkg


def test_prod_entrypoint_and_gunicorn_unchanged() -> None:
    text = _dockerfile()
    assert 'ENTRYPOINT ["/docker-entrypoint-prod.sh"]' in text
    assert '"--timeout", "600"' in text
    assert "docker-healthcheck-web.sh" in text
    assert "verify_prod_image.sh" not in text


def test_verify_prod_image_script_exists_and_skips_django_check() -> None:
    script = _REPO_ROOT / "scripts" / "verify_prod_image.sh"
    assert script.is_file()
    body = script.read_text(encoding="utf-8")
    assert not any(
        line.strip().startswith("python manage.py check")
        for line in body.splitlines()
    )
    assert "weasyprint" in body
    assert "libpq5" in body


def test_ci_mounts_verify_script_into_prod_image() -> None:
    ci = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "Dockerfile.prod" in ci
    assert "scripts/verify_prod_image.sh:/verify_prod_image.sh" in ci
    assert "/app/scripts/verify_prod_image.sh" not in ci


def test_runtime_does_not_copy_entire_builder_app_tree() -> None:
    runtime = _runtime_section(_dockerfile())
    assert "COPY --from=builder /app /app" not in runtime
    for path in (
        "/app/manage.py",
        "/app/apps",
        "/app/cogitomedica",
        "/app/templates",
        "/app/locale",
        "/app/static",
    ):
        assert f"COPY --from=builder {path} {path}" in runtime


def test_dockerignore_excludes_tests_and_dev_trees() -> None:
    text = (_REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
    for pattern in (".github", "learning", "**/tests", "media", "public"):
        assert pattern in text, pattern
