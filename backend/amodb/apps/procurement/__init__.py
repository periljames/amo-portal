"""Tenant-scoped aviation Procurement and Supply Chain domain."""

# Keep the Procurement evidence validation/audit service authoritative while
# replacing node-local retained-file persistence with the portal storage layer.
from .document_shared_storage import install_procurement_shared_storage

install_procurement_shared_storage()

__all__ = ["install_procurement_shared_storage"]
