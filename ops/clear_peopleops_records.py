"""Delete all operational and policy records from the PeopleOps database.

The synthetic HRIS database is a separate service and is intentionally not
modified by this command.
"""

from __future__ import annotations

import argparse

from sqlalchemy import delete, func, select

from peopleops_api.db import create_session_factory
from peopleops_api.models import (
    AnalysisInteraction,
    Conversation,
    HumanReviewDecision,
    HumanReviewRequest,
    IngestionJob,
    PolicyChunk,
    PolicyDocument,
    PolicyVersion,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="confirm deletion")
    args = parser.parse_args()
    if not args.yes:
        raise SystemExit("Refusing to delete PeopleOps records without --yes")

    from peopleops_api.config import Settings

    session = create_session_factory(Settings())()
    models = (
        HumanReviewDecision,
        HumanReviewRequest,
        AnalysisInteraction,
        Conversation,
        IngestionJob,
        PolicyChunk,
        PolicyVersion,
        PolicyDocument,
    )
    try:
        before = {
            model.__tablename__: session.scalar(select(func.count()).select_from(model))
            for model in models
        }
        for model in models:
            session.execute(delete(model))
        session.commit()
        after = {
            model.__tablename__: session.scalar(select(func.count()).select_from(model))
            for model in models
        }
        print(f"Deleted PeopleOps records: {before}")
        print(f"Remaining PeopleOps records: {after}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
