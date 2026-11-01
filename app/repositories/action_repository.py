"""Durable, owner-bound confirmation proposals using the request transaction."""

from datetime import UTC, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidRequestError
from app.core.time import utcnow
from app.repositories.models import PendingActionRow
from app.schemas.chat import ActionProposal


class ActionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, action: ActionProposal, *, session_id: str, user_id: str) -> None:
        self._session.add(
            PendingActionRow(
                action_id=action.action_id,
                session_id=session_id,
                user_id=user_id,
                proposal_json=action.model_dump_json(),
                expires_at=utcnow() + timedelta(minutes=15),
            )
        )

    async def resolve(self, action_id: str, *, session_id: str, user_id: str) -> ActionProposal:
        row = await self._session.get(PendingActionRow, action_id)
        if row is None or row.session_id != session_id or row.user_id != user_id:
            raise InvalidRequestError("待确认操作不存在或已过期，请重新发起。")
        expires = row.expires_at
        if expires.tzinfo is None:  # SQLite returns naive values for UTC DateTime columns.
            expires = expires.replace(tzinfo=UTC)
        if expires <= utcnow():
            raise InvalidRequestError("待确认操作不存在或已过期，请重新发起。")
        # Keep proposals until expiry so retries use the executor's durable idempotency key.
        return ActionProposal.model_validate_json(row.proposal_json)
