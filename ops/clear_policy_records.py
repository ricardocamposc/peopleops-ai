"""Delete only PeopleOps policy records and their cascaded ingestion data."""

from __future__ import annotations

import argparse

from sqlalchemy import delete, func, select

from peopleops_api.db import create_session_factory
from peopleops_api.models import IngestionJob, PolicyChunk, PolicyDocument, PolicyVersion


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="confirm deletion")
    args = parser.parse_args()
    if not args.yes:
        raise SystemExit("Refusing to delete policy records without --yes")

    from peopleops_api.config import Settings

    settings = Settings()
    session = create_session_factory(settings)()
    try:
        counts = {
            "policy_document": session.scalar(select(func.count()).select_from(PolicyDocument)),
            "policy_version": session.scalar(select(func.count()).select_from(PolicyVersion)),
            "policy_chunk": session.scalar(select(func.count()).select_from(PolicyChunk)),
            "ingestion_job": session.scalar(select(func.count()).select_from(IngestionJob)),
        }
        session.execute(delete(PolicyDocument))
        session.commit()
        remaining = {
            "policy_document": session.scalar(select(func.count()).select_from(PolicyDocument)),
            "policy_version": session.scalar(select(func.count()).select_from(PolicyVersion)),
            "policy_chunk": session.scalar(select(func.count()).select_from(PolicyChunk)),
            "ingestion_job": session.scalar(select(func.count()).select_from(IngestionJob)),
        }
        print(f"Deleted policy records: {counts}")
        print(f"Remaining policy records: {remaining}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
