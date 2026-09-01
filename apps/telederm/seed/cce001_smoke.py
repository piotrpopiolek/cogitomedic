"""Migration-only shim: 0002/0003 import TELEDERM_SMOKE_CATALOG from here.

Canonical catalog: apps.telederm.seed.catalog
Path CCE-001 data: apps.telederm.seed.paths.cce001
"""

from apps.telederm.seed.catalog import TELEDERM_SMOKE_CATALOG

__all__ = ["TELEDERM_SMOKE_CATALOG"]
