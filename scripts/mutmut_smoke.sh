#!/usr/bin/env sh
# CI / make mutmut-smoke: verify mutmut config and mutant workspace (not full score gate).
set -eu

python -m pytest apps/medical/tests/test_name_normalize.py \
  -c mutmut_pytest.ini --no-cov -q --tb=line

rm -rf mutants
# Generation + stats must succeed for the pilot module.
mutmut run 'apps.medical.name_normalize*'

if [ ! -f mutants/apps/medical/name_normalize.py ]; then
  echo "mutmut smoke failed: mutants/apps/medical/name_normalize.py missing" >&2
  exit 1
fi

if [ ! -f mutants/conftest.py ]; then
  echo "mutmut smoke failed: mutants/conftest.py missing (also_copy)" >&2
  exit 1
fi

# Stats phase must resolve mutated modules from mutants/, not repo root.
if ! python -c "
import os, sys
os.chdir('mutants')
sys.path.insert(0, '.')
import conftest  # noqa: F401 — bootstrap + import isolation
import apps.medical.name_normalize as m
assert 'mutants' in (getattr(m, '__file__', '') or '')
"; then
  echo "mutmut smoke failed: import isolation under mutants/" >&2
  exit 1
fi

echo "mutmut smoke OK (mutant workspace created, pytest config valid)"
