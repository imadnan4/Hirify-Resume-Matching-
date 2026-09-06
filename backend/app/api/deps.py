"""Shared FastAPI dependencies (Annotated aliases per official best practices)."""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.db import get_db

DbSession = Annotated[Session, Depends(get_db)]
