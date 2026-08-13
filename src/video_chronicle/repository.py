"""Repository port and in-memory stage-05 reference adapter."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .project import ProjectState


class ProjectNotFoundError(KeyError):
    """Raised when a project ID is absent from a repository."""


@runtime_checkable
class ProjectRepository(Protocol):
    def save(self, state: ProjectState) -> None: ...

    def get(self, project_id: str) -> ProjectState: ...

    def list_project_ids(self) -> tuple[str, ...]: ...


class InMemoryProjectRepository:
    """Process-local replacement store for immutable project snapshots."""

    def __init__(self) -> None:
        self._projects: dict[str, ProjectState] = {}

    def save(self, state: ProjectState) -> None:
        if not isinstance(state, ProjectState):
            raise TypeError("state must be ProjectState")
        self._projects[state.project_id] = state

    def get(self, project_id: str) -> ProjectState:
        try:
            return self._projects[project_id]
        except KeyError as exc:
            raise ProjectNotFoundError(project_id) from exc

    def list_project_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._projects))

