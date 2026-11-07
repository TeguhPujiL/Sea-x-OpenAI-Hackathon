from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Integer, MetaData, Uuid
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator


class UuidV4(TypeDecorator):
    impl = Uuid
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        value = value if isinstance(value, UUID) else UUID(str(value))
        if value.version != 4:
            raise ValueError("Resource identifiers must be UUID v4")
        return value


class UtcDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must be timezone-aware")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s", "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


class Identity:
    id = Column(UuidV4, primary_key=True, default=uuid4)


class Created:
    created_at = Column(UtcDateTime, nullable=False, default=now)


class Mutable(Created):
    version = Column(Integer, nullable=False, default=1)
    updated_at = Column(UtcDateTime, nullable=False, default=now, onupdate=now)


class SoftDeleted:
    deleted_at = Column(UtcDateTime, nullable=True)
