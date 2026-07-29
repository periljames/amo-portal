"""Prevent unsigned artifacts from entering signature-required record series."""
from __future__ import annotations

from . import knowledge_service


_original_create_documentation_record = knowledge_service.create_documentation_record


def _create_documentation_record_signature_guarded(*args, **kwargs):
    profile = kwargs.get("profile")
    if profile is None and len(args) > 4:
        profile = args[4]
    if bool(getattr(profile, "requires_signature", False)):
        # The current portal does not yet perform certificate-chain, revocation,
        # document-integrity, signer-identity, or trusted-timestamp validation.
        # Detecting a PDF signature field alone would not establish a valid signature,
        # so fail closed rather than retain unsigned/unverified evidence as compliant.
        raise knowledge_service.HTTPException(
            status_code=409,
            detail=(
                "This controlled workflow requires a validated digital signature, "
                "but trusted PDF signature validation is not configured"
            ),
        )
    return _original_create_documentation_record(*args, **kwargs)


knowledge_service.create_documentation_record = _create_documentation_record_signature_guarded


__all__ = ["_create_documentation_record_signature_guarded"]
