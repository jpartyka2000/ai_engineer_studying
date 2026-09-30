"""Tests for the workspace filesystem safety kernel.

These are the highest-stakes tests in the workspace app: the module under test is
the only code in the project that deletes directory trees. Every test here
describes a way the app could destroy or expose something it shouldn't.
"""

import json
from pathlib import Path

import pytest

from apps.workspace.exceptions import NotDeletableError, UnsafePathError
from apps.workspace.services import paths


@pytest.fixture
def ws_root(tmp_path, settings):
    """Point WORKSPACE_ROOT at a temp directory deep enough to pass sanity checks."""
    root = tmp_path / "home" / "user" / "ai-prep-workspaces"
    root.mkdir(parents=True)
    settings.WORKSPACE_ROOT = root
    return root.resolve()


@pytest.fixture
def workspace(ws_root):
    """A scaffolded workspace directory carrying a valid sentinel."""
    ws = ws_root / "ex-001-demo"
    ws.mkdir()
    paths.write_sentinel(ws, session_id=42, exercise_slug="ex-001-demo")
    return ws


# ---------------------------------------------------------------------------
# Containment
# ---------------------------------------------------------------------------


def test_accepts_a_directory_inside_the_root(ws_root):
    target = ws_root / "ex-001-demo"
    assert paths.assert_safe_workspace_path(target) == target.resolve()


def test_accepts_a_nested_path_inside_a_workspace(ws_root):
    target = ws_root / "ex-001-demo" / "app" / "models.py"
    assert paths.assert_safe_workspace_path(target) == target.resolve()


def test_rejects_the_workspace_root_itself(ws_root):
    """Deleting the root would wipe every workspace at once."""
    with pytest.raises(UnsafePathError, match="root itself"):
        paths.assert_safe_workspace_path(ws_root)


def test_rejects_a_path_outside_the_root(ws_root, tmp_path):
    with pytest.raises(UnsafePathError, match="outside"):
        paths.assert_safe_workspace_path(tmp_path / "elsewhere")


def test_rejects_parent_traversal(ws_root):
    with pytest.raises(UnsafePathError, match=r"\.\."):
        paths.assert_safe_workspace_path(ws_root / ".." / "escaped")


def test_rejects_traversal_that_would_resolve_back_inside(ws_root):
    """`..` is refused outright, even when the result would land inside the root.

    Allowing it would mean the containment check depends on string normalisation
    order, which is exactly the kind of subtlety that produces a CVE.
    """
    with pytest.raises(UnsafePathError, match=r"\.\."):
        paths.assert_safe_workspace_path(ws_root / "ex-001" / ".." / "ex-002")


def test_rejects_a_relative_path(ws_root):
    with pytest.raises(UnsafePathError, match="absolute"):
        paths.assert_safe_workspace_path("ex-001-demo")


def test_rejects_a_sibling_of_the_root_sharing_its_prefix(ws_root):
    """`/a/b/root-evil` must not pass a naive startswith-style containment check."""
    sibling = ws_root.parent / (ws_root.name + "-evil")
    with pytest.raises(UnsafePathError, match="outside"):
        paths.assert_safe_workspace_path(sibling / "ex-001")


# ---------------------------------------------------------------------------
# Symlinks
# ---------------------------------------------------------------------------


def test_rejects_a_symlink_escaping_to_filesystem_root(ws_root):
    """The canonical escape: a workspace entry symlinked to `/`."""
    link = ws_root / "ex-001-demo"
    link.symlink_to(Path(ws_root.anchor), target_is_directory=True)
    with pytest.raises(UnsafePathError, match="symlink"):
        paths.assert_safe_workspace_path(link)


def test_rejects_a_symlink_pointing_outside_the_root(ws_root, tmp_path):
    outside = tmp_path / "precious"
    outside.mkdir()
    link = ws_root / "ex-001-demo"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafePathError, match="symlink"):
        paths.assert_safe_workspace_path(link)


def test_rejects_a_symlink_pointing_at_a_sibling_inside_the_root(ws_root):
    """Containment alone would allow this, because the target is still inside.

    Deleting through such a link would destroy a different workspace's contents.
    """
    real = ws_root / "ex-002-real"
    real.mkdir()
    link = ws_root / "ex-001-demo"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(UnsafePathError, match="symlink"):
        paths.assert_safe_workspace_path(link)


def test_rejects_a_symlinked_intermediate_component(ws_root, tmp_path):
    outside = tmp_path / "precious"
    outside.mkdir()
    ws = ws_root / "ex-001-demo"
    ws.mkdir()
    (ws / "app").symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafePathError, match="symlink"):
        paths.assert_safe_workspace_path(ws / "app" / "models.py")


# ---------------------------------------------------------------------------
# Root sanity
# ---------------------------------------------------------------------------


def test_rejects_filesystem_root_as_workspace_root(settings):
    settings.WORKSPACE_ROOT = Path("/")
    with pytest.raises(UnsafePathError, match="filesystem root"):
        paths.assert_safe_workspace_path("/anything")


def test_rejects_home_directory_as_workspace_root(settings):
    settings.WORKSPACE_ROOT = Path.home()
    with pytest.raises(UnsafePathError, match="home directory"):
        paths.assert_safe_workspace_path(Path.home() / "ex-001")


def test_rejects_project_directory_as_workspace_root(settings):
    settings.WORKSPACE_ROOT = Path(settings.BASE_DIR)
    with pytest.raises(UnsafePathError, match="project directory"):
        paths.assert_safe_workspace_path(Path(settings.BASE_DIR) / "ex-001")


def test_rejects_a_shallow_workspace_root(settings, monkeypatch):
    """A two-component root like /Users is too close to a system directory."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: Path("/elsewhere")))
    settings.WORKSPACE_ROOT = Path("/Users")
    with pytest.raises(UnsafePathError, match="shallow"):
        paths.assert_safe_workspace_path("/Users/ex-001")


# ---------------------------------------------------------------------------
# Sentinel and deletability
# ---------------------------------------------------------------------------


def test_write_then_read_sentinel_round_trips(workspace):
    sentinel = paths.read_sentinel(workspace)
    assert sentinel is not None
    assert sentinel["session_id"] == 42
    assert sentinel["exercise_slug"] == "ex-001-demo"
    assert sentinel["app"] == paths.SENTINEL_APP_ID
    assert sentinel["schema_version"] == paths.SENTINEL_SCHEMA_VERSION


def test_read_sentinel_returns_none_when_absent(ws_root):
    bare = ws_root / "not-ours"
    bare.mkdir()
    assert paths.read_sentinel(bare) is None


def test_read_sentinel_returns_none_for_another_apps_file(ws_root, settings):
    """A same-named file written by something else must not be trusted."""
    other = ws_root / "not-ours"
    other.mkdir()
    paths.sentinel_path(other).write_text(json.dumps({"app": "something-else"}))
    assert paths.read_sentinel(other) is None


def test_read_sentinel_returns_none_for_malformed_json(ws_root):
    other = ws_root / "not-ours"
    other.mkdir()
    paths.sentinel_path(other).write_text("{not json")
    assert paths.read_sentinel(other) is None


def test_assert_deletable_accepts_a_sentinelled_directory(workspace):
    assert paths.assert_deletable(workspace) == workspace.resolve()


def test_assert_deletable_refuses_without_a_sentinel(ws_root):
    """The single most important guard: never delete what we did not create."""
    users_own_work = ws_root / "my-important-project"
    users_own_work.mkdir()
    (users_own_work / "thesis.txt").write_text("years of work")

    with pytest.raises(NotDeletableError, match="sentinel"):
        paths.assert_deletable(users_own_work)
    assert (users_own_work / "thesis.txt").exists()


def test_assert_deletable_refuses_a_running_session(workspace):
    with pytest.raises(NotDeletableError, match="still running"):
        paths.assert_deletable(workspace, active_session_ids={42})


def test_assert_deletable_allows_when_another_session_is_running(workspace):
    assert paths.assert_deletable(workspace, active_session_ids={99}) == workspace.resolve()


def test_assert_deletable_refuses_a_missing_directory(ws_root):
    with pytest.raises(NotDeletableError, match="Not a directory"):
        paths.assert_deletable(ws_root / "gone")


def test_destroy_removes_a_sentinelled_workspace(workspace):
    (workspace / "app").mkdir()
    (workspace / "app" / "models.py").write_text("x = 1")

    paths.destroy(workspace)
    assert not workspace.exists()


def test_destroy_refuses_and_leaves_the_tree_intact(ws_root):
    """Verify destroy is gated, not just assert_deletable."""
    users_own_work = ws_root / "my-important-project"
    users_own_work.mkdir()
    (users_own_work / "thesis.txt").write_text("years of work")

    with pytest.raises(NotDeletableError):
        paths.destroy(users_own_work)
    assert (users_own_work / "thesis.txt").read_text() == "years of work"


def test_destroy_refuses_the_workspace_root(ws_root):
    with pytest.raises(UnsafePathError):
        paths.destroy(ws_root)
    assert ws_root.exists()


# ---------------------------------------------------------------------------
# safe_join (the file-preview endpoint's guard)
# ---------------------------------------------------------------------------


def test_safe_join_resolves_a_normal_relative_path(workspace):
    (workspace / "app").mkdir()
    target = workspace / "app" / "models.py"
    target.write_text("x = 1")
    assert paths.safe_join(workspace, "app/models.py") == target.resolve()


def test_safe_join_rejects_traversal_to_etc_passwd(workspace):
    """The attack this function exists to stop."""
    with pytest.raises(UnsafePathError, match=r"\.\."):
        paths.safe_join(workspace, "../../../../etc/passwd")


def test_safe_join_rejects_an_absolute_path(workspace):
    with pytest.raises(UnsafePathError, match="relative"):
        paths.safe_join(workspace, "/etc/passwd")


def test_safe_join_rejects_a_symlink_out_of_the_workspace(workspace, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("token")
    (workspace / "link.txt").symlink_to(secret)
    with pytest.raises(UnsafePathError, match="symlink"):
        paths.safe_join(workspace, "link.txt")


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("number", "slug", "expected"),
    [
        (1, "fix-stale-cache", "ex-001-fix-stale-cache"),
        (17, "ex-017-tenant-isolation", "ex-017-tenant-isolation"),
        (50, "ex-7-mislabelled", "ex-050-mislabelled"),
    ],
)
def test_session_dir_name(number, slug, expected):
    assert paths.session_dir_name(number, slug) == expected
