#!/usr/bin/env sh
# CI / make mutmut-smoke: verify mutmut config and mutant workspace (not full score gate).
set -eu

python -m pytest apps/medical/tests/test_name_normalize.py \
  -c mutmut_pytest.ini --no-cov -q --tb=line

rm -rf mutants
# mutmut may exit 1 when test↔mutant mapping is incomplete; generation must still succeed.
mutmut run 'apps.medical.name_normalize*' || true

if [ ! -f mutants/apps/medical/name_normalize.py ]; then
  echo "mutmut smoke failed: mutants/apps/medical/name_normalize.py missing" >&2
  exit 1
fi

echo "mutmut smoke OK (mutant workspace created, pytest config valid)"
