"""Initialize universal induction policy and source adapters."""

from . import service_facade as hardened
from . import services as base
from . import auto_mapping as _auto_mapping  # noqa: F401
from . import xlsb_support as _xlsb_support  # noqa: F401

base.publish_revision = hardened.publish_revision
base.create_tenant_program_revision = hardened.create_tenant_program_revision
base.resolve_applicability = hardened.resolve_applicability
base._create_counter_opening = hardened._create_counter_opening
base._materialise_program = hardened._materialise_program
