"""Safe Git/GitHub helpers built on GitPython.

All repository input is validated and normalized here so that callers never
construct shell commands from user input. Cloning uses GitPython's API (no
shell), and we restrict ingestion to public GitHub HTTP(S) URLs.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from git import GitCommandError, Repo

from app.core.exceptions import IngestionError

_GITHUB_URL = re.compile(
    r"^https?://(www\.)?github\.com/(?P<owner>[\w.\-]+)/(?P<repo>[\w.\-]+?)(\.git)?/?$",
    re.IGNORECASE,
)


def parse_github_url(url: str) -> tuple[str, str]:
    """Return ``(owner, repo)`` for a valid GitHub URL, else raise."""
    match = _GITHUB_URL.match(url.strip())
    if not match:
        raise IngestionError("Only public GitHub repository URLs are supported.")
    owner = match.group("owner")
    repo = match.group("repo")
    if repo.endswith(".git"):
        repo = repo[:-4]
    return owner, repo


def clone_repository(url: str, destination: Path, *, depth: int = 1) -> Repo:
    """Shallow-clone a GitHub repository to ``destination``.

    Removes any existing directory first so re-ingestion is idempotent.
    """
    parse_github_url(url)  # validate before doing any filesystem work

    if destination.exists():
        shutil.rmtree(destination, ignore_errors=True)
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        # GitPython invokes git via its API with an argument list — never a
        # shell string — so the URL cannot inject additional commands.
        return Repo.clone_from(url, destination, depth=depth, multi_options=["--no-tags"])
    except GitCommandError as exc:
        raise IngestionError(
            f"Failed to clone repository. Check the URL is public and correct. ({exc.status})"
        ) from exc


def fetch_latest(path: Path, branch: str | None = None) -> str | None:
    """Incrementally update an existing local clone to its remote HEAD.

    Performs a shallow ``git fetch`` of ``branch`` (or whatever HEAD tracks when
    omitted) and hard-resets the working tree to the fetched commit. Unlike
    :func:`clone_repository`, this downloads only the new objects — it never
    re-clones — and is safe to call repeatedly. Returns the new HEAD sha.

    Raises :class:`IngestionError` if the path is not a clone or the fetch fails.
    """
    try:
        repo = Repo(path)
    except Exception as exc:
        raise IngestionError(
            "Local working copy is not a git repository; re-ingest it."
        ) from exc

    target = (branch or "HEAD").strip() or "HEAD"
    try:
        # Fetch only the requested branch at depth 1; reset to FETCH_HEAD so we
        # don't depend on how the remote-tracking ref is named on a shallow
        # single-branch clone.
        repo.git.fetch("origin", target, "--depth=1")
        repo.git.reset("--hard", "FETCH_HEAD")
    except GitCommandError as exc:
        raise IngestionError(
            f"Failed to fetch latest changes from GitHub. ({exc.status})"
        ) from exc

    try:
        return repo.head.commit.hexsha
    except Exception:  # pragma: no cover - defensive
        return None


def read_local_commit(path: Path) -> str | None:
    """Read the current HEAD commit of an existing local clone.

    Opens the repository read-only — it never fetches, pulls, or modifies the
    working tree — so local edits are always preserved. Returns ``None`` if the
    path is not a git repository (e.g. a plain working copy in tests).
    """
    try:
        return Repo(path).head.commit.hexsha
    except Exception:
        return None


def get_repo_metadata(repo: Repo) -> dict:
    """Extract lightweight metadata from a cloned repo."""
    default_branch = "main"
    try:
        default_branch = repo.active_branch.name
    except (TypeError, ValueError):
        # Detached HEAD (common with shallow clones) — fall back to HEAD sha.
        pass

    commit_sha = None
    try:
        commit_sha = repo.head.commit.hexsha
    except Exception:  # pragma: no cover - defensive
        pass

    return {"default_branch": default_branch, "commit_sha": commit_sha}
