"""Assemble full telederm questionnaire catalog"""

from __future__ import annotations

from typing import Any

from apps.telederm.seed.common import COMMON_QUESTIONS
from apps.telederm.seed.paths.cce002 import CCE002_QUESTIONS
from apps.telederm.seed.paths.cce003 import CCE003_QUESTIONS
from apps.telederm.seed.paths.cce004 import CCE004_QUESTIONS
from apps.telederm.seed.paths.cce005 import CCE005_QUESTIONS
from apps.telederm.seed.paths.cce006 import CCE006_QUESTIONS
from apps.telederm.seed.paths.cce007 import CCE007_QUESTIONS
from apps.telederm.seed.paths.cce008 import CCE008_QUESTIONS
from apps.telederm.seed.paths.cce009 import CCE009_QUESTIONS
from apps.telederm.seed.paths.cce010 import CCE010_QUESTIONS
from apps.telederm.seed.paths.cce011 import CCE011_CATALOG
from apps.telederm.seed.paths.cce012 import CCE012_CATALOG
from apps.telederm.seed.paths.cce013 import CCE013_CATALOG
from apps.telederm.seed.paths.cce014 import CCE014_CATALOG
from apps.telederm.seed.paths.cce015 import CCE015_CATALOG
from apps.telederm.seed.paths.cce001 import CCE001_QUESTIONS
from apps.telederm.seed.paths.global_fields import GLOBAL_FIELDS_CATALOG

TELEDERM_CATALOG: list[dict[str, Any]] = [
    *COMMON_QUESTIONS,
    *CCE001_QUESTIONS,
    *CCE002_QUESTIONS,
    *CCE003_QUESTIONS,
    *CCE004_QUESTIONS,
    *CCE005_QUESTIONS,
    *CCE006_QUESTIONS,
    *CCE007_QUESTIONS,
    *CCE008_QUESTIONS,
    *CCE009_QUESTIONS,
    *CCE010_QUESTIONS,
    *CCE011_CATALOG,
    *CCE012_CATALOG,
    *CCE013_CATALOG,
    *CCE014_CATALOG,
    *CCE015_CATALOG,
    *GLOBAL_FIELDS_CATALOG,
]

# Backward-compatible alias used by earlier migrations / tests.
TELEDERM_SMOKE_CATALOG = TELEDERM_CATALOG
