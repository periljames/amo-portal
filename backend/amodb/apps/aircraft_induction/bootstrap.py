"""Apply the hardened service implementations before API route functions run."""

from . import service_facade as hardened
from . import services as base

base.publish_revision = hardened.publish_revision
base.create_tenant_program_revision = hardened.create_tenant_program_revision
base.resolve_applicability = hardened.resolve_applicability
base._create_counter_opening = hardened._create_counter_opening
base._materialise_program = hardened._materialise_program
