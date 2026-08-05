"""Single ORM import surface for the universal induction bounded context."""

from sqlalchemy.orm import synonym

from .domain_models import *  # noqa: F401,F403

# Keep the public service vocabulary concise while the database uses explicit
# non-colliding column names. These are mapped synonyms, not legacy routes or
# duplicate persistence models.
TemplateSourceDocument.revision_id = synonym("template_revision_id")
TemplateSourceDocument.revision = synonym("document_revision")
TemplateConfigurationNode.revision_id = synonym("template_revision_id")
TemplateRequirement.revision_id = synonym("template_revision_id")
