"""Shared FastAPI dependencies (Annotated aliases per official best practices)."""
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.db import get_db

if TYPE_CHECKING:
    from app.models.tables import Organization

DbSession = Annotated[Session, Depends(get_db)]


def get_current_org(db: DbSession) -> "Organization":
    """Workspace resolver. Single default org until Google login lands, then this
    returns the caller's org. Override in tests for isolation checks."""
    from app.models.tables import Organization

    org = db.query(Organization).order_by(Organization.id).first()
    if org is None:
        org = Organization(name="Default workspace")
        db.add(org)
        db.commit()
        db.refresh(org)
    return org


CurrentOrg = Annotated["Organization", Depends(get_current_org)]
