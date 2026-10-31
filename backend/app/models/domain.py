"""Domain verification and email security checks ORM model.

Conforms to Section 8 & Feature F3 of PROJECT_SPECIFICATION.md:
- Domain resolution and MX route availability
- Email authentication records: SPF, DMARC, DKIM
- Lookalike / typosquatting flags against verified company domains
"""

from datetime import datetime
from typing import Any, Dict, Optional
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON
from app.db.base import Base


class DomainCheck(Base):
    """
    Audit log of domain authentication, mail exchange checks, and lookalike warnings.
    Table 8 of PROJECT_SPECIFICATION.md.
    """
    __tablename__ = "domain_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    dns_status: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN")
    mx_status: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN")
    spf_status: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN")
    dkim_status: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN")
    dmarc_status: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN")
    lookalike_flags: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    source_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
