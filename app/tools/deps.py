"""Repository-backed tool base."""

from app.core.request_scope import get_db_session
from app.repositories.lab_repository import LabRepository


class LabRepositoryBackedTool:
    """Resolve the request-scoped lab repository without storing sessions on tools."""

    def __init__(self, repository: LabRepository | None = None) -> None:
        self._lab_repository = repository

    @property
    def repository(self) -> LabRepository:
        if self._lab_repository is not None:
            return self._lab_repository
        return LabRepository(get_db_session())
