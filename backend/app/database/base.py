"""Declarative base for all ORM models.

Every model added under app/models/ subclasses Base so it registers on
Base.metadata — that's what Alembic's autogenerate compares against the live
database to produce migrations.

The naming convention is set here, before any model/migration exists, because
retrofitting it after tables are created means hand-writing a migration to
rename every auto-generated constraint. It makes constraint/index names
deterministic (e.g. "uq_users_email" instead of Postgres's default
"users_email_key"), which is what lets autogenerate produce clean, stable
diffs across environments.
"""
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
