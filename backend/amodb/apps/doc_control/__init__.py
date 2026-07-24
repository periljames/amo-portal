"""Document Control application package.

The explicit ``sitecustomize`` import is intentional. Python console entry points do
not consistently discover the repository-local sitecustomize module before Alembic
loads this package, even when ``PYTHONPATH`` contains ``backend``. Importing it here
makes the compatibility hook deterministic because Alembic's environment imports
Document Control models before migration traversal begins. The hook itself remains
dormant for API, worker, test, and management processes.
"""

import sitecustomize  # noqa: F401  # process-gated Alembic compatibility hook

from .router import router

__all__ = ["router"]
