from fastapi import APIRouter

from . import schemas
from .approvals import approve_exact_configuration
from .context import get_context, list_entries
from .corrections import correct_latest_entry
from .drafting import create_draft, preview_entry
from .posting import post_entry

router = APIRouter(
    prefix="/daily-utilisation",
    tags=["daily aircraft utilisation"],
)
router.add_api_route(
    "/aircraft/{serial_number}/context",
    get_context,
    methods=["GET"],
    response_model=schemas.DailyUtilisationContext,
)
router.add_api_route(
    "/aircraft/{serial_number}/entries",
    list_entries,
    methods=["GET"],
    response_model=list[schemas.DailyUtilisationEntryRead],
)
router.add_api_route(
    "/aircraft/{serial_number}/configuration",
    approve_exact_configuration,
    methods=["PUT"],
    response_model=schemas.DailyUtilisationContext,
)
router.add_api_route(
    "/aircraft/{serial_number}/preview",
    preview_entry,
    methods=["POST"],
    response_model=schemas.DailyUtilisationPreview,
)
router.add_api_route(
    "/aircraft/{serial_number}/entries",
    create_draft,
    methods=["POST"],
    response_model=schemas.DailyUtilisationDraftRead,
    status_code=201,
)
router.add_api_route(
    "/entries/{entry_id}/post",
    post_entry,
    methods=["POST"],
    response_model=schemas.DailyUtilisationPostRead,
)
router.add_api_route(
    "/entries/{entry_id}/correct",
    correct_latest_entry,
    methods=["POST"],
    response_model=schemas.DailyUtilisationPostRead,
)

__all__ = [
    "router",
    "approve_exact_configuration",
    "get_context",
    "list_entries",
    "preview_entry",
    "create_draft",
    "post_entry",
    "correct_latest_entry",
]
