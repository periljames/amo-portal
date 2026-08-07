"""Versioned aircraft engineering architecture domains."""

# Import model modules before the composition router so SQLAlchemy can resolve
# all string relationships during application mapper initialization.
from .aircraft_catalogue import models as aircraft_catalogue_models  # noqa: F401
from .aircraft_induction import models as aircraft_induction_models  # noqa: F401
from .content_packs import models as content_pack_models  # noqa: F401
from .content_packs import backend_models as content_pack_backend_models  # noqa: F401
from .daily_utilisation import models as daily_utilisation_models  # noqa: F401
from .effectivity import models as effectivity_models  # noqa: F401
from .import_staging import models as import_staging_models  # noqa: F401
from .tenant_programmes import models as tenant_programme_models  # noqa: F401
from . import router  # noqa: F401,E402
