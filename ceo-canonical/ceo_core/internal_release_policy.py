from __future__ import annotations

from dataclasses import dataclass

from .update_channel import official_channel


@dataclass(frozen=True, slots=True)
class InternalReleasePolicy:
    """Standing policy for CEO's own update channel.

    It is deliberately narrow: it authorizes publication of already-qualified CEO
    update artifacts to the single built-in update channel. It never authorizes
    installation, key rotation, arbitrary repository writes, or other external
    publication.
    """

    standing_publication_authorization: bool = True
    install_requires_human_confirmation: bool = True
    allow_key_rotation: bool = False
    path_prefix: str = "ceo-updates/"
    branch: str = "ceo-update-channel"

    @property
    def repository(self) -> str:
        return official_channel().intended_repository

    def allows(self, *, repository: str, branch: str, path: str) -> bool:
        repo = str(repository or "").strip().lower()
        intended = str(self.repository or "").strip().lower()
        clean_path = str(path or "").replace("\\", "/").lstrip("/")
        return bool(
            self.standing_publication_authorization
            and intended
            and repo == intended
            and str(branch or "") == self.branch
            and clean_path.startswith(self.path_prefix)
        )


def internal_release_policy() -> InternalReleasePolicy:
    return InternalReleasePolicy()
