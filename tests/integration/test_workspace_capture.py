"""Integration tests for workspace work-capture, against a real git repository.

The headline guarantee under test: capturing a submission must leave the user's
branch, HEAD, index and working tree exactly as they were. If capture disturbed
their state, submitting would silently sabotage the work being graded.
"""

from pathlib import Path

import pytest

from apps.workspace.services import diff_collector, git_ops

pytestmark = pytest.mark.skipif(
    not git_ops.git_available()[0], reason="git is not installed or too old"
)

SEED_IDENTITY = {
    "GIT_AUTHOR_NAME": "Original Author",
    "GIT_AUTHOR_EMAIL": "author@example.com",
    "GIT_COMMITTER_NAME": "Original Author",
    "GIT_COMMITTER_EMAIL": "author@example.com",
}


@pytest.fixture
def repo(tmp_path) -> Path:
    """A minimal seeded repository standing in for a scaffolded workspace."""
    ws = tmp_path / "ex-001-demo"
    ws.mkdir()
    (ws / "app").mkdir()
    (ws / "tests").mkdir()
    (ws / "app" / "orders.py").write_text("def total(items):\n    return sum(items)\n")
    (ws / "tests" / "test_orders.py").write_text("def test_total():\n    assert True\n")
    (ws / ".gitignore").write_text(".venv/\n__pycache__/\n*.pyc\n")

    git_ops.run_git(ws, "init", "-q")
    git_ops.run_git(ws, "add", "-A")
    git_ops.run_git(ws, "commit", "-q", "-m", "Initial scaffold", env_extra=SEED_IDENTITY)
    return ws


@pytest.fixture
def seed_sha(repo) -> str:
    return git_ops.head_sha(repo)


def snapshot_user_state(repo: Path) -> dict[str, str]:
    """Record everything about the repo the user could notice changing."""
    return {
        "head": git_ops.head_sha(repo),
        "branch": git_ops.run_git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        "status": git_ops.run_git(repo, "status", "--porcelain"),
        "staged": git_ops.run_git(repo, "diff", "--cached", "--name-only"),
        "unstaged": git_ops.run_git(repo, "diff", "--name-only"),
    }


def test_scaffolded_repo_starts_clean(repo):
    """A dirty tree at T=0 would corrupt the diff-against-seed story."""
    assert git_ops.is_tree_clean(repo)


def test_capture_collects_all_three_kinds_of_work(repo, seed_sha):
    # 1. Edit a tracked file and commit it.
    (repo / "app" / "orders.py").write_text(
        "def total(items):\n    return sum(items) if items else 0\n"
    )
    git_ops.run_git(repo, "add", "app/orders.py")
    git_ops.run_git(
        repo,
        "commit",
        "-q",
        "-m",
        "fix: guard against an empty basket\n\nSum of () was returning 0 already, but\nthe intent was unclear.",
        env_extra=SEED_IDENTITY,
    )
    # 2. Edit a tracked file and leave it uncommitted.
    (repo / "tests" / "test_orders.py").write_text(
        "def test_total():\n    assert True\n\n\ndef test_empty():\n    assert True\n"
    )
    # 3. Add a brand new, untracked file.
    (repo / "NOTES.md").write_text("## Root cause\nEmpty basket.\n")

    result = diff_collector.capture(repo, session_id=7, seed_sha=seed_sha)

    assert result.ok, result.error
    changed = {change.path for change in result.numstat}
    assert changed == {"app/orders.py", "tests/test_orders.py", "NOTES.md"}
    assert "app/orders.py" in result.diff_text
    assert "NOTES.md" in result.diff_text
    assert "def test_empty" in result.diff_text
    assert result.user_commit_count == 1
    assert result.files_changed == 3
    assert result.lines_added > 0
    assert not result.is_empty


def test_capture_does_not_disturb_the_users_git_state(repo, seed_sha):
    """The core guarantee. A plain `git add -A` here would stage their files."""
    (repo / "app" / "orders.py").write_text("def total(items):\n    return 0\n")
    (repo / "scratch.py").write_text("# still thinking\n")

    before = snapshot_user_state(repo)
    diff_collector.capture(repo, session_id=7, seed_sha=seed_sha)
    after = snapshot_user_state(repo)

    assert after == before
    # Specifically: nothing became staged.
    assert after["staged"] == ""
    # And the untracked file is still untracked, not added.
    assert "?? scratch.py" in after["status"]


def test_capture_records_commit_bodies_not_just_subjects(repo, seed_sha):
    """Commit messages are scored, and the "why" lives in the body."""
    (repo / "app" / "orders.py").write_text("def total(items):\n    return sum(items)\n# x\n")
    git_ops.run_git(repo, "add", "-A")
    git_ops.run_git(
        repo,
        "commit",
        "-q",
        "-m",
        "fix: clamp negative totals\n\nRefunds were arriving as negative line items.",
        env_extra=SEED_IDENTITY,
    )

    result = diff_collector.capture(repo, session_id=7, seed_sha=seed_sha)
    assert "clamp negative totals" in result.git_log
    assert "Refunds were arriving" in result.git_log


def test_capture_excludes_noise_from_the_diff_but_not_the_inventory(repo, seed_sha):
    """Excluded files must still appear in numstat, so trimming is never silent."""
    (repo / "poetry.lock").write_text("# " + "lock\n" * 500)
    (repo / "app" / "orders.py").write_text("def total(items):\n    return sum(items)\n# y\n")

    result = diff_collector.capture(repo, session_id=7, seed_sha=seed_sha)

    assert "poetry.lock" not in result.diff_text
    assert "poetry.lock" in {change.path for change in result.numstat}


def test_capture_honours_gitignore(repo, seed_sha):
    (repo / ".venv").mkdir()
    (repo / ".venv" / "huge.py").write_text("x = 1\n")

    result = diff_collector.capture(repo, session_id=7, seed_sha=seed_sha)
    assert not any(".venv" in change.path for change in result.numstat)


def test_capture_reports_an_empty_submission(repo, seed_sha):
    result = diff_collector.capture(repo, session_id=7, seed_sha=seed_sha)
    assert result.ok
    assert result.is_empty
    assert result.user_commit_count == 0
    assert result.numstat == []


def test_capture_writes_a_verifiable_bundle(repo, seed_sha, tmp_path):
    (repo / "NOTES.md").write_text("## Root cause\nfound it\n")
    destination = tmp_path / "bundles" / "7.bundle"

    result = diff_collector.capture(
        repo, session_id=7, seed_sha=seed_sha, bundle_destination=destination
    )

    assert result.bundle_path == str(destination)
    assert destination.exists()
    # A bundle git itself refuses to verify would be useless as an archive.
    git_ops.run_git(repo, "bundle", "verify", str(destination))


def test_capture_can_include_whole_files(repo, seed_sha):
    (repo / "app" / "orders.py").write_text("def total(items):\n    return 1\n")

    result = diff_collector.capture(
        repo, session_id=7, seed_sha=seed_sha, include_full_files=["app/orders.py"]
    )

    assert result.full_files["app/orders.py"] == "def total(items):\n    return 1\n"


def test_capture_survives_a_missing_directory(tmp_path):
    """A deleted workspace must yield a graded failure, never a 500."""
    result = diff_collector.capture(tmp_path / "gone", session_id=7, seed_sha="deadbeef")
    assert not result.ok
    assert "no longer exists" in result.error


def test_capture_survives_a_non_repository(tmp_path):
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    result = diff_collector.capture(plain, session_id=7, seed_sha="deadbeef")
    assert not result.ok
    assert "not a git repository" in result.error


def test_snapshot_ref_is_private_and_pinned(repo, seed_sha):
    """The snapshot must be reachable by ref so a later rebase cannot orphan it."""
    ref, sha = diff_collector.snapshot_work(repo, 7)
    assert ref == "refs/submissions/7"
    assert git_ops.run_git(repo, "rev-parse", ref) == sha
    # It must not appear as a branch the user would see.
    assert "submissions" not in git_ops.run_git(repo, "branch", "--no-color")


def test_capture_works_without_a_user_git_identity(repo, seed_sha):
    """Global git config is disabled, so commit-tree must supply its own identity.

    Without an explicit identity this fails with "Please tell me who you are".
    """
    (repo / "NOTES.md").write_text("notes\n")
    result = diff_collector.capture(repo, session_id=7, seed_sha=seed_sha)
    assert result.ok, result.error
    assert result.snapshot_sha


def test_relevance_order_puts_focus_paths_first():
    changes = [
        diff_collector.FileChange("zzz_other.py", 1, 0),
        diff_collector.FileChange("tests/test_x.py", 5, 0),
        diff_collector.FileChange("README.md", 2, 0),
        diff_collector.FileChange("nl2sql/policy/row_level_policy.py", 20, 3),
        diff_collector.FileChange("security/audit_log.py", 4, 0),
    ]
    ordered = diff_collector.relevance_order(
        changes,
        focus_paths=["nl2sql/policy/row_level_policy.py"],
        check_paths=["security/"],
    )
    assert [change.path for change in ordered] == [
        "nl2sql/policy/row_level_policy.py",
        "security/audit_log.py",
        "zzz_other.py",
        "tests/test_x.py",
        "README.md",
    ]
