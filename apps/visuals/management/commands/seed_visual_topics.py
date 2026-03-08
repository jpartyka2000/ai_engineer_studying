"""
Management command to seed initial visual topics.

This command:
1. Enables supports_visuals=True for all active subjects
2. Creates sample visual topics for Git, scikit-learn, transformers, LightGBM, and System Design
"""

from django.core.management.base import BaseCommand

from apps.subjects.models import Subject
from apps.visuals.models import VisualTopic


class Command(BaseCommand):
    """Seed visual topics for subjects with visual support."""

    help = "Seed initial visual topics and enable visuals for all subjects"

    def handle(self, *args, **options):
        """Execute the command."""
        self.stdout.write("Enabling visuals for all active subjects...")
        self.enable_visuals_for_all_subjects()

        self.stdout.write("Seeding visual topics...")
        self.seed_git_visuals()
        self.seed_git_rebase_visual()
        self.seed_git_reset_visual()
        self.seed_git_fetch_vs_pull_visual()
        self.seed_git_cherry_pick_visual()
        self.seed_git_feature_branch_workflow_visual()
        self.seed_git_update_feature_branch_visual()
        self.seed_git_merge_conflicts_visual()
        self.seed_sklearn_visuals()
        self.seed_decision_tree_fundamentals_visual()
        self.seed_cart_visual()
        self.seed_random_forest_visual()
        self.seed_extra_trees_visual()
        self.seed_logistic_regression_visual()
        self.seed_isolation_forest_visual()
        self.seed_transformers_visuals()
        self.seed_lightgbm_visuals()
        self.seed_lightgbm_tree_growth_visual()
        self.seed_lightgbm_parallel_training_visual()
        self.seed_system_design_visuals()
        self.seed_gpu_generations_visual()
        self.seed_gpu_architecture_visual()

        self.stdout.write(self.style.SUCCESS("Successfully seeded visual topics!"))

    def enable_visuals_for_all_subjects(self):
        """Enable supports_visuals for all active subjects."""
        count = Subject.objects.filter(is_active=True).update(supports_visuals=True)
        self.stdout.write(f"  Enabled visuals for {count} subjects")

    def get_or_create_subject(self, name: str, slug: str, category: str) -> Subject:
        """Get or create a subject by slug."""
        subject, created = Subject.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "category": category,
                "description": f"Learn {name} concepts",
                "supports_visuals": True,
            },
        )
        if not subject.supports_visuals:
            subject.supports_visuals = True
            subject.save(update_fields=["supports_visuals"])
        return subject

    def seed_git_visuals(self):
        """Seed Git visual topics."""
        subject = self.get_or_create_subject("Git", "git", "DevOps & Tooling")

        # Git Branches and HEAD
        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="git-branches-head",
            defaults={
                "title": "Git Branches and HEAD",
                "description": "Learn how Git branches work and what the HEAD pointer means",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "beginner",
                "estimated_time_minutes": 5,
                "tags": ["git", "branches", "HEAD", "version-control"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "Initial Repository",
                        "explanation": "A new Git repository starts with a single commit on the `main` branch. **HEAD** is a special pointer that tells Git which branch (and commit) you're currently working on.",
                        "diagram_data": 'gitGraph\n    commit id: "C0" tag: "HEAD -> main"',
                    },
                    {
                        "step_number": 1,
                        "title": "Adding Commits",
                        "explanation": "Each new commit you make gets added to the current branch. The branch pointer (`main`) moves forward to the new commit, and HEAD follows along since it points to the branch.",
                        "diagram_data": 'gitGraph\n    commit id: "C0"\n    commit id: "C1"\n    commit id: "C2" tag: "HEAD -> main"',
                    },
                    {
                        "step_number": 2,
                        "title": "Creating a Branch",
                        "explanation": "When you create a new branch with `git branch feature`, Git creates a new pointer at the current commit. However, HEAD still points to `main` - you haven't switched branches yet.",
                        "diagram_data": 'gitGraph\n    commit id: "C0"\n    commit id: "C1"\n    commit id: "C2" tag: "main, feature"\n    branch feature',
                    },
                    {
                        "step_number": 3,
                        "title": "Switching Branches (Checkout)",
                        "explanation": "Running `git checkout feature` (or `git switch feature`) moves HEAD to point to the `feature` branch. Your working directory now reflects the state of that branch.",
                        "diagram_data": 'gitGraph\n    commit id: "C0"\n    commit id: "C1"\n    commit id: "C2" tag: "main"\n    branch feature\n    checkout feature\n    commit id: "" tag: "HEAD -> feature"',
                    },
                    {
                        "step_number": 4,
                        "title": "Working on Feature Branch",
                        "explanation": "Now when you make commits, they go on the `feature` branch. The `main` branch stays where it was. This is how Git enables parallel development.",
                        "diagram_data": 'gitGraph\n    commit id: "C0"\n    commit id: "C1"\n    commit id: "C2" tag: "main"\n    branch feature\n    checkout feature\n    commit id: "C3"\n    commit id: "C4" tag: "HEAD -> feature"',
                    },
                    {
                        "step_number": 5,
                        "title": "Merging Branches",
                        "explanation": "When your feature is complete, you can merge it back into `main`. First checkout main, then run `git merge feature`. Git creates a merge commit that combines both histories.",
                        "diagram_data": 'gitGraph\n    commit id: "C0"\n    commit id: "C1"\n    commit id: "C2"\n    branch feature\n    checkout feature\n    commit id: "C3"\n    commit id: "C4"\n    checkout main\n    merge feature id: "C5" tag: "HEAD -> main"',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_git_rebase_visual(self):
        """Seed Git rebase visual topic."""
        subject = self.get_or_create_subject("Git", "git", "DevOps & Tooling")

        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="git-rebase",
            defaults={
                "title": "Git Rebase: Rewriting History",
                "description": "Learn how git rebase works and when to use it instead of merge",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "intermediate",
                "estimated_time_minutes": 8,
                "tags": ["git", "rebase", "merge", "history"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "Starting Point: Diverged Branches",
                        "explanation": "You have a **feature branch** that diverged from **main**. Both branches have new commits. This is a common scenario when working on a feature while others merge to main.",
                        "diagram_data": 'gitGraph\n    commit id: "A"\n    commit id: "B"\n    branch feature\n    checkout feature\n    commit id: "C"\n    commit id: "D"\n    checkout main\n    commit id: "E"\n    commit id: "F" tag: "main"',
                    },
                    {
                        "step_number": 1,
                        "title": "The Merge Approach",
                        "explanation": "With **git merge**, you create a merge commit that combines both histories. The commit history shows the parallel development. This preserves the true history but can create a cluttered log.",
                        "diagram_data": 'gitGraph\n    commit id: "A"\n    commit id: "B"\n    branch feature\n    checkout feature\n    commit id: "C"\n    commit id: "D"\n    checkout main\n    commit id: "E"\n    commit id: "F"\n    merge feature id: "M" tag: "merge commit"',
                    },
                    {
                        "step_number": 2,
                        "title": "The Rebase Approach",
                        "explanation": 'With **git rebase main**, you "replay" your feature commits on top of main. It\'s like saying: "pretend I started my work from the latest main." This creates a **linear history**.',
                        "diagram_data": 'gitGraph\n    commit id: "A"\n    commit id: "B"\n    commit id: "E"\n    commit id: "F" tag: "main"\n    commit id: "C\'" type: HIGHLIGHT\n    commit id: "D\'" tag: "feature" type: HIGHLIGHT',
                    },
                    {
                        "step_number": 3,
                        "title": "How Rebase Works (Step 1)",
                        "explanation": "Git first finds the **common ancestor** (commit B) of your branch and the target branch. Then it temporarily saves your commits (C, D) as patches.",
                        "diagram_data": 'gitGraph\n    commit id: "A"\n    commit id: "B" tag: "common ancestor"\n    branch feature\n    checkout feature\n    commit id: "C (saved)"\n    commit id: "D (saved)"\n    checkout main\n    commit id: "E"\n    commit id: "F" tag: "rebase onto here"',
                    },
                    {
                        "step_number": 4,
                        "title": "How Rebase Works (Step 2)",
                        "explanation": "Git moves your branch pointer to the tip of main (commit F). Then it **replays** each of your commits, one by one, creating new commits C' and D' with new hashes.",
                        "diagram_data": 'gitGraph\n    commit id: "A"\n    commit id: "B"\n    commit id: "E"\n    commit id: "F"\n    commit id: "C\' (replayed)" type: HIGHLIGHT\n    commit id: "D\' (replayed)" tag: "feature" type: HIGHLIGHT',
                    },
                    {
                        "step_number": 5,
                        "title": "Handling Conflicts",
                        "explanation": "If a conflict occurs during replay, Git pauses and lets you resolve it. After fixing conflicts: **git add .** then **git rebase --continue**. Use **git rebase --abort** to cancel.",
                        "diagram_data": "flowchart TD\n    A[git rebase main] --> B{Conflict?}\n    B -->|No| C[Commit replayed]\n    B -->|Yes| D[CONFLICT - Rebase paused]\n    D --> E[Fix conflicts manually]\n    E --> F[git add .]\n    F --> G[git rebase --continue]\n    G --> B\n    D --> H[git rebase --abort]\n    H --> I[Back to original state]\n    style D fill:#FFB6C1\n    style G fill:#90EE90",
                    },
                    {
                        "step_number": 6,
                        "title": "Interactive Rebase: Squashing Commits",
                        "explanation": "Use **git rebase -i HEAD~3** to modify the last 3 commits. You can **squash** (combine), **reword** (edit message), **edit** (amend), **drop** (delete), or **reorder** commits.",
                        "diagram_data": 'flowchart LR\n    subgraph Before\n    A1["fix typo"]\n    A2["add feature"]\n    A3["fix typo again"]\n    end\n    subgraph "git rebase -i"\n    B1["pick: add feature"]\n    B2["squash: fix typo"]\n    B3["squash: fix typo again"]\n    end\n    subgraph After\n    C1["add feature (clean)"]\n    end\n    Before --> B1\n    B1 --> After\n    style C1 fill:#90EE90',
                    },
                    {
                        "step_number": 7,
                        "title": "The Golden Rule of Rebasing",
                        "explanation": "**Never rebase commits that have been pushed and shared with others.** Rebase rewrites history (new commit hashes). If others based work on the old commits, you'll cause conflicts and confusion.",
                        "diagram_data": 'flowchart TD\n    subgraph "Safe to Rebase"\n    A[Local commits not pushed]\n    B[Your own feature branch]\n    C[Before opening PR]\n    end\n    subgraph "NEVER Rebase"\n    D[Commits on main/master]\n    E[Shared branches]\n    F[After PR is merged]\n    end\n    style A fill:#90EE90\n    style B fill:#90EE90\n    style C fill:#90EE90\n    style D fill:#FFB6C1\n    style E fill:#FFB6C1\n    style F fill:#FFB6C1',
                    },
                    {
                        "step_number": 8,
                        "title": "Rebase vs Merge: When to Use Each",
                        "explanation": "Use **rebase** for: cleaning up local commits, keeping feature branch up-to-date, linear history preference. Use **merge** for: preserving complete history, shared branches, when history matters.",
                        "diagram_data": 'flowchart TD\n    Q{What are you doing?}\n    Q -->|"Updating feature branch<br/>with latest main"| R1["git rebase main<br/>(if not shared)"]\n    Q -->|"Integrating feature<br/>into main"| R2["git merge feature<br/>(preserves history)"]\n    Q -->|"Cleaning up commits<br/>before PR"| R3["git rebase -i<br/>(squash/reword)"]\n    Q -->|"Shared branch or<br/>already pushed"| R4["git merge<br/>(safer)"]\n    style R1 fill:#ADD8E6\n    style R2 fill:#90EE90\n    style R3 fill:#ADD8E6\n    style R4 fill:#90EE90',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_git_reset_visual(self):
        """Seed Git reset visual topic."""
        subject = self.get_or_create_subject("Git", "git", "DevOps & Tooling")

        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="git-reset",
            defaults={
                "title": "Git Reset: Soft, Mixed, and Hard",
                "description": "Understand the three reset modes and how they affect HEAD, staging, and working directory",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "intermediate",
                "estimated_time_minutes": 7,
                "tags": ["git", "reset", "undo", "HEAD"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "The Three Trees of Git",
                        "explanation": 'Git manages three "trees" (file collections): **Working Directory** (your files), **Staging Area/Index** (next commit), and **Repository/HEAD** (last commit). Understanding these is key to understanding reset.',
                        "diagram_data": 'flowchart LR\n    subgraph "Three Trees"\n    WD["Working Directory<br/>(Your Files)"]\n    SA["Staging Area<br/>(Index)"]\n    REPO["Repository<br/>(HEAD Commit)"]\n    end\n    WD -->|git add| SA\n    SA -->|git commit| REPO\n    style WD fill:#90EE90\n    style SA fill:#FFFACD\n    style REPO fill:#ADD8E6',
                    },
                    {
                        "step_number": 1,
                        "title": "Starting State",
                        "explanation": "Let's say you have 3 commits (A→B→C) and HEAD points to C. All three trees are in sync - working directory, staging area, and HEAD all have the same content.",
                        "diagram_data": 'gitGraph\n    commit id: "A"\n    commit id: "B"\n    commit id: "C" tag: "HEAD"',
                    },
                    {
                        "step_number": 2,
                        "title": "Git Reset --soft",
                        "explanation": '**--soft** only moves HEAD to the target commit. Staging area and working directory are **untouched**. Your changes appear as "staged for commit". Use this to redo a commit message or combine commits.',
                        "diagram_data": 'flowchart TB\n    subgraph "After: git reset --soft B"\n    HEAD2["HEAD → B"]\n    STAGE2["Staging: C\'s changes<br/>(ready to commit)"]\n    WORK2["Working Dir: C\'s changes"]\n    end\n    subgraph Legend\n    L1["Moved"]\n    L2["Unchanged"]\n    end\n    style HEAD2 fill:#FFB6C1\n    style STAGE2 fill:#90EE90\n    style WORK2 fill:#90EE90\n    style L1 fill:#FFB6C1\n    style L2 fill:#90EE90',
                    },
                    {
                        "step_number": 3,
                        "title": "Soft Reset Use Case",
                        "explanation": "Made a commit but want to change the message or add more files? Use **git reset --soft HEAD~1** to undo the commit but keep everything staged. Then commit again with the right message.",
                        "diagram_data": 'flowchart LR\n    A["Oops, wrong commit message"] --> B["git reset --soft HEAD~1"]\n    B --> C["Changes still staged"]\n    C --> D["git commit -m \'Better message\'"]\n    style D fill:#90EE90',
                    },
                    {
                        "step_number": 4,
                        "title": "Git Reset --mixed (Default)",
                        "explanation": '**--mixed** (the default) moves HEAD and resets the staging area, but leaves working directory **untouched**. Changes appear as "unstaged". Use this to unstage files or reorganize what goes into commits.',
                        "diagram_data": 'flowchart TB\n    subgraph "After: git reset --mixed B"\n    HEAD3["HEAD → B"]\n    STAGE3["Staging: Empty<br/>(matches B)"]\n    WORK3["Working Dir: C\'s changes<br/>(unstaged)"]\n    end\n    subgraph Legend\n    L1["Moved/Reset"]\n    L2["Unchanged"]\n    end\n    style HEAD3 fill:#FFB6C1\n    style STAGE3 fill:#FFB6C1\n    style WORK3 fill:#90EE90\n    style L1 fill:#FFB6C1\n    style L2 fill:#90EE90',
                    },
                    {
                        "step_number": 5,
                        "title": "Mixed Reset Use Case",
                        "explanation": "Accidentally staged files you didn't want? Or want to split a big commit into smaller ones? Use **git reset HEAD~1** (mixed is default) to unstage and re-add files selectively.",
                        "diagram_data": 'flowchart LR\n    A["Committed too many files"] --> B["git reset HEAD~1"]\n    B --> C["All changes unstaged"]\n    C --> D["git add file1.py"]\n    D --> E["git commit -m \'First part\'"]\n    E --> F["git add file2.py"]\n    F --> G["git commit -m \'Second part\'"]\n    style E fill:#90EE90\n    style G fill:#90EE90',
                    },
                    {
                        "step_number": 6,
                        "title": "Git Reset --hard",
                        "explanation": "**--hard** moves HEAD, resets staging area, AND resets working directory. All changes are **discarded**. This is destructive - uncommitted work is lost! Use with caution.",
                        "diagram_data": 'flowchart TB\n    subgraph "After: git reset --hard B"\n    HEAD4["HEAD → B"]\n    STAGE4["Staging: Empty<br/>(matches B)"]\n    WORK4["Working Dir: B\'s content<br/>(C\'s changes GONE)"]\n    end\n    subgraph Legend\n    L1["Moved/Reset"]\n    L2["DESTROYED"]\n    end\n    style HEAD4 fill:#FFB6C1\n    style STAGE4 fill:#FFB6C1\n    style WORK4 fill:#FFB6C1\n    style L1 fill:#FFB6C1\n    style L2 fill:#FF0000',
                    },
                    {
                        "step_number": 7,
                        "title": "Hard Reset Use Case",
                        "explanation": "Want to completely abandon recent work and go back? **git reset --hard HEAD~2** throws away the last 2 commits entirely. Or **git reset --hard origin/main** to match the remote exactly.",
                        "diagram_data": 'flowchart LR\n    A["Made a mess of things"] --> B["git reset --hard origin/main"]\n    B --> C["Local matches remote exactly"]\n    C --> D["All local changes gone"]\n    style D fill:#FFB6C1',
                    },
                    {
                        "step_number": 8,
                        "title": "Comparison Summary",
                        "explanation": "Quick reference: **--soft** keeps everything, **--mixed** unstages but keeps files, **--hard** destroys everything. When in doubt, start with --soft - you can always go harder.",
                        "diagram_data": 'flowchart TB\n    subgraph "git reset --soft"\n    S1["HEAD: Moved"]\n    S2["Staging: Unchanged"]\n    S3["Working: Unchanged"]\n    end\n    subgraph "git reset --mixed"\n    M1["HEAD: Moved"]\n    M2["Staging: Reset"]\n    M3["Working: Unchanged"]\n    end\n    subgraph "git reset --hard"\n    H1["HEAD: Moved"]\n    H2["Staging: Reset"]\n    H3["Working: Reset"]\n    end\n    style S1 fill:#FFB6C1\n    style S2 fill:#90EE90\n    style S3 fill:#90EE90\n    style M1 fill:#FFB6C1\n    style M2 fill:#FFB6C1\n    style M3 fill:#90EE90\n    style H1 fill:#FFB6C1\n    style H2 fill:#FFB6C1\n    style H3 fill:#FFB6C1',
                    },
                    {
                        "step_number": 9,
                        "title": "Recovery with Reflog",
                        "explanation": "Accidentally did a hard reset? Git reflog tracks all HEAD movements. Find the lost commit hash with **git reflog** and recover with **git reset --hard <hash>**. Commits aren't truly gone until garbage collected (~30 days).",
                        "diagram_data": 'flowchart TD\n    A["Oops! git reset --hard"] --> B["git reflog"]\n    B --> C["See: abc123 HEAD@{1}: commit: My work"]\n    C --> D["git reset --hard abc123"]\n    D --> E["Work recovered!"]\n    style A fill:#FFB6C1\n    style E fill:#90EE90',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_git_fetch_vs_pull_visual(self):
        """Seed Git fetch vs pull visual topic."""
        subject = self.get_or_create_subject("Git", "git", "DevOps & Tooling")

        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="git-fetch-vs-pull",
            defaults={
                "title": "Git Fetch vs Pull",
                "description": "Understand the difference between fetch and pull, and when to use each",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "beginner",
                "estimated_time_minutes": 5,
                "tags": ["git", "fetch", "pull", "remote"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "The Setup: Local and Remote",
                        "explanation": "You have a **local repository** on your machine and a **remote repository** (like GitHub). Your local repo has **remote-tracking branches** (like origin/main) that remember where the remote branches were last time you checked.",
                        "diagram_data": 'flowchart LR\n    subgraph "Your Machine"\n    LOCAL["Local Repo<br/>main branch"]\n    TRACK["origin/main<br/>(tracking branch)"]\n    end\n    subgraph "GitHub"\n    REMOTE["Remote Repo<br/>main branch"]\n    end\n    TRACK -.->|"tracks"| REMOTE\n    style LOCAL fill:#90EE90\n    style TRACK fill:#FFFACD\n    style REMOTE fill:#ADD8E6',
                    },
                    {
                        "step_number": 1,
                        "title": "Starting State",
                        "explanation": "Both local and remote are at commit B. Someone else pushes commit C to the remote. Now the remote is ahead, but your local repo doesn't know yet.",
                        "diagram_data": 'flowchart LR\n    subgraph "Local (outdated)"\n    L1["A"] --> L2["B"]\n    L2 --> LH["main, origin/main"]\n    end\n    subgraph "Remote (ahead)"\n    R1["A"] --> R2["B"] --> R3["C"]\n    R3 --> RH["main"]\n    end\n    style R3 fill:#90EE90\n    style LH fill:#FFFACD',
                    },
                    {
                        "step_number": 2,
                        "title": "Git Fetch: Download Only",
                        "explanation": "**git fetch** downloads new commits from the remote and updates your **remote-tracking branch** (origin/main). It does NOT touch your local main branch. Safe and non-destructive.",
                        "diagram_data": 'flowchart LR\n    subgraph "After: git fetch"\n    L1["A"] --> L2["B"]\n    L2 --> LH["main (unchanged)"]\n    L2 --> L3["C"]\n    L3 --> OH["origin/main (updated)"]\n    end\n    style L3 fill:#90EE90\n    style OH fill:#90EE90\n    style LH fill:#FFFACD',
                    },
                    {
                        "step_number": 3,
                        "title": "After Fetch: You Decide",
                        "explanation": "After fetching, you can inspect what changed before merging. Use **git log origin/main** or **git diff main origin/main** to see what's new. Then merge when ready.",
                        "diagram_data": 'flowchart TD\n    A["git fetch origin"] --> B["origin/main updated"]\n    B --> C{"Review changes?"}\n    C -->|"git log origin/main"| D["See new commits"]\n    C -->|"git diff main origin/main"| E["See code changes"]\n    D --> F["git merge origin/main"]\n    E --> F\n    F --> G["Local main updated"]\n    style A fill:#ADD8E6\n    style G fill:#90EE90',
                    },
                    {
                        "step_number": 4,
                        "title": "Git Pull: Fetch + Merge",
                        "explanation": "**git pull** is simply **git fetch** followed by **git merge**. It downloads AND immediately integrates the changes into your current branch. Convenient but gives you less control.",
                        "diagram_data": 'flowchart LR\n    subgraph "git pull = fetch + merge"\n    FETCH["git fetch"]\n    MERGE["git merge origin/main"]\n    FETCH --> MERGE\n    end\n    style FETCH fill:#ADD8E6\n    style MERGE fill:#90EE90',
                    },
                    {
                        "step_number": 5,
                        "title": "Pull Result",
                        "explanation": "After **git pull**, your local main is updated to include the remote changes. If there were no local commits, it's a simple fast-forward. Otherwise, a merge commit may be created.",
                        "diagram_data": 'flowchart LR\n    subgraph "After: git pull (fast-forward)"\n    L1["A"] --> L2["B"] --> L3["C"]\n    L3 --> LH["main, origin/main"]\n    end\n    style L3 fill:#90EE90\n    style LH fill:#90EE90',
                    },
                    {
                        "step_number": 6,
                        "title": "When Branches Diverge",
                        "explanation": "If you have local commits AND the remote has new commits, **git pull** will create a **merge commit**. This can clutter history. Some teams prefer **git pull --rebase** for a linear history.",
                        "diagram_data": 'flowchart TB\n    subgraph "Before Pull (diverged)"\n    B1["A"] --> B2["B"]\n    B2 --> B3["C (local)"]\n    B2 --> B4["D (remote)"]\n    end\n    subgraph "After git pull"\n    A1["A"] --> A2["B"]\n    A2 --> A3["C"]\n    A2 --> A4["D"]\n    A3 --> A5["M (merge)"]\n    A4 --> A5\n    end\n    style A5 fill:#FFFACD',
                    },
                    {
                        "step_number": 7,
                        "title": "Git Pull --rebase",
                        "explanation": "**git pull --rebase** fetches then rebases your local commits on top of the remote changes. This creates a linear history without merge commits. Popular for keeping a clean git log.",
                        "diagram_data": 'flowchart TB\n    subgraph "Before"\n    B1["A"] --> B2["B"]\n    B2 --> B3["C (local)"]\n    B2 --> B4["D (remote)"]\n    end\n    subgraph "After git pull --rebase"\n    A1["A"] --> A2["B"] --> A4["D"] --> A3["C\' (rebased)"]\n    end\n    style A3 fill:#90EE90',
                    },
                    {
                        "step_number": 8,
                        "title": "When to Use Each",
                        "explanation": "Use **fetch** when: you want to review changes first, working on shared branch, or CI/CD scripts. Use **pull** when: you trust incoming changes, working alone, want convenience. Use **pull --rebase** for linear history.",
                        "diagram_data": 'flowchart TD\n    Q{"What do you need?"}\n    Q -->|"Review before integrating"| F["git fetch<br/>then git merge"]\n    Q -->|"Quick update, trust remote"| P["git pull"]\n    Q -->|"Update + linear history"| PR["git pull --rebase"]\n    Q -->|"Just see what\'s new"| FO["git fetch<br/>git log origin/main"]\n    style F fill:#ADD8E6\n    style P fill:#90EE90\n    style PR fill:#FFFACD\n    style FO fill:#E6E6FA',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_git_cherry_pick_visual(self):
        """Seed Git cherry-pick visual topic."""
        subject = self.get_or_create_subject("Git", "git", "DevOps & Tooling")

        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="git-cherry-pick",
            defaults={
                "title": "Git Cherry-pick: Selective Commit Copying",
                "description": "Learn how to copy specific commits from one branch to another with cherry-pick",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "intermediate",
                "estimated_time_minutes": 7,
                "tags": ["git", "cherry-pick", "commits", "branches"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "What is Cherry-pick?",
                        "explanation": "**Git cherry-pick** copies a specific commit from one branch and applies it to another branch. Unlike merge (which brings all commits) or rebase (which moves your branch), cherry-pick lets you pick individual commits.",
                        "diagram_data": 'flowchart LR\n    subgraph "Cherry-pick Concept"\n    TREE["Branch with many commits"]\n    CHERRY["Pick ONE specific commit"]\n    TARGET["Apply to your branch"]\n    end\n    TREE --> CHERRY --> TARGET\n    style CHERRY fill:#FFB6C1',
                    },
                    {
                        "step_number": 1,
                        "title": "Starting Scenario",
                        "explanation": "You're on **main** branch and need a specific bug fix (commit D) from the **feature** branch, but you don't want all the feature commits yet. This is a perfect use case for cherry-pick.",
                        "diagram_data": 'gitGraph\n    commit id: "A"\n    commit id: "B" tag: "main"\n    branch feature\n    checkout feature\n    commit id: "C" type: NORMAL\n    commit id: "D (bug fix)" type: HIGHLIGHT\n    commit id: "E" type: NORMAL',
                    },
                    {
                        "step_number": 2,
                        "title": "Find the Commit Hash",
                        "explanation": "First, identify the commit you want to cherry-pick using **git log**. Each commit has a unique SHA hash. You can use the full hash or the first 7 characters.",
                        "diagram_data": 'flowchart TD\n    A["git log feature --oneline"] --> B["Output:"]\n    B --> C["abc123e E - Add feature tests"]\n    B --> D["def456d D - Fix critical bug"]\n    B --> E["ghi789c C - Start feature work"]\n    D --> F["Copy: def456d"]\n    style D fill:#90EE90\n    style F fill:#90EE90',
                    },
                    {
                        "step_number": 3,
                        "title": "Execute Cherry-pick",
                        "explanation": "Run **git cherry-pick <commit-hash>** while on your target branch. Git creates a NEW commit with the same changes but a different hash. The original commit stays on its branch.",
                        "diagram_data": 'gitGraph\n    commit id: "A"\n    commit id: "B"\n    branch feature\n    checkout feature\n    commit id: "C"\n    commit id: "D (bug fix)"\n    commit id: "E"\n    checkout main\n    commit id: "D\'" tag: "main" type: HIGHLIGHT',
                    },
                    {
                        "step_number": 4,
                        "title": "Cherry-pick vs Original",
                        "explanation": "The cherry-picked commit (D') has the **same code changes** and **same commit message** as the original (D), but a **different SHA hash** because it has different parent commits. They're copies, not the same commit.",
                        "diagram_data": 'flowchart LR\n    subgraph "Feature Branch"\n    D["Commit D<br/>SHA: def456d<br/>Parent: C"]\n    end\n    subgraph "Main Branch"\n    DP["Commit D\'<br/>SHA: xyz789a<br/>Parent: B"]\n    end\n    D -->|"Same changes<br/>Different hash"| DP\n    style D fill:#ADD8E6\n    style DP fill:#90EE90',
                    },
                    {
                        "step_number": 5,
                        "title": "Cherry-picking Multiple Commits",
                        "explanation": "You can cherry-pick multiple commits in sequence. List them individually or use a range. Order matters - commits are applied in the order you specify.",
                        "diagram_data": 'flowchart TD\n    subgraph "Single commits"\n    S1["git cherry-pick abc123"]\n    S2["git cherry-pick def456 ghi789"]\n    end\n    subgraph "Range of commits"\n    R1["git cherry-pick abc123..def456"]\n    R2["(excludes abc123, includes def456)"]\n    end\n    subgraph "Range inclusive"\n    I1["git cherry-pick abc123^..def456"]\n    I2["(includes both endpoints)"]\n    end\n    style S1 fill:#ADD8E6\n    style R1 fill:#FFFACD\n    style I1 fill:#90EE90',
                    },
                    {
                        "step_number": 6,
                        "title": "Handling Conflicts",
                        "explanation": "If the cherry-picked changes conflict with your branch, Git pauses and asks you to resolve them. After fixing conflicts, use **git add** then **git cherry-pick --continue**.",
                        "diagram_data": 'flowchart TD\n    A["git cherry-pick abc123"] --> B{Conflict?}\n    B -->|No| C["Commit created automatically"]\n    B -->|Yes| D["CONFLICT - Cherry-pick paused"]\n    D --> E["Fix conflicts in files"]\n    E --> F["git add ."]\n    F --> G["git cherry-pick --continue"]\n    G --> C\n    D --> H["git cherry-pick --abort"]\n    H --> I["Cancel and restore original state"]\n    style D fill:#FFB6C1\n    style C fill:#90EE90\n    style H fill:#FFFACD',
                    },
                    {
                        "step_number": 7,
                        "title": "Useful Options",
                        "explanation": "Cherry-pick has helpful options: **-n / --no-commit** stages changes without committing (useful for combining), **-x** adds source commit info to message, **-e** lets you edit the commit message.",
                        "diagram_data": 'flowchart TB\n    subgraph "Common Options"\n    O1["--no-commit (-n)<br/>Stage changes only, don\'t commit"]\n    O2["-x<br/>Add \'cherry picked from...\' to message"]\n    O3["--edit (-e)<br/>Edit commit message before committing"]\n    O4["--signoff (-s)<br/>Add Signed-off-by line"]\n    end\n    subgraph "Example"\n    E1["git cherry-pick -x abc123"]\n    E2["Message includes:<br/>cherry picked from commit abc123"]\n    end\n    O2 --> E1 --> E2\n    style O1 fill:#ADD8E6\n    style O2 fill:#90EE90\n    style O3 fill:#FFFACD',
                    },
                    {
                        "step_number": 8,
                        "title": "Common Use Cases",
                        "explanation": "Cherry-pick is ideal for: **hotfixes** (apply bug fix to release branch), **backporting** (bring feature to older version), **selective integration** (pick specific commits from PRs), and **undoing mistakes** (revert then cherry-pick good commits).",
                        "diagram_data": 'flowchart TD\n    subgraph "Hotfix Scenario"\n    H1["Bug found in production"]\n    H2["Fix made on develop"]\n    H3["Cherry-pick fix to release branch"]\n    H1 --> H2 --> H3\n    end\n    subgraph "Backport Scenario"\n    B1["New feature on main"]\n    B2["Customer needs it on v2.x"]\n    B3["Cherry-pick to release/2.x"]\n    B1 --> B2 --> B3\n    end\n    style H3 fill:#90EE90\n    style B3 fill:#ADD8E6',
                    },
                    {
                        "step_number": 9,
                        "title": "Cherry-pick vs Merge vs Rebase",
                        "explanation": "**Merge** brings all commits and preserves branch history. **Rebase** moves entire branch to new base. **Cherry-pick** copies specific commits individually. Use cherry-pick when you need surgical precision.",
                        "diagram_data": 'flowchart TD\n    Q{"What do you need?"}\n    Q -->|"All commits from branch"| M["git merge<br/>Preserves history"]\n    Q -->|"Move branch to new base"| R["git rebase<br/>Linear history"]\n    Q -->|"Just specific commits"| C["git cherry-pick<br/>Selective copying"]\n    subgraph "Cherry-pick is for"\n    C1["Hotfixes"]\n    C2["Backports"]\n    C3["Selective features"]\n    end\n    C --> C1\n    C --> C2\n    C --> C3\n    style M fill:#ADD8E6\n    style R fill:#FFFACD\n    style C fill:#90EE90',
                    },
                    {
                        "step_number": 10,
                        "title": "Potential Pitfalls",
                        "explanation": "Be careful: cherry-picking creates **duplicate commits** (same changes, different hashes). If you later merge the original branch, you may see the changes twice or get conflicts. Document cherry-picks with **-x** flag.",
                        "diagram_data": 'flowchart TD\n    subgraph "Warning: Duplicate Commits"\n    W1["Cherry-pick D to main as D\'"]\n    W2["Later merge feature to main"]\n    W3["Git sees D and D\' as different"]\n    W4["May cause conflicts or duplicates"]\n    end\n    W1 --> W2 --> W3 --> W4\n    subgraph "Best Practices"\n    BP1["Use -x flag for traceability"]\n    BP2["Document in PR/commit message"]\n    BP3["Consider if merge is better"]\n    end\n    style W4 fill:#FFB6C1\n    style BP1 fill:#90EE90\n    style BP2 fill:#90EE90',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_git_feature_branch_workflow_visual(self):
        """Seed Git feature branch workflow visual topic."""
        subject = self.get_or_create_subject("Git", "git", "DevOps & Tooling")

        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="git-feature-branch-workflow",
            defaults={
                "title": "Feature Branch Workflow",
                "description": "The standard Git workflow for team development: create branch, develop, open PR, merge",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "beginner",
                "estimated_time_minutes": 8,
                "tags": ["git", "workflow", "feature-branch", "pull-request", "team"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "The Feature Branch Workflow",
                        "explanation": "The most common Git workflow for teams: **main** branch is always deployable, all work happens on **feature branches**, changes are merged via **Pull Requests** after code review.",
                        "diagram_data": 'flowchart LR\n    subgraph "Feature Branch Workflow"\n    A["1. Create branch"] --> B["2. Make commits"]\n    B --> C["3. Push branch"]\n    C --> D["4. Open PR"]\n    D --> E["5. Code review"]\n    E --> F["6. Merge to main"]\n    end\n    style F fill:#90EE90',
                    },
                    {
                        "step_number": 1,
                        "title": "Step 1: Start from Updated Main",
                        "explanation": "Always start from the latest **main** branch. This ensures your feature branch has all recent changes and minimizes conflicts later.",
                        "diagram_data": 'flowchart TB\n    subgraph "Before Starting"\n    A["git checkout main"]\n    B["git pull origin main"]\n    C["Now you have latest code"]\n    end\n    A --> B --> C\n    subgraph "Main Branch"\n    M1["A"] --> M2["B"] --> M3["C"]\n    M3 --> HEAD["HEAD"]\n    end\n    style C fill:#90EE90\n    style HEAD fill:#ADD8E6',
                    },
                    {
                        "step_number": 2,
                        "title": "Step 2: Create Feature Branch",
                        "explanation": "Create a descriptive branch name. Common conventions: **feature/**, **fix/**, **chore/**. The branch starts at the same commit as main.",
                        "diagram_data": 'gitGraph\n    commit id: "A"\n    commit id: "B"\n    commit id: "C" tag: "main"\n    branch feature/user-auth\n    checkout feature/user-auth\n    commit id: "" tag: "HEAD"',
                    },
                    {
                        "step_number": 3,
                        "title": "Step 3: Develop on Feature Branch",
                        "explanation": "Make commits on your feature branch. Commit often with clear messages. Your work is isolated - it doesn't affect main or other developers until merged.",
                        "diagram_data": 'gitGraph\n    commit id: "A"\n    commit id: "B"\n    commit id: "C" tag: "main"\n    branch feature/user-auth\n    checkout feature/user-auth\n    commit id: "Add login form"\n    commit id: "Add validation"\n    commit id: "Add tests" tag: "HEAD"',
                    },
                    {
                        "step_number": 4,
                        "title": "Meanwhile: Main May Move Ahead",
                        "explanation": "While you work, other developers may merge their PRs to main. This is normal! We'll handle it before merging. Your branch and main have **diverged**.",
                        "diagram_data": 'gitGraph\n    commit id: "A"\n    commit id: "B"\n    commit id: "C"\n    branch feature/user-auth\n    checkout feature/user-auth\n    commit id: "D (your work)"\n    commit id: "E (your work)"\n    checkout main\n    commit id: "F (teammate)" tag: "main"\n    commit id: "G (teammate)"',
                    },
                    {
                        "step_number": 5,
                        "title": "Step 4: Push Branch to Remote",
                        "explanation": "Push your feature branch to the remote repository. Use **-u** flag the first time to set up tracking. This backs up your work and enables PR creation.",
                        "diagram_data": 'flowchart LR\n    subgraph "Local"\n    L["feature/user-auth<br/>commits D, E"]\n    end\n    subgraph "Remote (GitHub)"\n    R["origin/feature/user-auth<br/>commits D, E"]\n    end\n    L -->|"git push -u origin feature/user-auth"| R\n    style R fill:#90EE90',
                    },
                    {
                        "step_number": 6,
                        "title": "Step 5: Open Pull Request",
                        "explanation": "Create a **Pull Request** (PR) on GitHub/GitLab. Add a description of changes, link related issues, and request reviewers. The PR shows the diff between your branch and main.",
                        "diagram_data": 'flowchart TB\n    subgraph "Pull Request"\n    TITLE["Title: Add user authentication"]\n    DESC["Description:<br/>- Added login form<br/>- Added validation<br/>- Added tests"]\n    DIFF["Files changed: 5<br/>+200 -50 lines"]\n    REV["Reviewers: @alice, @bob"]\n    end\n    subgraph "PR Status"\n    S1["CI checks running..."]\n    S2["Awaiting review"]\n    end\n    style TITLE fill:#ADD8E6',
                    },
                    {
                        "step_number": 7,
                        "title": "Step 6: Code Review",
                        "explanation": "Teammates review your code, leave comments, and may request changes. Address feedback with new commits. The PR updates automatically when you push.",
                        "diagram_data": 'flowchart TB\n    subgraph "Review Process"\n    R1["Reviewer comments:<br/>\'Consider using async here\'"]\n    R2["You make changes"]\n    R3["Push new commit"]\n    R4["Reviewer approves ✓"]\n    end\n    R1 --> R2 --> R3 --> R4\n    subgraph "PR Updated"\n    P["Original commits + fix commit"]\n    end\n    R3 --> P\n    style R4 fill:#90EE90',
                    },
                    {
                        "step_number": 8,
                        "title": "Step 7: Update Branch if Needed",
                        "explanation": "If main has new commits, update your branch before merging. Either **merge main into feature** or **rebase feature onto main**. This ensures clean integration.",
                        "diagram_data": 'flowchart TB\n    Q{"Main has new commits?"}\n    Q -->|Yes| UPDATE["Update your branch"]\n    Q -->|No| READY["Ready to merge"]\n    UPDATE --> OPT1["Option 1: git merge main<br/>(creates merge commit)"]\n    UPDATE --> OPT2["Option 2: git rebase main<br/>(linear history)"]\n    OPT1 --> PUSH["git push"]\n    OPT2 --> PUSHF["git push --force-with-lease"]\n    PUSH --> READY\n    PUSHF --> READY\n    style READY fill:#90EE90',
                    },
                    {
                        "step_number": 9,
                        "title": "Step 8: Merge the PR",
                        "explanation": "Once approved and CI passes, merge the PR. Common strategies: **Merge commit** (preserves history), **Squash and merge** (clean history), **Rebase and merge** (linear history).",
                        "diagram_data": 'flowchart TB\n    subgraph "Merge Strategies"\n    M1["Merge commit<br/>Preserves all commits<br/>Shows branch history"]\n    M2["Squash and merge<br/>All commits → one commit<br/>Clean main history"]\n    M3["Rebase and merge<br/>Replay commits on main<br/>Linear history"]\n    end\n    M2 --> REC["Most common for<br/>feature branches"]\n    style M2 fill:#90EE90\n    style REC fill:#ADD8E6',
                    },
                    {
                        "step_number": 10,
                        "title": "After Merge: Clean Up",
                        "explanation": "After merging, **delete the feature branch** (GitHub can do this automatically). Update your local main and delete the local feature branch.",
                        "diagram_data": 'flowchart TB\n    A["PR merged!"] --> B["Delete remote branch<br/>(GitHub button or CLI)"]\n    B --> C["git checkout main"]\n    C --> D["git pull origin main"]\n    D --> E["git branch -d feature/user-auth"]\n    E --> F["Ready for next feature!"]\n    style F fill:#90EE90',
                    },
                    {
                        "step_number": 11,
                        "title": "Final Result",
                        "explanation": "Your feature is now part of main! If you used squash merge, it appears as a single commit. The feature branch is gone, and main has moved forward.",
                        "diagram_data": 'gitGraph\n    commit id: "A"\n    commit id: "B"\n    commit id: "C"\n    commit id: "F (teammate)"\n    commit id: "G (teammate)"\n    commit id: "Add user auth" tag: "main" type: HIGHLIGHT',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_git_update_feature_branch_visual(self):
        """Seed Git update feature branch visual topic."""
        subject = self.get_or_create_subject("Git", "git", "DevOps & Tooling")

        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="git-update-feature-branch",
            defaults={
                "title": "Keeping Your Feature Branch Updated",
                "description": "How to update your feature branch when main has moved ahead: merge vs rebase approaches",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "intermediate",
                "estimated_time_minutes": 8,
                "tags": ["git", "rebase", "merge", "feature-branch", "team"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "The Situation: Diverged Branches",
                        "explanation": "You're working on a feature branch while teammates merge changes to main. Your branch has **diverged** from main. Before merging your PR, you need to incorporate those main changes.",
                        "diagram_data": 'gitGraph\n    commit id: "A"\n    commit id: "B"\n    branch feature\n    checkout feature\n    commit id: "C (yours)"\n    commit id: "D (yours)"\n    checkout main\n    commit id: "E (teammate)"\n    commit id: "F (teammate)" tag: "main"',
                    },
                    {
                        "step_number": 1,
                        "title": "Why Update Your Branch?",
                        "explanation": "Updating ensures: (1) Your code works with latest main, (2) Conflicts are resolved NOW, not during merge, (3) CI tests against current main state, (4) Reviewers see the final integrated code.",
                        "diagram_data": 'flowchart TB\n    subgraph "Problems if you don\'t update"\n    P1["Conflicts discovered at merge time"]\n    P2["Your code may break with new main"]\n    P3["CI passes but merge fails"]\n    end\n    subgraph "Benefits of updating"\n    B1["Resolve conflicts early"]\n    B2["Test against real main"]\n    B3["Smooth merge"]\n    end\n    style P1 fill:#FFB6C1\n    style P2 fill:#FFB6C1\n    style B1 fill:#90EE90\n    style B3 fill:#90EE90',
                    },
                    {
                        "step_number": 2,
                        "title": "Two Approaches: Merge vs Rebase",
                        "explanation": "You have two options: **Merge main into feature** (easier, preserves history) or **Rebase feature onto main** (cleaner history, rewrites commits). Both achieve the same result.",
                        "diagram_data": 'flowchart TB\n    DIVERGED["Diverged branches"]\n    DIVERGED --> MERGE["Option 1: Merge"]\n    DIVERGED --> REBASE["Option 2: Rebase"]\n    MERGE --> M_RES["Creates merge commit<br/>Preserves exact history<br/>Easier for beginners"]\n    REBASE --> R_RES["Rewrites your commits<br/>Linear history<br/>Cleaner but advanced"]\n    style MERGE fill:#ADD8E6\n    style REBASE fill:#90EE90',
                    },
                    {
                        "step_number": 3,
                        "title": "Option 1: Merge Main into Feature",
                        "explanation": "Fetch latest main, then merge it INTO your feature branch. This creates a **merge commit** that combines both histories. Your original commits stay unchanged.",
                        "diagram_data": 'flowchart TB\n    subgraph "Commands"\n    C1["git checkout feature"]\n    C2["git fetch origin"]\n    C3["git merge origin/main"]\n    C4["# Resolve conflicts if any"]\n    C5["git push"]\n    end\n    C1 --> C2 --> C3 --> C4 --> C5\n    style C3 fill:#ADD8E6',
                    },
                    {
                        "step_number": 4,
                        "title": "Merge Result",
                        "explanation": "After merging main into feature, you have a **merge commit** (M) that combines both branches. Your commits C, D are unchanged. The feature branch now includes main's changes.",
                        "diagram_data": 'gitGraph\n    commit id: "A"\n    commit id: "B"\n    branch feature\n    checkout feature\n    commit id: "C (yours)"\n    commit id: "D (yours)"\n    checkout main\n    commit id: "E"\n    commit id: "F" tag: "main"\n    checkout feature\n    merge main id: "M" tag: "feature"',
                    },
                    {
                        "step_number": 5,
                        "title": "Option 2: Rebase Feature onto Main",
                        "explanation": "Fetch latest main, then rebase your feature branch ONTO main. This **replays** your commits on top of main, creating new commit hashes. Results in linear history.",
                        "diagram_data": 'flowchart TB\n    subgraph "Commands"\n    C1["git checkout feature"]\n    C2["git fetch origin"]\n    C3["git rebase origin/main"]\n    C4["# Resolve conflicts if any"]\n    C5["git push --force-with-lease"]\n    end\n    C1 --> C2 --> C3 --> C4 --> C5\n    style C3 fill:#90EE90\n    style C5 fill:#FFB6C1',
                    },
                    {
                        "step_number": 6,
                        "title": "Rebase Result",
                        "explanation": "After rebasing, your commits C, D are **replayed** as C', D' on top of main. They have new hashes but same changes. The history is now linear - no merge commit needed.",
                        "diagram_data": 'gitGraph\n    commit id: "A"\n    commit id: "B"\n    commit id: "E"\n    commit id: "F" tag: "main"\n    commit id: "C\' (yours)" type: HIGHLIGHT\n    commit id: "D\' (yours)" tag: "feature" type: HIGHLIGHT',
                    },
                    {
                        "step_number": 7,
                        "title": "Why --force-with-lease?",
                        "explanation": "After rebasing, your local commits have NEW hashes. You need **force push** to update the remote. Use **--force-with-lease** instead of --force - it's safer and fails if someone else pushed.",
                        "diagram_data": 'flowchart TB\n    subgraph "Force Push Safety"\n    F1["--force<br/>Overwrites remote blindly<br/>May lose teammate\'s commits"]\n    F2["--force-with-lease<br/>Checks remote first<br/>Fails if remote changed"]\n    end\n    F1 --> DANGER["Dangerous!"]\n    F2 --> SAFE["Safe choice"]\n    style DANGER fill:#FFB6C1\n    style SAFE fill:#90EE90\n    style F2 fill:#90EE90',
                    },
                    {
                        "step_number": 8,
                        "title": "Handling Conflicts",
                        "explanation": "Both merge and rebase may encounter conflicts if you and teammates edited the same code. You'll need to manually resolve these conflicts before completing the operation.",
                        "diagram_data": 'flowchart TB\n    subgraph "During Merge"\n    M1["CONFLICT in file.py"]\n    M2["Fix conflicts in editor"]\n    M3["git add file.py"]\n    M4["git commit"]\n    end\n    subgraph "During Rebase"\n    R1["CONFLICT in file.py"]\n    R2["Fix conflicts in editor"]\n    R3["git add file.py"]\n    R4["git rebase --continue"]\n    end\n    M1 --> M2 --> M3 --> M4\n    R1 --> R2 --> R3 --> R4\n    style M4 fill:#90EE90\n    style R4 fill:#90EE90',
                    },
                    {
                        "step_number": 9,
                        "title": "Which Should You Use?",
                        "explanation": "Both are valid! **Merge** is simpler and preserves history. **Rebase** creates cleaner history but rewrites commits. Many teams have conventions - follow your team's practice.",
                        "diagram_data": 'flowchart TB\n    Q{"Which to use?"}\n    Q -->|"Beginner / shared branch"| MERGE["Use Merge"]\n    Q -->|"Clean history / solo branch"| REBASE["Use Rebase"]\n    Q -->|"Team has convention"| FOLLOW["Follow team practice"]\n    subgraph "Common Conventions"\n    CONV1["Rebase before opening PR"]\n    CONV2["Merge for long-running branches"]\n    CONV3["Squash merge into main"]\n    end\n    style FOLLOW fill:#ADD8E6',
                    },
                    {
                        "step_number": 10,
                        "title": "Quick Reference",
                        "explanation": "Summary of commands for both approaches. Remember: after rebase, you must force push. After merge, regular push works.",
                        "diagram_data": 'flowchart TB\n    subgraph "Merge Approach"\n    M["git fetch origin<br/>git checkout feature<br/>git merge origin/main<br/># resolve conflicts<br/>git push"]\n    end\n    subgraph "Rebase Approach"\n    R["git fetch origin<br/>git checkout feature<br/>git rebase origin/main<br/># resolve conflicts<br/>git push --force-with-lease"]\n    end\n    style M fill:#ADD8E6\n    style R fill:#90EE90',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_git_merge_conflicts_visual(self):
        """Seed Git merge conflicts visual topic."""
        subject = self.get_or_create_subject("Git", "git", "DevOps & Tooling")

        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="git-merge-conflicts",
            defaults={
                "title": "Resolving Merge Conflicts",
                "description": "Step-by-step guide to understanding and resolving Git merge conflicts",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "intermediate",
                "estimated_time_minutes": 10,
                "tags": ["git", "conflicts", "merge", "team", "collaboration"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "What Causes Merge Conflicts?",
                        "explanation": "A **merge conflict** occurs when Git can't automatically merge changes because both branches modified the **same lines** in the same file, or one branch deleted a file the other modified.",
                        "diagram_data": 'flowchart TB\n    subgraph "Main Branch"\n    M["Line 5: print(\'Hello\')"]\n    end\n    subgraph "Feature Branch"\n    F["Line 5: print(\'Hi there\')"]\n    end\n    M --> CONFLICT["CONFLICT!<br/>Same line, different changes<br/>Git can\'t choose"]\n    F --> CONFLICT\n    style CONFLICT fill:#FFB6C1',
                    },
                    {
                        "step_number": 1,
                        "title": "When Conflicts DON'T Happen",
                        "explanation": "Git auto-merges when changes are in **different files** or **different parts of the same file**. Only overlapping changes cause conflicts. Most merges are automatic!",
                        "diagram_data": 'flowchart TB\n    subgraph "Auto-merge: Different files"\n    A1["You: edit file_a.py"]\n    A2["Teammate: edit file_b.py"]\n    A3["No conflict!"]\n    end\n    subgraph "Auto-merge: Different lines"\n    B1["You: edit lines 1-10"]\n    B2["Teammate: edit lines 50-60"]\n    B3["No conflict!"]\n    end\n    A1 --> A3\n    A2 --> A3\n    B1 --> B3\n    B2 --> B3\n    style A3 fill:#90EE90\n    style B3 fill:#90EE90',
                    },
                    {
                        "step_number": 2,
                        "title": "Conflict Markers",
                        "explanation": "When a conflict occurs, Git marks the conflicting section in the file with special markers. You'll see **your changes** and **their changes** separated by markers.",
                        "diagram_data": 'flowchart TB\n    subgraph "Conflict Markers in File"\n    C1["<<<<<<< HEAD"]\n    C2["print(\'Hello\')  # Your version"]\n    C3["======="]\n    C4["print(\'Hi there\')  # Their version"]\n    C5[">>>>>>> feature-branch"]\n    end\n    C1 --> C2 --> C3 --> C4 --> C5\n    style C1 fill:#ADD8E6\n    style C3 fill:#FFFACD\n    style C5 fill:#FFB6C1',
                    },
                    {
                        "step_number": 3,
                        "title": "Understanding the Markers",
                        "explanation": "**<<<<<<< HEAD**: Start of YOUR current branch's version. **=======**: Separator between versions. **>>>>>>> branch**: End of INCOMING branch's version. You need to resolve and remove all markers.",
                        "diagram_data": 'flowchart TB\n    subgraph "Marker Meanings"\n    M1["<<<<<<< HEAD<br/>Start of YOUR changes<br/>(current branch)"]\n    M2["=======<br/>Divider between<br/>the two versions"]\n    M3[">>>>>>> feature<br/>End of THEIR changes<br/>(incoming branch)"]\n    end\n    style M1 fill:#ADD8E6\n    style M2 fill:#FFFACD\n    style M3 fill:#FFB6C1',
                    },
                    {
                        "step_number": 4,
                        "title": "Step 1: Identify Conflicted Files",
                        "explanation": 'After a failed merge/rebase, use **git status** to see which files have conflicts. They\'ll be marked as "both modified" or "unmerged".',
                        "diagram_data": 'flowchart TB\n    subgraph "git status output"\n    S1["Unmerged paths:"]\n    S2["both modified: src/app.py"]\n    S3["both modified: src/utils.py"]\n    end\n    S1 --> S2 --> S3\n    subgraph "What to do"\n    D1["Open each conflicted file"]\n    D2["Find conflict markers"]\n    D3["Resolve each conflict"]\n    end\n    S3 --> D1 --> D2 --> D3\n    style S2 fill:#FFB6C1\n    style S3 fill:#FFB6C1',
                    },
                    {
                        "step_number": 5,
                        "title": "Step 2: Open File and Find Conflicts",
                        "explanation": "Open each conflicted file in your editor. Search for **<<<<<<<** to find all conflicts. Most editors highlight conflicts with colors.",
                        "diagram_data": 'flowchart TB\n    subgraph "In Your Editor"\n    E1["Line 10: def calculate():"]\n    E2["Line 11: <<<<<<< HEAD"]\n    E3["Line 12:     return x + y"]\n    E4["Line 13: ======="]\n    E5["Line 14:     return x * y"]\n    E6["Line 15: >>>>>>> feature"]\n    E7["Line 16: "]\n    end\n    E2 --> CONFLICT["Conflict here!"]\n    style E2 fill:#FFB6C1\n    style CONFLICT fill:#FFB6C1',
                    },
                    {
                        "step_number": 6,
                        "title": "Step 3: Decide What to Keep",
                        "explanation": "You have four choices: (1) Keep YOUR version, (2) Keep THEIR version, (3) Keep BOTH, (4) Write something completely NEW. The right choice depends on what the code should do.",
                        "diagram_data": 'flowchart TB\n    CONFLICT["Conflict: x+y vs x*y"]\n    CONFLICT --> YOURS["Keep yours:<br/>return x + y"]\n    CONFLICT --> THEIRS["Keep theirs:<br/>return x * y"]\n    CONFLICT --> BOTH["Keep both:<br/>return x + y, x * y"]\n    CONFLICT --> NEW["Write new:<br/>return x + y + z"]\n    style YOURS fill:#ADD8E6\n    style THEIRS fill:#90EE90\n    style BOTH fill:#FFFACD\n    style NEW fill:#E6E6FA',
                    },
                    {
                        "step_number": 7,
                        "title": "Step 4: Edit the File",
                        "explanation": "Manually edit the file: remove ALL conflict markers and keep/write the correct code. The result should be valid, working code with NO markers remaining.",
                        "diagram_data": 'flowchart LR\n    subgraph "Before (with markers)"\n    B1["<<<<<<< HEAD"]\n    B2["return x + y"]\n    B3["======="]\n    B4["return x * y"]\n    B5[">>>>>>> feature"]\n    end\n    subgraph "After (resolved)"\n    A1["return x + y  # Kept your version"]\n    end\n    B1 --> A1\n    style A1 fill:#90EE90',
                    },
                    {
                        "step_number": 8,
                        "title": "Step 5: Stage the Resolved File",
                        "explanation": "After fixing ALL conflicts in a file, stage it with **git add**. This tells Git you've resolved the conflicts. Repeat for all conflicted files.",
                        "diagram_data": 'flowchart TB\n    A["Fix conflicts in src/app.py"]\n    B["git add src/app.py"]\n    C["Fix conflicts in src/utils.py"]\n    D["git add src/utils.py"]\n    E["All conflicts resolved!"]\n    A --> B --> C --> D --> E\n    style E fill:#90EE90',
                    },
                    {
                        "step_number": 9,
                        "title": "Step 6: Complete the Merge/Rebase",
                        "explanation": "For **merge**: run **git commit** (Git provides a default merge message). For **rebase**: run **git rebase --continue**. The operation completes successfully.",
                        "diagram_data": 'flowchart TB\n    subgraph "After Merge"\n    M1["All files staged"]\n    M2["git commit"]\n    M3["Merge complete!"]\n    end\n    subgraph "After Rebase"\n    R1["All files staged"]\n    R2["git rebase --continue"]\n    R3["May hit more conflicts..."]\n    R4["Eventually: Rebase complete!"]\n    end\n    M1 --> M2 --> M3\n    R1 --> R2 --> R3 --> R4\n    style M3 fill:#90EE90\n    style R4 fill:#90EE90',
                    },
                    {
                        "step_number": 10,
                        "title": "Aborting: When to Give Up",
                        "explanation": "If conflicts are too complex or you made a mistake, you can **abort** and return to the state before the merge/rebase. Nothing is lost!",
                        "diagram_data": 'flowchart TB\n    subgraph "Abort Commands"\n    A1["git merge --abort<br/>Cancel merge, go back"]\n    A2["git rebase --abort<br/>Cancel rebase, go back"]\n    end\n    subgraph "When to Abort"\n    W1["Conflicts too complex"]\n    W2["Need to discuss with teammate"]\n    W3["Made mistakes during resolution"]\n    W4["Want to try different approach"]\n    end\n    W1 --> A1\n    W1 --> A2\n    style A1 fill:#FFFACD\n    style A2 fill:#FFFACD',
                    },
                    {
                        "step_number": 11,
                        "title": "Pro Tips: Preventing Conflicts",
                        "explanation": "Reduce conflicts by: (1) Pulling/rebasing frequently, (2) Keeping PRs small, (3) Communicating with teammates about file changes, (4) Using feature flags for big changes.",
                        "diagram_data": 'flowchart TB\n    subgraph "Prevention Strategies"\n    P1["Update branch daily<br/>git pull --rebase origin main"]\n    P2["Small, focused PRs<br/>Fewer files = fewer conflicts"]\n    P3["Communicate<br/>\'I\'m refactoring auth.py\'"]\n    P4["Feature flags<br/>Merge often, enable later"]\n    end\n    style P1 fill:#90EE90\n    style P2 fill:#90EE90\n    style P3 fill:#ADD8E6\n    style P4 fill:#ADD8E6',
                    },
                    {
                        "step_number": 12,
                        "title": "Quick Reference: Conflict Resolution",
                        "explanation": "Summary of the complete conflict resolution workflow for both merge and rebase scenarios.",
                        "diagram_data": 'flowchart TB\n    subgraph "Merge Conflict Resolution"\n    M1["git merge feature"]\n    M2["CONFLICT!"]\n    M3["Edit files, remove markers"]\n    M4["git add <files>"]\n    M5["git commit"]\n    M6["Done!"]\n    end\n    subgraph "Rebase Conflict Resolution"\n    R1["git rebase main"]\n    R2["CONFLICT!"]\n    R3["Edit files, remove markers"]\n    R4["git add <files>"]\n    R5["git rebase --continue"]\n    R6["Repeat if more conflicts..."]\n    R7["Done!"]\n    end\n    M1 --> M2 --> M3 --> M4 --> M5 --> M6\n    R1 --> R2 --> R3 --> R4 --> R5 --> R6 --> R7\n    style M6 fill:#90EE90\n    style R7 fill:#90EE90',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_sklearn_visuals(self):
        """Seed scikit-learn visual topics."""
        subject = self.get_or_create_subject(
            "scikit-learn", "scikit-learn", "ML Frameworks"
        )

        # Decision Tree Training
        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="decision-tree-training",
            defaults={
                "title": "Decision Tree Training Process",
                "description": "Visualize how a Decision Tree classifier learns from data by finding optimal splits",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "intermediate",
                "estimated_time_minutes": 8,
                "tags": ["decision-tree", "classification", "supervised-learning"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "Training Data",
                        "explanation": "We start with labeled training data. Our goal is to find **decision rules** (splits) that separate the data into pure groups based on the target labels.",
                        "diagram_data": 'graph TB\n    subgraph Training Data\n    A["X=[2,3], y=0 (Blue)"]\n    B["X=[4,5], y=1 (Red)"]\n    C["X=[1,2], y=0 (Blue)"]\n    D["X=[5,4], y=1 (Red)"]\n    E["X=[3,1], y=0 (Blue)"]\n    end',
                    },
                    {
                        "step_number": 1,
                        "title": "Root Node - All Data",
                        "explanation": "The tree starts with a **root node** containing all training samples. We need to find the best feature and threshold to split this data. The goal is to create child nodes that are more 'pure' (contain mostly one class).",
                        "diagram_data": 'graph TB\n    Root["Root Node<br/>5 samples<br/>3 Blue, 2 Red<br/>Impurity: 0.48"]',
                    },
                    {
                        "step_number": 2,
                        "title": "Evaluating Split Candidates",
                        "explanation": "For each feature, we try different **threshold values** and calculate the **information gain** (or Gini reduction). The split that best separates the classes wins.",
                        "diagram_data": 'graph TB\n    Root["Root: 5 samples"]\n    Root --> |"Try: X1 < 3.5"| Split1["Left: 3 samples<br/>Right: 2 samples"]\n    Root --> |"Try: X2 < 2.5"| Split2["Left: 2 samples<br/>Right: 3 samples"]\n    Split1 --> Best["Best Split!<br/>Gini Gain: 0.32"]\n    style Best fill:#90EE90',
                    },
                    {
                        "step_number": 3,
                        "title": "First Split Applied",
                        "explanation": "We apply the best split `X1 < 3.5`. Samples with X1 < 3.5 go left, others go right. The left node is now **pure** (all Blue), but the right still needs splitting.",
                        "diagram_data": 'graph TB\n    Root["X1 < 3.5?"]\n    Root -->|Yes| Left["3 samples<br/>3 Blue, 0 Red<br/>PURE!"]\n    Root -->|No| Right["2 samples<br/>0 Blue, 2 Red<br/>PURE!"]\n    style Left fill:#ADD8E6\n    style Right fill:#FFB6C1',
                    },
                    {
                        "step_number": 4,
                        "title": "Stopping Criteria",
                        "explanation": "A node becomes a **leaf** when: (1) it's pure (all same class), (2) max depth reached, (3) min samples threshold, or (4) no split improves purity. Leaf nodes make predictions.",
                        "diagram_data": 'graph TB\n    Root["X1 < 3.5?"]\n    Root -->|Yes| Left["Predict: Blue<br/>Confidence: 100%"]\n    Root -->|No| Right["Predict: Red<br/>Confidence: 100%"]\n    style Left fill:#ADD8E6\n    style Right fill:#FFB6C1',
                    },
                    {
                        "step_number": 5,
                        "title": "Making Predictions",
                        "explanation": "To predict a new sample, start at the root and follow the decision path. At each node, go left or right based on the split condition until you reach a leaf.",
                        "diagram_data": 'graph TB\n    New["New Sample<br/>X=[2.5, 3]"]\n    New --> Root["X1 < 3.5?"]\n    Root -->|"2.5 < 3.5? Yes!"| Left["Predict: Blue"]\n    Root -.->|No| Right["Predict: Red"]\n    style New fill:#FFFACD\n    style Left fill:#ADD8E6',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_decision_tree_fundamentals_visual(self):
        """Seed Decision Tree Fundamentals visual topic."""
        subject = self.get_or_create_subject(
            "scikit-learn", "scikit-learn", "ML Frameworks"
        )

        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="decision-tree-fundamentals",
            defaults={
                "title": "Decision Trees: Fundamentals",
                "description": "Master the core concepts of decision trees: splits, impurity measures, tree structure, and prediction",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "beginner",
                "estimated_time_minutes": 12,
                "tags": [
                    "decision-tree",
                    "classification",
                    "regression",
                    "supervised-learning",
                    "fundamentals",
                ],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "What is a Decision Tree?",
                        "explanation": "A **decision tree** is a flowchart-like structure where each internal node represents a test on a feature, each branch represents an outcome, and each leaf represents a prediction. It mimics human decision-making!",
                        "diagram_data": 'graph TB\n    ROOT["Is it raining?"]\n    ROOT -->|Yes| L1["Take umbrella"]\n    ROOT -->|No| R1["Is it sunny?"]\n    R1 -->|Yes| L2["Wear sunglasses"]\n    R1 -->|No| R2["Just go outside"]\n    style ROOT fill:#E6E6FA\n    style L1 fill:#90EE90\n    style L2 fill:#90EE90\n    style R2 fill:#90EE90',
                    },
                    {
                        "step_number": 1,
                        "title": "Tree Anatomy",
                        "explanation": "A decision tree has: **Root node** (top, first split), **Internal nodes** (decision points), **Branches** (outcomes of tests), **Leaf nodes** (final predictions). Depth = longest path from root to leaf.",
                        "diagram_data": 'graph TB\n    ROOT["ROOT NODE<br/>(First split)"]\n    ROOT --> INT1["INTERNAL NODE<br/>(Another split)"]\n    ROOT --> LEAF1["LEAF NODE<br/>(Prediction)"]\n    INT1 --> LEAF2["LEAF NODE<br/>(Prediction)"]\n    INT1 --> LEAF3["LEAF NODE<br/>(Prediction)"]\n    style ROOT fill:#FFB6C1\n    style INT1 fill:#FFFACD\n    style LEAF1 fill:#90EE90\n    style LEAF2 fill:#90EE90\n    style LEAF3 fill:#90EE90\n    NOTE["Depth = 2<br/>Leaves = 3"]',
                    },
                    {
                        "step_number": 2,
                        "title": "The Goal: Separate Classes",
                        "explanation": "For classification, the goal is to create **pure** leaf nodes where all samples belong to ONE class. We achieve this by finding splits that best separate the classes at each step.",
                        "diagram_data": 'flowchart TB\n    subgraph "Before Split"\n    MIXED["Mixed: 50 Red, 50 Blue"]\n    end\n    subgraph "After Good Split"\n    LEFT["45 Red, 5 Blue<br/>(mostly Red)"]\n    RIGHT["5 Red, 45 Blue<br/>(mostly Blue)"]\n    end\n    MIXED -->|"Feature X < 0.5"| LEFT\n    MIXED -->|"Feature X >= 0.5"| RIGHT\n    style MIXED fill:#E6E6FA\n    style LEFT fill:#FFB6C1\n    style RIGHT fill:#ADD8E6',
                    },
                    {
                        "step_number": 3,
                        "title": 'Impurity: Measuring "Mixedness"',
                        "explanation": "**Impurity** measures how mixed the classes are in a node. Pure node (all same class) = 0 impurity. Evenly mixed = maximum impurity. We want splits that REDUCE impurity the most.",
                        "diagram_data": 'flowchart LR\n    subgraph "Pure Node"\n    P["100% Class A<br/>Impurity = 0"]\n    end\n    subgraph "Slightly Mixed"\n    S["90% A, 10% B<br/>Low Impurity"]\n    end\n    subgraph "Highly Mixed"\n    H["50% A, 50% B<br/>Max Impurity"]\n    end\n    style P fill:#90EE90\n    style S fill:#FFFACD\n    style H fill:#FFB6C1',
                    },
                    {
                        "step_number": 4,
                        "title": "Gini Impurity",
                        "explanation": "**Gini Impurity** = 1 - Σ(pᵢ²) where pᵢ is the proportion of class i. Range: 0 (pure) to 0.5 (binary) or higher (multiclass). Measures probability of misclassifying a random sample.",
                        "diagram_data": 'flowchart TB\n    subgraph "Gini Formula"\n    F["Gini = 1 - Σ(pᵢ²)"]\n    end\n    subgraph "Examples"\n    E1["Pure: [100%, 0%]<br/>Gini = 1 - (1² + 0²) = 0"]\n    E2["Mixed: [50%, 50%]<br/>Gini = 1 - (0.5² + 0.5²) = 0.5"]\n    E3["Skewed: [90%, 10%]<br/>Gini = 1 - (0.9² + 0.1²) = 0.18"]\n    end\n    style E1 fill:#90EE90\n    style E2 fill:#FFB6C1\n    style E3 fill:#FFFACD',
                    },
                    {
                        "step_number": 5,
                        "title": "Entropy (Information Gain)",
                        "explanation": "**Entropy** = -Σ(pᵢ × log₂(pᵢ)). Measures uncertainty/information content. Range: 0 (pure) to log₂(classes). **Information Gain** = entropy before split - weighted entropy after.",
                        "diagram_data": 'flowchart TB\n    subgraph "Entropy Formula"\n    F["Entropy = -Σ(pᵢ × log₂(pᵢ))"]\n    end\n    subgraph "Examples"\n    E1["Pure: [100%, 0%]<br/>Entropy = 0 bits"]\n    E2["Mixed: [50%, 50%]<br/>Entropy = 1 bit"]\n    E3["Skewed: [90%, 10%]<br/>Entropy ≈ 0.47 bits"]\n    end\n    style E1 fill:#90EE90\n    style E2 fill:#FFB6C1\n    style E3 fill:#FFFACD',
                    },
                    {
                        "step_number": 6,
                        "title": "Gini vs Entropy",
                        "explanation": "Both work well in practice. **Gini** is slightly faster (no log). **Entropy** is from information theory. Gini tends to isolate the most frequent class; Entropy produces more balanced trees.",
                        "diagram_data": 'flowchart TB\n    subgraph "Gini Impurity"\n    G1["Faster computation"]\n    G2["No logarithm needed"]\n    G3["Default in scikit-learn"]\n    G4["Favors larger partitions"]\n    end\n    subgraph "Entropy"\n    E1["Information-theoretic"]\n    E2["Slightly slower"]\n    E3["More balanced splits"]\n    E4["Used in ID3, C4.5"]\n    end\n    style G3 fill:#90EE90\n    style E4 fill:#ADD8E6',
                    },
                    {
                        "step_number": 7,
                        "title": "Finding the Best Split",
                        "explanation": "For each feature, try different thresholds and calculate the **impurity reduction** (gain). The split with the HIGHEST gain wins. Repeat recursively for child nodes.",
                        "diagram_data": 'flowchart TB\n    NODE["Node: 100 samples"]\n    NODE --> TRY["Try all features & thresholds"]\n    subgraph "Candidates"\n    C1["F1 < 0.3: gain=0.15"]\n    C2["F1 < 0.7: gain=0.22"]\n    C3["F2 < 0.5: gain=0.31"]\n    C4["F3 < 0.2: gain=0.18"]\n    end\n    TRY --> C1\n    TRY --> C2\n    TRY --> C3\n    TRY --> C4\n    C3 --> BEST["Winner: F2 < 0.5"]\n    style C3 fill:#90EE90\n    style BEST fill:#90EE90',
                    },
                    {
                        "step_number": 8,
                        "title": "Regression Trees",
                        "explanation": "For regression, leaf nodes predict a **numeric value** (usually the mean of samples). Instead of impurity, we minimize **MSE** (Mean Squared Error) or **MAE** (Mean Absolute Error).",
                        "diagram_data": 'flowchart TB\n    subgraph "Classification"\n    CL["Leaf predicts CLASS<br/>Majority vote"]\n    CM["Minimize Gini/Entropy"]\n    end\n    subgraph "Regression"\n    RL["Leaf predicts NUMBER<br/>Mean of samples"]\n    RM["Minimize MSE/MAE"]\n    end\n    subgraph "MSE Split"\n    MSE["MSE = (1/n) Σ(yᵢ - ȳ)²<br/>Find split that minimizes<br/>weighted child MSE"]\n    end\n    style CL fill:#ADD8E6\n    style RL fill:#90EE90\n    style MSE fill:#FFFACD',
                    },
                    {
                        "step_number": 9,
                        "title": "Stopping Criteria",
                        "explanation": "Tree growth stops when: (1) **max_depth** reached, (2) node has fewer than **min_samples_split**, (3) leaf has fewer than **min_samples_leaf**, (4) node is **pure**, (5) no split improves impurity.",
                        "diagram_data": 'flowchart TB\n    GROW["Growing tree..."]\n    GROW --> CHECK{"Stop?"}\n    CHECK -->|"max_depth reached"| STOP["Create leaf"]\n    CHECK -->|"< min_samples_split"| STOP\n    CHECK -->|"Pure node"| STOP\n    CHECK -->|"No gain > 0"| STOP\n    CHECK -->|"Otherwise"| CONT["Continue splitting"]\n    CONT --> GROW\n    style STOP fill:#90EE90\n    style CONT fill:#ADD8E6',
                    },
                    {
                        "step_number": 10,
                        "title": "Making Predictions",
                        "explanation": "To predict: start at root, evaluate the condition, follow the appropriate branch, repeat until reaching a leaf. The leaf's value is the prediction (class or number).",
                        "diagram_data": 'flowchart TB\n    NEW["New sample:<br/>F1=0.6, F2=0.3, F3=0.8"]\n    NEW --> R["F2 < 0.5?<br/>0.3 < 0.5? YES"]\n    R -->|Yes| L1["F1 < 0.4?<br/>0.6 < 0.4? NO"]\n    R -.->|No| R1["..."]\n    L1 -.->|Yes| L2["..."]\n    L1 -->|No| LEAF["LEAF<br/>Predict: Class A"]\n    style NEW fill:#E6E6FA\n    style LEAF fill:#90EE90',
                    },
                    {
                        "step_number": 11,
                        "title": "Overfitting Problem",
                        "explanation": "Deep trees can **memorize** training data (overfit). A tree with one sample per leaf has 100% training accuracy but fails on new data. Solution: limit depth, prune, or use ensembles.",
                        "diagram_data": 'flowchart TB\n    subgraph "Overfit Tree"\n    OF["Very deep"]\n    OF1["1 sample per leaf"]\n    OF2["100% train accuracy"]\n    OF3["Poor test accuracy"]\n    end\n    subgraph "Good Tree"\n    GD["Limited depth"]\n    GD1["Many samples per leaf"]\n    GD2["~95% train accuracy"]\n    GD3["Good test accuracy"]\n    end\n    style OF3 fill:#FFB6C1\n    style GD3 fill:#90EE90',
                    },
                    {
                        "step_number": 12,
                        "title": "Pruning",
                        "explanation": "**Pruning** removes branches that don't improve generalization. **Pre-pruning**: stop early (max_depth, min_samples). **Post-pruning**: grow full tree, then remove unhelpful branches.",
                        "diagram_data": 'flowchart TB\n    subgraph "Pre-pruning (Early Stopping)"\n    PRE1["Set max_depth=5"]\n    PRE2["Set min_samples_leaf=10"]\n    PRE3["Tree stops growing early"]\n    end\n    subgraph "Post-pruning"\n    POST1["Grow full tree"]\n    POST2["Evaluate each subtree"]\n    POST3["Remove if no improvement"]\n    POST4["Use validation set or CV"]\n    end\n    PRE1 --> PRE3\n    PRE2 --> PRE3\n    POST1 --> POST2 --> POST3\n    style PRE3 fill:#90EE90\n    style POST3 fill:#ADD8E6',
                    },
                    {
                        "step_number": 13,
                        "title": "Strengths and Weaknesses",
                        "explanation": "Decision trees are interpretable and handle mixed data types, but they're prone to overfitting and are unstable (small data changes → different tree). Ensembles address weaknesses.",
                        "diagram_data": 'flowchart TB\n    subgraph "Strengths"\n    S1["Easy to interpret"]\n    S2["Handles numeric & categorical"]\n    S3["No feature scaling needed"]\n    S4["Captures non-linear patterns"]\n    S5["Fast prediction"]\n    end\n    subgraph "Weaknesses"\n    W1["Prone to overfitting"]\n    W2["Unstable (high variance)"]\n    W3["Greedy, not globally optimal"]\n    W4["Biased toward features with more levels"]\n    end\n    style S1 fill:#90EE90\n    style S2 fill:#90EE90\n    style S3 fill:#90EE90\n    style W1 fill:#FFB6C1\n    style W2 fill:#FFB6C1',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_cart_visual(self):
        """Seed CART (Classification and Regression Trees) visual topic."""
        subject = self.get_or_create_subject(
            "scikit-learn", "scikit-learn", "ML Frameworks"
        )

        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="cart-algorithm",
            defaults={
                "title": "CART: Classification and Regression Trees",
                "description": "Deep dive into the CART algorithm used by scikit-learn, including binary splits, cost-complexity pruning, and implementation details",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "intermediate",
                "estimated_time_minutes": 12,
                "tags": [
                    "cart",
                    "decision-tree",
                    "pruning",
                    "gini",
                    "scikit-learn",
                ],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "What is CART?",
                        "explanation": "**CART** (Classification And Regression Trees) is a specific decision tree algorithm developed by Breiman et al. (1984). It's the algorithm used by scikit-learn's DecisionTreeClassifier and DecisionTreeRegressor.",
                        "diagram_data": 'flowchart TB\n    subgraph "Decision Tree Algorithms"\n    ID3["ID3 (1986)<br/>Categorical only<br/>Multi-way splits"]\n    C45["C4.5 (1993)<br/>Handles continuous<br/>Multi-way splits"]\n    CART["CART (1984)<br/>Numeric & categorical<br/>BINARY splits only"]\n    end\n    CART --> SK["scikit-learn uses CART"]\n    style CART fill:#90EE90\n    style SK fill:#ADD8E6',
                    },
                    {
                        "step_number": 1,
                        "title": "CART Key Feature: Binary Splits Only",
                        "explanation": 'CART always creates **exactly two children** per split (binary tree). Even categorical features are split as "is X in {A,B}?" vs "is X in {C,D}?". This simplifies the algorithm and tree structure.',
                        "diagram_data": 'flowchart TB\n    subgraph "CART (Binary)"\n    CB["Color in {Red, Blue}?"]\n    CB -->|Yes| CBL["Left child"]\n    CB -->|No| CBR["Right child"]\n    end\n    subgraph "Other (Multi-way)"\n    CM["Color = ?"]\n    CM -->|Red| CMR["Child 1"]\n    CM -->|Blue| CMB["Child 2"]\n    CM -->|Green| CMG["Child 3"]\n    end\n    style CB fill:#90EE90\n    style CM fill:#FFFACD',
                    },
                    {
                        "step_number": 2,
                        "title": "CART for Classification",
                        "explanation": "For classification, CART uses **Gini impurity** by default (entropy is optional). At each node, it finds the binary split that maximizes the Gini gain (impurity reduction).",
                        "diagram_data": 'flowchart TB\n    NODE["Node: 100 samples<br/>60 Class A, 40 Class B<br/>Gini = 0.48"]\n    NODE --> SPLIT["Best split: X1 < 0.5"]\n    SPLIT --> LEFT["Left: 50 samples<br/>48 A, 2 B<br/>Gini = 0.077"]\n    SPLIT --> RIGHT["Right: 50 samples<br/>12 A, 38 B<br/>Gini = 0.355"]\n    GAIN["Gini Gain = 0.48 - (0.5×0.077 + 0.5×0.355) = 0.264"]\n    style NODE fill:#E6E6FA\n    style LEFT fill:#ADD8E6\n    style RIGHT fill:#FFB6C1\n    style GAIN fill:#90EE90',
                    },
                    {
                        "step_number": 3,
                        "title": "CART for Regression",
                        "explanation": "For regression, CART minimizes **MSE** (Mean Squared Error) by default. Each leaf predicts the **mean** of its samples. The split that minimizes weighted child MSE is chosen.",
                        "diagram_data": 'flowchart TB\n    NODE["Node: 100 samples<br/>Mean y = 50<br/>MSE = 400"]\n    NODE --> SPLIT["Best split: X2 < 3.5"]\n    SPLIT --> LEFT["Left: 40 samples<br/>Mean y = 30<br/>MSE = 100"]\n    SPLIT --> RIGHT["Right: 60 samples<br/>Mean y = 63<br/>MSE = 150"]\n    GAIN["MSE Reduction = 400 - (0.4×100 + 0.6×150) = 270"]\n    style NODE fill:#E6E6FA\n    style LEFT fill:#ADD8E6\n    style RIGHT fill:#90EE90\n    style GAIN fill:#90EE90',
                    },
                    {
                        "step_number": 4,
                        "title": "The Greedy Splitting Algorithm",
                        "explanation": "CART uses a **greedy** recursive algorithm: at each node, find the locally best split without looking ahead. This is fast but doesn't guarantee the globally optimal tree.",
                        "diagram_data": 'flowchart TB\n    A["1. Start with all data at root"]\n    B["2. For each feature:"]\n    C["   Try all possible thresholds"]\n    D["   Calculate Gini/MSE for each"]\n    E["3. Select best feature + threshold"]\n    F["4. Split node into two children"]\n    G{"5. Stopping criteria met?"}\n    H["6. Create leaf node"]\n    I["7. Recurse on children"]\n    A --> B --> C --> D --> E --> F --> G\n    G -->|Yes| H\n    G -->|No| I\n    I --> B\n    style E fill:#90EE90\n    style H fill:#ADD8E6',
                    },
                    {
                        "step_number": 5,
                        "title": "Handling Continuous Features",
                        "explanation": "For a continuous feature with N unique values, CART tries N-1 possible thresholds (midpoints between sorted values). It picks the threshold with the best impurity reduction.",
                        "diagram_data": 'flowchart TB\n    subgraph "Feature X values"\n    V["Sorted: [1.2, 2.5, 3.1, 4.8, 5.0]"]\n    end\n    subgraph "Candidate Thresholds"\n    T1["X < 1.85"]\n    T2["X < 2.80"]\n    T3["X < 3.95"]\n    T4["X < 4.90"]\n    end\n    V --> T1\n    V --> T2\n    V --> T3\n    V --> T4\n    T2 --> BEST["Best: X < 2.80<br/>Gini gain = 0.35"]\n    style BEST fill:#90EE90',
                    },
                    {
                        "step_number": 6,
                        "title": "Handling Categorical Features",
                        "explanation": "For categorical features, CART tries all possible binary partitions of categories. With k categories, there are 2^(k-1) - 1 possible splits. For ordered targets, this can be optimized.",
                        "diagram_data": 'flowchart TB\n    subgraph "Categorical: Color = {R, G, B}"\n    CAT["3 categories → 3 possible splits"]\n    end\n    subgraph "Possible Binary Splits"\n    S1["{R} vs {G, B}"]\n    S2["{G} vs {R, B}"]\n    S3["{B} vs {R, G}"]\n    end\n    CAT --> S1\n    CAT --> S2\n    CAT --> S3\n    S1 --> EVAL["Evaluate all, pick best"]\n    S2 --> EVAL\n    S3 --> EVAL\n    style EVAL fill:#90EE90',
                    },
                    {
                        "step_number": 7,
                        "title": "Cost-Complexity Pruning (CCP)",
                        "explanation": "CART's signature pruning method: **Minimal Cost-Complexity Pruning**. It balances tree complexity against training error using parameter α (ccp_alpha). Higher α = simpler trees.",
                        "diagram_data": 'flowchart TB\n    subgraph "Cost-Complexity Formula"\n    F["Rα(T) = R(T) + α × |T|"]\n    F1["R(T) = training error"]\n    F2["|T| = number of leaves"]\n    F3["α = complexity penalty"]\n    end\n    subgraph "Effect of α"\n    A0["α = 0: Full tree (no pruning)"]\n    A1["α = 0.01: Some pruning"]\n    A2["α = 0.1: Heavy pruning"]\n    A3["α → ∞: Just root (1 leaf)"]\n    end\n    style A0 fill:#FFB6C1\n    style A1 fill:#FFFACD\n    style A2 fill:#ADD8E6\n    style A3 fill:#90EE90',
                    },
                    {
                        "step_number": 8,
                        "title": "How CCP Works",
                        "explanation": 'CCP works bottom-up: start with full tree, compute the "effective α" for each internal node, prune nodes with smallest α first. Repeat to get a sequence of trees, then pick best by cross-validation.',
                        "diagram_data": 'flowchart TB\n    A["1. Grow full tree T_max"]\n    B["2. For each internal node, compute:<br/>α_eff = (error_leaf - error_subtree) / (leaves_subtree - 1)"]\n    C["3. Prune node with smallest α_eff"]\n    D["4. Repeat → sequence of trees"]\n    E["5. Cross-validate to find best α"]\n    F["6. Return pruned tree for that α"]\n    A --> B --> C --> D --> E --> F\n    style E fill:#90EE90\n    style F fill:#ADD8E6',
                    },
                    {
                        "step_number": 9,
                        "title": "Finding Optimal Alpha with CV",
                        "explanation": "Use **cross-validation** to find the best ccp_alpha. scikit-learn's `cost_complexity_pruning_path()` returns all α values and corresponding impurities. Plot and choose α with best CV score.",
                        "diagram_data": 'flowchart TB\n    subgraph "Process"\n    P1["Get pruning path:<br/>clf.cost_complexity_pruning_path(X, y)"]\n    P2["Returns: ccp_alphas, impurities"]\n    P3["For each alpha, train with CV"]\n    P4["Plot alpha vs CV score"]\n    P5["Pick alpha with best score<br/>(or 1-SE rule)"]\n    end\n    P1 --> P2 --> P3 --> P4 --> P5\n    style P5 fill:#90EE90',
                    },
                    {
                        "step_number": 10,
                        "title": "CART Leaf Predictions",
                        "explanation": "**Classification**: leaf predicts the majority class. Probabilities = class proportions in leaf. **Regression**: leaf predicts the mean (or median with MAE criterion).",
                        "diagram_data": 'flowchart TB\n    subgraph "Classification Leaf"\n    CL["Samples: 45 A, 5 B"]\n    CP["Prediction: Class A"]\n    CPR["Probabilities: A=0.9, B=0.1"]\n    end\n    subgraph "Regression Leaf"\n    RL["Samples: [10, 12, 15, 11, 14]"]\n    RP["Prediction: mean = 12.4"]\n    end\n    CL --> CP --> CPR\n    RL --> RP\n    style CP fill:#90EE90\n    style RP fill:#ADD8E6',
                    },
                    {
                        "step_number": 11,
                        "title": "Feature Importance in CART",
                        "explanation": "CART computes feature importance as the **total impurity decrease** brought by each feature across all nodes, weighted by samples reaching each node, normalized to sum to 1.",
                        "diagram_data": 'flowchart TB\n    subgraph "Computing Importance"\n    C1["For each node split on feature F:"]\n    C2["Importance += (n_node/n_total) × Δimpurity"]\n    C3["Sum across all nodes"]\n    C4["Normalize so sum = 1"]\n    end\n    subgraph "Result"\n    R["Feature Importances:<br/>X1: 0.45<br/>X2: 0.30<br/>X3: 0.15<br/>X4: 0.10"]\n    end\n    C1 --> C2 --> C3 --> C4 --> R\n    style R fill:#90EE90',
                    },
                    {
                        "step_number": 12,
                        "title": "CART in scikit-learn",
                        "explanation": "scikit-learn implements CART with additional hyperparameters for pre-pruning and CCP. Key parameters: criterion, max_depth, min_samples_split, min_samples_leaf, ccp_alpha.",
                        "diagram_data": 'flowchart TB\n    subgraph "Key Parameters"\n    P1["criterion: \'gini\'/\'entropy\'/\'log_loss\'<br/>(classification)"]\n    P2["criterion: \'squared_error\'/\'absolute_error\'<br/>(regression)"]\n    P3["max_depth: int or None"]\n    P4["min_samples_split: int (default=2)"]\n    P5["min_samples_leaf: int (default=1)"]\n    P6["ccp_alpha: float (default=0)"]\n    end\n    style P6 fill:#90EE90',
                    },
                    {
                        "step_number": 13,
                        "title": "Complete Example",
                        "explanation": "Putting it all together: load data, train CART, prune with CCP, evaluate, and interpret with feature importances.",
                        "diagram_data": 'flowchart TB\n    subgraph "Code Flow"\n    C1["from sklearn.tree import<br/>DecisionTreeClassifier"]\n    C2["clf = DecisionTreeClassifier(<br/>criterion=\'gini\',<br/>max_depth=10,<br/>ccp_alpha=0.01)"]\n    C3["clf.fit(X_train, y_train)"]\n    C4["predictions = clf.predict(X_test)"]\n    C5["proba = clf.predict_proba(X_test)"]\n    C6["importance = clf.feature_importances_"]\n    C7["from sklearn.tree import plot_tree<br/>plot_tree(clf)"]\n    end\n    C1 --> C2 --> C3 --> C4\n    C3 --> C5\n    C3 --> C6\n    C3 --> C7\n    style C4 fill:#90EE90\n    style C7 fill:#ADD8E6',
                    },
                    {
                        "step_number": 14,
                        "title": "CART vs Other Tree Algorithms",
                        "explanation": "CART's binary splits and Gini criterion make it simple and fast. ID3/C4.5 use entropy and allow multi-way splits. CHAID uses chi-square tests. Each has trade-offs.",
                        "diagram_data": 'flowchart TB\n    subgraph "CART"\n    CART1["Binary splits only"]\n    CART2["Gini (default) or Entropy"]\n    CART3["Handles numeric & categorical"]\n    CART4["Cost-complexity pruning"]\n    end\n    subgraph "C4.5"\n    C451["Multi-way splits"]\n    C452["Gain Ratio (normalized entropy)"]\n    C453["Handles missing values"]\n    C454["Error-based pruning"]\n    end\n    subgraph "CHAID"\n    CH1["Multi-way splits"]\n    CH2["Chi-square tests"]\n    CH3["For categorical targets"]\n    end\n    style CART4 fill:#90EE90\n    style C453 fill:#ADD8E6',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_random_forest_visual(self):
        """Seed Random Forest visual topic."""
        subject = self.get_or_create_subject(
            "scikit-learn", "scikit-learn", "ML Frameworks"
        )

        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="random-forest",
            defaults={
                "title": "Random Forest: Complete Guide",
                "description": "Understand how Random Forest works from training to prediction, including bagging, feature sampling, and ensemble voting",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "intermediate",
                "estimated_time_minutes": 15,
                "tags": [
                    "random-forest",
                    "ensemble",
                    "bagging",
                    "classification",
                    "regression",
                ],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "The Big Picture: Ensemble of Trees",
                        "explanation": "Random Forest is an **ensemble method** that builds many decision trees and combines their predictions. Each tree is trained on a different random subset of data and features, making the forest robust and accurate.",
                        "diagram_data": 'flowchart TB\n    DATA["Training Data"]\n    DATA --> T1["Tree 1"]\n    DATA --> T2["Tree 2"]\n    DATA --> T3["Tree 3"]\n    DATA --> TN["Tree N"]\n    T1 --> VOTE["Combine Predictions"]\n    T2 --> VOTE\n    T3 --> VOTE\n    TN --> VOTE\n    VOTE --> FINAL["Final Prediction"]\n    style VOTE fill:#90EE90\n    style FINAL fill:#ADD8E6',
                    },
                    {
                        "step_number": 1,
                        "title": "Why Multiple Trees? The Wisdom of Crowds",
                        "explanation": "A single decision tree is prone to **overfitting** - it memorizes training data noise. By training many diverse trees and averaging their predictions, errors cancel out. This is called **bagging** (Bootstrap AGGregatING).",
                        "diagram_data": 'flowchart LR\n    subgraph "Single Tree Problem"\n    ST["One Tree"]\n    ST --> OF["Overfits to noise<br/>High variance"]\n    end\n    subgraph "Random Forest Solution"\n    RF["100 Trees"]\n    RF --> AVG["Average predictions"]\n    AVG --> STABLE["Stable & accurate<br/>Low variance"]\n    end\n    style OF fill:#FFB6C1\n    style STABLE fill:#90EE90',
                    },
                    {
                        "step_number": 2,
                        "title": "Step 1: Bootstrap Sampling",
                        "explanation": "For each tree, create a **bootstrap sample**: randomly select N samples **with replacement** from the original N samples. Some samples appear multiple times, others not at all (~37% are left out - these become the OOB set).",
                        "diagram_data": 'flowchart TB\n    subgraph "Original Data (N=6)"\n    D["[A, B, C, D, E, F]"]\n    end\n    subgraph "Bootstrap Samples (with replacement)"\n    B1["Tree 1: [A, A, C, D, D, F]"]\n    B2["Tree 2: [B, B, C, E, E, F]"]\n    B3["Tree 3: [A, C, D, D, E, F]"]\n    end\n    D -->|"Random sample<br/>with replacement"| B1\n    D -->|"Random sample<br/>with replacement"| B2\n    D -->|"Random sample<br/>with replacement"| B3\n    style B1 fill:#ADD8E6\n    style B2 fill:#90EE90\n    style B3 fill:#FFFACD',
                    },
                    {
                        "step_number": 3,
                        "title": "Step 2: Feature Subsampling at Each Split",
                        "explanation": "When finding the best split at each node, only consider a **random subset of features** (typically √p for classification, p/3 for regression). This decorrelates trees and increases diversity.",
                        "diagram_data": 'flowchart TB\n    subgraph "All Features (p=9)"\n    ALL["F1, F2, F3, F4, F5, F6, F7, F8, F9"]\n    end\n    subgraph "At Node Split (√9 = 3 features)"\n    N1["Node 1 considers:<br/>F2, F5, F8"]\n    N2["Node 2 considers:<br/>F1, F4, F7"]\n    N3["Node 3 considers:<br/>F3, F6, F9"]\n    end\n    ALL -->|"Random √p features"| N1\n    ALL -->|"Random √p features"| N2\n    ALL -->|"Random √p features"| N3\n    N1 --> BEST1["Best: F5 < 0.3"]\n    N2 --> BEST2["Best: F4 < 0.7"]\n    style BEST1 fill:#90EE90\n    style BEST2 fill:#90EE90',
                    },
                    {
                        "step_number": 4,
                        "title": "Building a Single Tree",
                        "explanation": "Each tree grows using its bootstrap sample. At every node: (1) randomly select m features, (2) find the best split among those m, (3) split the node, (4) repeat recursively until stopping criteria met.",
                        "diagram_data": 'flowchart TB\n    subgraph "Tree Building Algorithm"\n    A["Start: All bootstrap samples at root"]\n    B["Select random m features"]\n    C["Find best split among m"]\n    D["Split node into two children"]\n    E{"Stopping criteria?"}\n    F["Create leaf with prediction"]\n    end\n    A --> B --> C --> D --> E\n    E -->|"No: min_samples,<br/>max_depth not reached"| B\n    E -->|"Yes"| F\n    style F fill:#90EE90',
                    },
                    {
                        "step_number": 5,
                        "title": "Tree 1: Example Structure",
                        "explanation": "Here's what Tree 1 might look like after training on its bootstrap sample. Notice it uses different features at different nodes. Trees are typically grown deep (low bias) since variance is reduced by averaging.",
                        "diagram_data": 'graph TB\n    R1["F5 < 0.3?"]\n    R1 -->|Yes| L1["F2 < 0.6?"]\n    R1 -->|No| L2["F8 < 0.4?"]\n    L1 -->|Yes| LL1["Predict: A<br/>samples: 45"]\n    L1 -->|No| LR1["F9 < 0.5?"]\n    LR1 -->|Yes| LRL["Predict: B<br/>samples: 28"]\n    LR1 -->|No| LRR["Predict: A<br/>samples: 12"]\n    L2 -->|Yes| RL1["Predict: B<br/>samples: 67"]\n    L2 -->|No| RR1["Predict: C<br/>samples: 23"]\n    style R1 fill:#E6E6FA\n    style LL1 fill:#ADD8E6\n    style LRL fill:#90EE90\n    style LRR fill:#ADD8E6\n    style RL1 fill:#90EE90\n    style RR1 fill:#FFFACD',
                    },
                    {
                        "step_number": 6,
                        "title": "Tree 2: Different Structure",
                        "explanation": "Tree 2 trained on a different bootstrap sample and used different random features at splits. It has a completely different structure! This **diversity** is key to Random Forest's power.",
                        "diagram_data": 'graph TB\n    R2["F1 < 0.7?"]\n    R2 -->|Yes| L3["F4 < 0.2?"]\n    R2 -->|No| L4["F6 < 0.8?"]\n    L3 -->|Yes| LL2["Predict: B<br/>samples: 38"]\n    L3 -->|No| LR2["Predict: A<br/>samples: 51"]\n    L4 -->|Yes| RL2["F3 < 0.5?"]\n    L4 -->|No| RR2["Predict: C<br/>samples: 31"]\n    RL2 -->|Yes| RLL["Predict: B<br/>samples: 29"]\n    RL2 -->|No| RLR["Predict: A<br/>samples: 26"]\n    style R2 fill:#E6E6FA\n    style LL2 fill:#90EE90\n    style LR2 fill:#ADD8E6\n    style RR2 fill:#FFFACD\n    style RLL fill:#90EE90\n    style RLR fill:#ADD8E6',
                    },
                    {
                        "step_number": 7,
                        "title": "The Complete Forest",
                        "explanation": "After training, we have N trees (typically 100-500), each with unique structure due to bootstrap sampling and feature randomization. Together they form a powerful ensemble.",
                        "diagram_data": 'flowchart TB\n    subgraph "Random Forest (N=100 trees)"\n    T1["Tree 1<br/>Bootstrap 1<br/>Depth: 12"]\n    T2["Tree 2<br/>Bootstrap 2<br/>Depth: 15"]\n    T3["Tree 3<br/>Bootstrap 3<br/>Depth: 11"]\n    TD["..."]\n    T100["Tree 100<br/>Bootstrap 100<br/>Depth: 14"]\n    end\n    NOTE["Each tree is different due to:<br/>1. Different bootstrap samples<br/>2. Different random features at splits"]\n    style T1 fill:#ADD8E6\n    style T2 fill:#90EE90\n    style T3 fill:#FFFACD\n    style T100 fill:#FFB6C1\n    style NOTE fill:#E6E6FA',
                    },
                    {
                        "step_number": 8,
                        "title": "Making Predictions: Classification",
                        "explanation": "For **classification**: pass the sample through ALL trees, collect each tree's vote, and use **majority voting**. The class with the most votes wins. Probability = proportion of trees voting for each class.",
                        "diagram_data": 'flowchart TB\n    NEW["New Sample X"]\n    NEW --> T1["Tree 1: Class A"]\n    NEW --> T2["Tree 2: Class B"]\n    NEW --> T3["Tree 3: Class A"]\n    NEW --> T4["Tree 4: Class A"]\n    NEW --> T5["Tree 5: Class B"]\n    T1 --> VOTE["Vote Count:<br/>A: 3 votes (60%)<br/>B: 2 votes (40%)"]\n    T2 --> VOTE\n    T3 --> VOTE\n    T4 --> VOTE\n    T5 --> VOTE\n    VOTE --> PRED["Prediction: Class A<br/>Probability: 0.60"]\n    style PRED fill:#90EE90\n    style T1 fill:#ADD8E6\n    style T3 fill:#ADD8E6\n    style T4 fill:#ADD8E6\n    style T2 fill:#FFB6C1\n    style T5 fill:#FFB6C1',
                    },
                    {
                        "step_number": 9,
                        "title": "Making Predictions: Regression",
                        "explanation": "For **regression**: pass the sample through all trees, collect each tree's numeric prediction, and compute the **average**. This averaging smooths out individual tree errors.",
                        "diagram_data": 'flowchart TB\n    NEW["New Sample X"]\n    NEW --> T1["Tree 1: 23.5"]\n    NEW --> T2["Tree 2: 25.1"]\n    NEW --> T3["Tree 3: 22.8"]\n    NEW --> T4["Tree 4: 24.2"]\n    NEW --> T5["Tree 5: 23.9"]\n    T1 --> AVG["Average:<br/>(23.5+25.1+22.8+24.2+23.9)/5"]\n    T2 --> AVG\n    T3 --> AVG\n    T4 --> AVG\n    T5 --> AVG\n    AVG --> PRED["Prediction: 23.9"]\n    style PRED fill:#90EE90\n    style AVG fill:#E6E6FA',
                    },
                    {
                        "step_number": 10,
                        "title": "Out-of-Bag (OOB) Error Estimation",
                        "explanation": "~37% of samples are left out of each bootstrap sample. For each sample, predict using only trees where it was **not** in the training set. This gives a free validation estimate without needing a separate test set!",
                        "diagram_data": 'flowchart TB\n    subgraph "Sample A"\n    SA["In: Tree 1, Tree 3<br/>Out: Tree 2, Tree 4, Tree 5"]\n    end\n    subgraph "OOB Prediction for A"\n    OOB["Use only Tree 2, 4, 5<br/>(trees that didn\'t see A)"]\n    PRED["OOB Prediction for A"]\n    end\n    SA --> OOB --> PRED\n    subgraph "OOB Score"\n    ALL["Do this for all samples"]\n    SCORE["OOB Accuracy ≈ Test Accuracy"]\n    end\n    PRED --> ALL --> SCORE\n    style SCORE fill:#90EE90\n    style OOB fill:#FFFACD',
                    },
                    {
                        "step_number": 11,
                        "title": "Feature Importance: Gini Importance",
                        "explanation": "**Gini importance** (or Mean Decrease in Impurity): sum up how much each feature reduces impurity across all trees and all splits. Features that create purer splits are more important.",
                        "diagram_data": 'flowchart TB\n    subgraph "Across All Trees"\n    T1S["Tree 1: F5 reduces Gini by 0.15"]\n    T2S["Tree 2: F5 reduces Gini by 0.12"]\n    T3S["Tree 3: F5 reduces Gini by 0.18"]\n    end\n    T1S --> SUM["Sum for F5:<br/>0.15 + 0.12 + 0.18 = 0.45"]\n    T2S --> SUM\n    T3S --> SUM\n    SUM --> NORM["Normalize across features"]\n    NORM --> IMP["F5 Importance: 0.23<br/>F1 Importance: 0.18<br/>F3 Importance: 0.15<br/>..."]\n    style IMP fill:#90EE90',
                    },
                    {
                        "step_number": 12,
                        "title": "Feature Importance: Permutation Importance",
                        "explanation": "**Permutation importance**: shuffle one feature's values and measure how much accuracy drops. Large drop = important feature. More reliable than Gini importance for correlated features.",
                        "diagram_data": 'flowchart TB\n    subgraph "Original"\n    O["OOB Accuracy: 0.92"]\n    end\n    subgraph "Shuffle Feature F5"\n    S["Shuffle F5 values randomly"]\n    P["New OOB Accuracy: 0.78"]\n    end\n    subgraph "Importance"\n    I["F5 Importance = 0.92 - 0.78 = 0.14"]\n    end\n    O --> S --> P --> I\n    R["Repeat for each feature"]\n    I --> R\n    style I fill:#90EE90\n    style P fill:#FFB6C1',
                    },
                    {
                        "step_number": 13,
                        "title": "Key Hyperparameters",
                        "explanation": "Important parameters to tune: **n_estimators** (number of trees), **max_features** (features per split), **max_depth** (tree depth), **min_samples_split**, **min_samples_leaf**, **bootstrap** (True/False).",
                        "diagram_data": 'flowchart TB\n    subgraph "Number of Trees"\n    N["n_estimators=100-500<br/>More trees = better but slower<br/>Diminishing returns after ~100"]\n    end\n    subgraph "Features per Split"\n    M["max_features=\'sqrt\' (classification)<br/>max_features=\'auto\' (regression)<br/>Lower = more diversity"]\n    end\n    subgraph "Tree Depth"\n    D["max_depth=None (grow fully)<br/>Deeper = lower bias<br/>Averaging handles variance"]\n    end\n    subgraph "Leaf Size"\n    L["min_samples_leaf=1<br/>Higher = more regularization"]\n    end\n    style N fill:#ADD8E6\n    style M fill:#90EE90\n    style D fill:#FFFACD\n    style L fill:#FFB6C1',
                    },
                    {
                        "step_number": 14,
                        "title": "Parallelization",
                        "explanation": "Random Forest is **embarrassingly parallel**: trees are independent and can be trained simultaneously. Set **n_jobs=-1** to use all CPU cores. Training and prediction both parallelize well.",
                        "diagram_data": 'flowchart TB\n    subgraph "n_jobs=-1 (8 cores)"\n    C1["Core 1: Trees 1-12"]\n    C2["Core 2: Trees 13-24"]\n    C3["Core 3: Trees 25-36"]\n    C4["Core 4: Trees 37-48"]\n    C5["Core 5: Trees 49-60"]\n    C6["Core 6: Trees 61-72"]\n    C7["Core 7: Trees 73-84"]\n    C8["Core 8: Trees 85-100"]\n    end\n    C1 --> DONE["All 100 trees in parallel"]\n    C2 --> DONE\n    C3 --> DONE\n    C4 --> DONE\n    C5 --> DONE\n    C6 --> DONE\n    C7 --> DONE\n    C8 --> DONE\n    DONE --> FAST["8x speedup!"]\n    style FAST fill:#90EE90',
                    },
                    {
                        "step_number": 15,
                        "title": "Random Forest vs Single Decision Tree",
                        "explanation": "Comparison: Single trees are fast and interpretable but overfit. Random Forests are slower and less interpretable but much more accurate and robust. The ensemble trades simplicity for performance.",
                        "diagram_data": 'flowchart TB\n    subgraph "Decision Tree"\n    DT1["Fast training"]\n    DT2["Easy to interpret"]\n    DT3["High variance (overfit)"]\n    DT4["Sensitive to data changes"]\n    end\n    subgraph "Random Forest"\n    RF1["Slower training"]\n    RF2["Black box"]\n    RF3["Low variance (stable)"]\n    RF4["Robust to noise"]\n    RF5["Built-in feature importance"]\n    RF6["OOB error estimation"]\n    end\n    style DT1 fill:#90EE90\n    style DT2 fill:#90EE90\n    style DT3 fill:#FFB6C1\n    style DT4 fill:#FFB6C1\n    style RF1 fill:#FFFACD\n    style RF2 fill:#FFFACD\n    style RF3 fill:#90EE90\n    style RF4 fill:#90EE90\n    style RF5 fill:#90EE90\n    style RF6 fill:#90EE90',
                    },
                    {
                        "step_number": 16,
                        "title": "scikit-learn Implementation",
                        "explanation": "Using Random Forest in scikit-learn is straightforward. Import the classifier or regressor, fit on training data, predict, and access feature importances and OOB score.",
                        "diagram_data": 'flowchart TB\n    subgraph "Code Flow"\n    C1["from sklearn.ensemble import<br/>RandomForestClassifier"]\n    C2["rf = RandomForestClassifier(<br/>n_estimators=100,<br/>max_features=\'sqrt\',<br/>oob_score=True,<br/>n_jobs=-1)"]\n    C3["rf.fit(X_train, y_train)"]\n    C4["predictions = rf.predict(X_test)"]\n    C5["probabilities = rf.predict_proba(X_test)"]\n    C6["importance = rf.feature_importances_"]\n    C7["oob = rf.oob_score_"]\n    end\n    C1 --> C2 --> C3 --> C4\n    C3 --> C5\n    C3 --> C6\n    C3 --> C7\n    style C4 fill:#90EE90\n    style C5 fill:#ADD8E6\n    style C6 fill:#FFFACD\n    style C7 fill:#FFB6C1',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_extra_trees_visual(self):
        """Seed Extra Trees (Extremely Randomized Trees) visual topic."""
        subject = self.get_or_create_subject(
            "scikit-learn", "scikit-learn", "ML Frameworks"
        )

        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="extra-trees",
            defaults={
                "title": "ExtraTrees: Extremely Randomized Trees",
                "description": "Learn how ExtraTrees adds even more randomization than Random Forest for faster training and lower variance",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "intermediate",
                "estimated_time_minutes": 10,
                "tags": [
                    "extra-trees",
                    "ensemble",
                    "randomization",
                    "classification",
                    "regression",
                ],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "ExtraTrees: Even More Random Than Random Forest",
                        "explanation": "**Extremely Randomized Trees (ExtraTrees)** takes the Random Forest concept further: instead of finding the *best* split among random features, it uses *random* split thresholds. This extra randomness trades a bit more bias for much lower variance.",
                        "diagram_data": 'flowchart LR\n    subgraph "Random Forest"\n    RF1["Random features"]\n    RF2["BEST split threshold"]\n    end\n    subgraph "ExtraTrees"\n    ET1["Random features"]\n    ET2["RANDOM split threshold"]\n    end\n    RF2 --> MORE["More randomness"]\n    ET2 --> MORE\n    MORE --> BENEFIT["Lower variance<br/>Faster training"]\n    style RF2 fill:#FFFACD\n    style ET2 fill:#90EE90\n    style BENEFIT fill:#ADD8E6',
                    },
                    {
                        "step_number": 1,
                        "title": "Key Difference #1: No Bootstrap Sampling",
                        "explanation": "By default, ExtraTrees uses the **entire dataset** for each tree (bootstrap=False). Random Forest samples with replacement. Using all data gives each tree more information but less diversity from sampling.",
                        "diagram_data": 'flowchart TB\n    DATA["Original Data (N samples)"]\n    subgraph "Random Forest"\n    RF["Bootstrap sample<br/>N samples WITH replacement<br/>~63% unique samples"]\n    end\n    subgraph "ExtraTrees (default)"\n    ET["Use ALL N samples<br/>No sampling<br/>100% of data"]\n    end\n    DATA --> RF\n    DATA --> ET\n    style RF fill:#FFFACD\n    style ET fill:#90EE90',
                    },
                    {
                        "step_number": 2,
                        "title": "Key Difference #2: Random Split Thresholds",
                        "explanation": "This is the **main innovation**. When splitting a node: Random Forest tries all possible thresholds to find the best. ExtraTrees picks ONE random threshold per feature and uses the best among those. Much faster!",
                        "diagram_data": 'flowchart TB\n    subgraph "Random Forest Split Finding"\n    RF1["Feature X1: values [0.1, 0.3, 0.5, 0.7, 0.9]"]\n    RF2["Try ALL thresholds:<br/>0.2, 0.4, 0.6, 0.8"]\n    RF3["Calculate gain for each"]\n    RF4["Pick best: 0.4 (gain=0.35)"]\n    end\n    subgraph "ExtraTrees Split Finding"\n    ET1["Feature X1: values [0.1, 0.3, 0.5, 0.7, 0.9]"]\n    ET2["Pick ONE random threshold:<br/>0.6"]\n    ET3["Calculate gain: 0.28"]\n    ET4["Done! Use 0.6"]\n    end\n    RF1 --> RF2 --> RF3 --> RF4\n    ET1 --> ET2 --> ET3 --> ET4\n    style RF3 fill:#FFB6C1\n    style ET2 fill:#90EE90\n    style ET4 fill:#90EE90',
                    },
                    {
                        "step_number": 3,
                        "title": "How ExtraTrees Finds a Split",
                        "explanation": "At each node: (1) Select random subset of features (like RF), (2) For EACH selected feature, pick ONE random threshold between min and max, (3) Evaluate gain for each, (4) Use the feature+threshold with best gain.",
                        "diagram_data": 'flowchart TB\n    NODE["Node with 500 samples"]\n    NODE --> SELECT["1. Select √p random features<br/>e.g., F2, F5, F8"]\n    SELECT --> RAND["2. Random threshold per feature"]\n    subgraph "Random Thresholds"\n    R1["F2: range [0,10]<br/>Random: 4.7"]\n    R2["F5: range [0,1]<br/>Random: 0.33"]\n    R3["F8: range [-5,5]<br/>Random: 1.2"]\n    end\n    RAND --> R1\n    RAND --> R2\n    RAND --> R3\n    R1 --> EVAL["3. Evaluate gains"]\n    R2 --> EVAL\n    R3 --> EVAL\n    EVAL --> BEST["4. Best: F5 < 0.33<br/>gain = 0.42"]\n    style BEST fill:#90EE90',
                    },
                    {
                        "step_number": 4,
                        "title": "Why Random Thresholds Work",
                        "explanation": 'Intuition: with enough trees, random thresholds will eventually "find" good splits. Individual trees may be weaker, but the ensemble averages out the randomness. More trees compensate for suboptimal individual splits.',
                        "diagram_data": 'flowchart TB\n    subgraph "Single Tree"\n    ST["Random thresholds<br/>= suboptimal splits<br/>= weaker tree"]\n    end\n    subgraph "Many Trees (100+)"\n    MT["Random variations<br/>cancel out"]\n    AVG["Average predictions"]\n    RESULT["Strong ensemble<br/>despite weak individuals"]\n    end\n    ST --> MT --> AVG --> RESULT\n    style ST fill:#FFB6C1\n    style RESULT fill:#90EE90',
                    },
                    {
                        "step_number": 5,
                        "title": "Training Speed Comparison",
                        "explanation": "ExtraTrees is **significantly faster** to train. Finding the optimal split requires sorting or histogram computation. Random thresholds skip this entirely - just pick a number and evaluate once!",
                        "diagram_data": 'flowchart LR\n    subgraph "Random Forest"\n    RF1["For each feature:"]\n    RF2["Sort values or<br/>build histogram"]\n    RF3["Try O(n) thresholds"]\n    RF4["O(n × features)"]\n    end\n    subgraph "ExtraTrees"\n    ET1["For each feature:"]\n    ET2["Pick random number"]\n    ET3["Evaluate once"]\n    ET4["O(features)"]\n    end\n    RF4 --> SLOW["Slower"]\n    ET4 --> FAST["Much Faster!"]\n    style SLOW fill:#FFB6C1\n    style FAST fill:#90EE90',
                    },
                    {
                        "step_number": 6,
                        "title": "Bias-Variance Trade-off",
                        "explanation": "ExtraTrees has **higher bias** (suboptimal splits) but **lower variance** (more randomization smooths predictions). For many problems, especially noisy data, this trade-off is favorable.",
                        "diagram_data": 'flowchart TB\n    subgraph "Random Forest"\n    RFB["Lower Bias<br/>(optimal splits)"]\n    RFV["Higher Variance<br/>(less randomization)"]\n    end\n    subgraph "ExtraTrees"\n    ETB["Higher Bias<br/>(random splits)"]\n    ETV["Lower Variance<br/>(extreme randomization)"]\n    end\n    subgraph "When ExtraTrees Wins"\n    W1["Noisy data"]\n    W2["Risk of overfitting"]\n    W3["Need fast training"]\n    end\n    style RFB fill:#90EE90\n    style RFV fill:#FFB6C1\n    style ETB fill:#FFFACD\n    style ETV fill:#90EE90\n    style W1 fill:#ADD8E6\n    style W2 fill:#ADD8E6\n    style W3 fill:#ADD8E6',
                    },
                    {
                        "step_number": 7,
                        "title": "Making Predictions",
                        "explanation": "Prediction works exactly like Random Forest: pass sample through all trees, collect predictions, use **majority vote** (classification) or **average** (regression). The ensemble mechanism is identical.",
                        "diagram_data": 'flowchart TB\n    NEW["New Sample"]\n    NEW --> T1["Tree 1: Class A"]\n    NEW --> T2["Tree 2: Class B"]\n    NEW --> T3["Tree 3: Class A"]\n    NEW --> T4["Tree 4: Class A"]\n    NEW --> T5["Tree 5: Class A"]\n    T1 --> VOTE["Majority Vote"]\n    T2 --> VOTE\n    T3 --> VOTE\n    T4 --> VOTE\n    T5 --> VOTE\n    VOTE --> PRED["Prediction: Class A<br/>(4 out of 5 trees)"]\n    style PRED fill:#90EE90',
                    },
                    {
                        "step_number": 8,
                        "title": "No OOB Score by Default",
                        "explanation": 'Since ExtraTrees uses all data (no bootstrap), there\'s no "out-of-bag" samples by default. To get OOB error, set **bootstrap=True**, but this makes it more like Random Forest.',
                        "diagram_data": 'flowchart TB\n    subgraph "ExtraTrees (default)"\n    ET1["bootstrap=False"]\n    ET2["All samples used"]\n    ET3["No OOB samples"]\n    ET4["oob_score not available"]\n    end\n    subgraph "ExtraTrees (with bootstrap)"\n    ETB1["bootstrap=True"]\n    ETB2["~63% samples per tree"]\n    ETB3["~37% OOB samples"]\n    ETB4["oob_score available"]\n    end\n    ET1 --> ET2 --> ET3 --> ET4\n    ETB1 --> ETB2 --> ETB3 --> ETB4\n    style ET4 fill:#FFB6C1\n    style ETB4 fill:#90EE90',
                    },
                    {
                        "step_number": 9,
                        "title": "Feature Importance",
                        "explanation": "ExtraTrees supports the same feature importance methods as Random Forest: **Gini importance** (mean decrease in impurity) and **permutation importance**. Interpretation is identical.",
                        "diagram_data": 'flowchart TB\n    subgraph "Feature Importance Methods"\n    G["Gini Importance<br/>feature_importances_"]\n    P["Permutation Importance<br/>sklearn.inspection"]\n    end\n    G --> R1["Sum impurity decrease<br/>across all trees/splits"]\n    P --> R2["Shuffle feature,<br/>measure accuracy drop"]\n    R1 --> IMP["Importance Ranking:<br/>F5: 0.25<br/>F2: 0.18<br/>F8: 0.15<br/>..."]\n    R2 --> IMP\n    style IMP fill:#90EE90',
                    },
                    {
                        "step_number": 10,
                        "title": "Side-by-Side: RF vs ExtraTrees",
                        "explanation": "Quick comparison of the two ensemble methods. Both are powerful; choice depends on your data and requirements.",
                        "diagram_data": 'flowchart TB\n    subgraph "Random Forest"\n    RF1["Bootstrap: Yes"]\n    RF2["Split threshold: Optimal"]\n    RF3["Training speed: Moderate"]\n    RF4["Bias: Lower"]\n    RF5["Variance: Higher"]\n    RF6["OOB score: Yes"]\n    end\n    subgraph "ExtraTrees"\n    ET1["Bootstrap: No (default)"]\n    ET2["Split threshold: Random"]\n    ET3["Training speed: Faster"]\n    ET4["Bias: Higher"]\n    ET5["Variance: Lower"]\n    ET6["OOB score: No (default)"]\n    end\n    style RF2 fill:#FFFACD\n    style ET2 fill:#90EE90\n    style RF3 fill:#FFFACD\n    style ET3 fill:#90EE90\n    style RF5 fill:#FFB6C1\n    style ET5 fill:#90EE90',
                    },
                    {
                        "step_number": 11,
                        "title": "When to Use ExtraTrees",
                        "explanation": "Choose ExtraTrees when: (1) training speed is critical, (2) data is noisy, (3) you're overfitting with RF, (4) you have many features. Try both and compare validation scores!",
                        "diagram_data": 'flowchart TB\n    Q{"Which to choose?"}\n    Q -->|"Need fast training"| ET["ExtraTrees"]\n    Q -->|"Noisy data"| ET\n    Q -->|"Overfitting issues"| ET\n    Q -->|"Need OOB score"| RF["Random Forest"]\n    Q -->|"Interpretability matters"| RF\n    Q -->|"Not sure"| BOTH["Try both!<br/>Compare CV scores"]\n    style ET fill:#90EE90\n    style RF fill:#ADD8E6\n    style BOTH fill:#FFFACD',
                    },
                    {
                        "step_number": 12,
                        "title": "Key Hyperparameters",
                        "explanation": "ExtraTrees shares most parameters with Random Forest. Key ones: **n_estimators**, **max_features**, **max_depth**, **min_samples_split**, **bootstrap** (False by default!).",
                        "diagram_data": 'flowchart TB\n    subgraph "Important Parameters"\n    P1["n_estimators=100<br/>Number of trees"]\n    P2["max_features=\'sqrt\'<br/>Features per split"]\n    P3["max_depth=None<br/>Tree depth limit"]\n    P4["min_samples_split=2<br/>Min samples to split"]\n    P5["bootstrap=False<br/>Use all data (default)"]\n    end\n    subgraph "Tuning Tips"\n    T1["More trees rarely hurts"]\n    T2["Lower max_features =<br/>more randomization"]\n    T3["Set bootstrap=True<br/>for OOB score"]\n    end\n    style P5 fill:#FFFACD\n    style T3 fill:#ADD8E6',
                    },
                    {
                        "step_number": 13,
                        "title": "scikit-learn Implementation",
                        "explanation": "Using ExtraTrees is nearly identical to Random Forest. Just import **ExtraTreesClassifier** or **ExtraTreesRegressor** instead.",
                        "diagram_data": 'flowchart TB\n    subgraph "Code"\n    C1["from sklearn.ensemble import<br/>ExtraTreesClassifier"]\n    C2["et = ExtraTreesClassifier(<br/>n_estimators=100,<br/>max_features=\'sqrt\',<br/>n_jobs=-1,<br/>random_state=42)"]\n    C3["et.fit(X_train, y_train)"]\n    C4["predictions = et.predict(X_test)"]\n    C5["importance = et.feature_importances_"]\n    end\n    C1 --> C2 --> C3 --> C4\n    C3 --> C5\n    subgraph "For OOB Score"\n    OOB["ExtraTreesClassifier(<br/>bootstrap=True,<br/>oob_score=True)"]\n    end\n    style C4 fill:#90EE90\n    style C5 fill:#FFFACD\n    style OOB fill:#ADD8E6',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_logistic_regression_visual(self):
        """Seed Logistic Regression visual topic."""
        subject = self.get_or_create_subject(
            "scikit-learn", "scikit-learn", "ML Frameworks"
        )

        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="logistic-regression",
            defaults={
                "title": "Logistic Regression: Complete Guide",
                "description": "Master logistic regression from sigmoid function to multi-class classification, including regularization and interpretation",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "intermediate",
                "estimated_time_minutes": 15,
                "tags": [
                    "logistic-regression",
                    "classification",
                    "sigmoid",
                    "probability",
                    "linear-model",
                ],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "What is Logistic Regression?",
                        "explanation": "Despite its name, **Logistic Regression** is a **classification** algorithm. It predicts the probability of a binary outcome using a linear combination of features transformed by the sigmoid function.",
                        "diagram_data": 'flowchart LR\n    subgraph "Linear Regression"\n    LR["Predicts continuous values<br/>y = mx + b<br/>Range: -∞ to +∞"]\n    end\n    subgraph "Logistic Regression"\n    LOG["Predicts probabilities<br/>P(y=1) = σ(mx + b)<br/>Range: 0 to 1"]\n    end\n    LR --> |"Add sigmoid"| LOG\n    style LOG fill:#90EE90',
                    },
                    {
                        "step_number": 1,
                        "title": "The Problem: Linear Output → Probability",
                        "explanation": "A linear model outputs any real number, but we need probabilities (0 to 1). We can't just clip values - we need a smooth transformation that maps (-∞, +∞) to (0, 1).",
                        "diagram_data": 'flowchart TB\n    LINEAR["Linear: z = w₁x₁ + w₂x₂ + ... + b<br/>Output: -∞ to +∞"]\n    PROBLEM["Problem: z=5 means what probability?<br/>z=-3 means what probability?"]\n    SOLUTION["Solution: Transform with sigmoid<br/>σ(z) squashes to (0, 1)"]\n    LINEAR --> PROBLEM --> SOLUTION\n    style PROBLEM fill:#FFB6C1\n    style SOLUTION fill:#90EE90',
                    },
                    {
                        "step_number": 2,
                        "title": "The Sigmoid (Logistic) Function",
                        "explanation": "The **sigmoid function** σ(z) = 1 / (1 + e⁻ᶻ) transforms any real number to a value between 0 and 1. It's S-shaped: negative inputs → near 0, positive inputs → near 1, zero → exactly 0.5.",
                        "diagram_data": 'flowchart TB\n    subgraph "Sigmoid Function: σ(z) = 1 / (1 + e⁻ᶻ)"\n    F["Input z → Output σ(z)"]\n    end\n    subgraph "Key Values"\n    V1["z = -∞ → σ(z) ≈ 0"]\n    V2["z = -2 → σ(z) ≈ 0.12"]\n    V3["z = 0 → σ(z) = 0.5"]\n    V4["z = +2 → σ(z) ≈ 0.88"]\n    V5["z = +∞ → σ(z) ≈ 1"]\n    end\n    subgraph "Properties"\n    P1["Always between 0 and 1"]\n    P2["Smooth and differentiable"]\n    P3["σ(-z) = 1 - σ(z)"]\n    end\n    style V3 fill:#FFFACD\n    style P1 fill:#90EE90',
                    },
                    {
                        "step_number": 3,
                        "title": "The Complete Model",
                        "explanation": "Logistic regression combines linear combination with sigmoid: **P(y=1|X) = σ(wᵀX + b)**. The linear part z = wᵀX + b is called the **log-odds** or **logit**.",
                        "diagram_data": 'flowchart LR\n    X["Features<br/>X = [x₁, x₂, ..., xₙ]"]\n    LINEAR["Linear combination<br/>z = w₁x₁ + w₂x₂ + ... + b"]\n    SIGMOID["Sigmoid<br/>σ(z) = 1/(1+e⁻ᶻ)"]\n    PROB["Probability<br/>P(y=1) ∈ (0,1)"]\n    X --> LINEAR --> SIGMOID --> PROB\n    style PROB fill:#90EE90',
                    },
                    {
                        "step_number": 4,
                        "title": "Log-Odds (Logit) Interpretation",
                        "explanation": "The linear part z represents **log-odds**: z = log(P/(1-P)). This means odds = eᶻ. A coefficient wᵢ means: increasing xᵢ by 1 multiplies the odds by e^(wᵢ).",
                        "diagram_data": 'flowchart TB\n    subgraph "Transformations"\n    P["Probability P"]\n    ODDS["Odds = P / (1-P)"]\n    LOGODDS["Log-odds = log(odds) = z"]\n    end\n    P -->|"P/(1-P)"| ODDS -->|"log()"| LOGODDS\n    subgraph "Example: P = 0.75"\n    E1["Odds = 0.75/0.25 = 3<br/>(3:1 in favor)"]\n    E2["Log-odds = log(3) ≈ 1.1"]\n    end\n    style LOGODDS fill:#90EE90',
                    },
                    {
                        "step_number": 5,
                        "title": "Making Predictions",
                        "explanation": "Compute z = wᵀX + b, apply sigmoid to get probability P, then use a **threshold** (default 0.5) to classify. P ≥ 0.5 → Class 1, P < 0.5 → Class 0.",
                        "diagram_data": 'flowchart TB\n    X["Input: x₁=2, x₂=3"]\n    Z["z = 0.5(2) + 0.8(3) - 1.5 = 1.9"]\n    P["P = σ(1.9) = 1/(1+e⁻¹·⁹) ≈ 0.87"]\n    T{"P ≥ 0.5?"}\n    C1["Predict: Class 1"]\n    C0["Predict: Class 0"]\n    X --> Z --> P --> T\n    T -->|"0.87 ≥ 0.5: Yes"| C1\n    T -->|No| C0\n    style C1 fill:#90EE90',
                    },
                    {
                        "step_number": 6,
                        "title": "The Decision Boundary",
                        "explanation": "The **decision boundary** is where P = 0.5, which means z = 0 (since σ(0) = 0.5). This is a **linear boundary**: w₁x₁ + w₂x₂ + ... + b = 0 (a hyperplane).",
                        "diagram_data": 'flowchart TB\n    subgraph "Decision Boundary"\n    DB["z = w₁x₁ + w₂x₂ + b = 0<br/>This is a straight line (2D)<br/>or hyperplane (higher D)"]\n    end\n    subgraph "Classification Regions"\n    R1["z > 0 → σ(z) > 0.5 → Class 1"]\n    R2["z < 0 → σ(z) < 0.5 → Class 0"]\n    R3["z = 0 → σ(z) = 0.5 → Boundary"]\n    end\n    style R1 fill:#90EE90\n    style R2 fill:#FFB6C1\n    style R3 fill:#FFFACD',
                    },
                    {
                        "step_number": 7,
                        "title": "Training: Maximum Likelihood Estimation",
                        "explanation": "We find weights that **maximize the likelihood** of observing our training data. For each sample, the likelihood is P if y=1, or (1-P) if y=0. We maximize the product of all likelihoods.",
                        "diagram_data": 'flowchart TB\n    subgraph "Likelihood for one sample"\n    L1["If y=1: L = P(y=1) = σ(z)"]\n    L2["If y=0: L = P(y=0) = 1 - σ(z)"]\n    L3["Combined: L = σ(z)^y × (1-σ(z))^(1-y)"]\n    end\n    subgraph "Total Likelihood"\n    TL["L_total = ∏ Lᵢ for all samples"]\n    ML["Maximize L_total<br/>(or minimize -log L_total)"]\n    end\n    L3 --> TL --> ML\n    style ML fill:#90EE90',
                    },
                    {
                        "step_number": 8,
                        "title": "Loss Function: Cross-Entropy (Log Loss)",
                        "explanation": "We minimize **cross-entropy loss** (negative log-likelihood): L = -[y·log(P) + (1-y)·log(1-P)]. This penalizes confident wrong predictions heavily.",
                        "diagram_data": 'flowchart TB\n    subgraph "Cross-Entropy Loss"\n    F["L = -[y·log(P) + (1-y)·log(1-P)]"]\n    end\n    subgraph "Intuition"\n    I1["If y=1: L = -log(P)<br/>Want P→1, so L→0"]\n    I2["If y=0: L = -log(1-P)<br/>Want P→0, so L→0"]\n    I3["Wrong confident prediction<br/>→ Very high loss"]\n    end\n    subgraph "Example"\n    E1["y=1, P=0.9: L = -log(0.9) ≈ 0.1"]\n    E2["y=1, P=0.1: L = -log(0.1) ≈ 2.3"]\n    end\n    style I3 fill:#FFB6C1\n    style E1 fill:#90EE90\n    style E2 fill:#FFB6C1',
                    },
                    {
                        "step_number": 9,
                        "title": "Optimization: Gradient Descent",
                        "explanation": "Unlike linear regression, there's **no closed-form solution**. We use **gradient descent** (or variants like L-BFGS, Newton's method) to iteratively find optimal weights.",
                        "diagram_data": 'flowchart TB\n    subgraph "Gradient Descent"\n    INIT["Initialize weights w, b"]\n    COMPUTE["Compute predictions P = σ(Xw + b)"]\n    LOSS["Compute loss L"]\n    GRAD["Compute gradients ∂L/∂w, ∂L/∂b"]\n    UPDATE["Update: w = w - α·∂L/∂w"]\n    CHECK{"Converged?"}\n    end\n    INIT --> COMPUTE --> LOSS --> GRAD --> UPDATE --> CHECK\n    CHECK -->|No| COMPUTE\n    CHECK -->|Yes| DONE["Done!"]\n    style DONE fill:#90EE90',
                    },
                    {
                        "step_number": 10,
                        "title": "Regularization: Preventing Overfitting",
                        "explanation": "Regularization adds a penalty for large weights. **L2 (Ridge)** shrinks all weights. **L1 (Lasso)** can zero out weights (feature selection). **Elastic Net** combines both.",
                        "diagram_data": 'flowchart TB\n    subgraph "Regularized Loss"\n    BASE["Base: Cross-entropy loss"]\n    L2["L2 (Ridge): + λ·Σwᵢ²<br/>Shrinks weights"]\n    L1["L1 (Lasso): + λ·Σ|wᵢ|<br/>Zeros out weights"]\n    EN["Elastic Net: + λ₁·Σ|wᵢ| + λ₂·Σwᵢ²"]\n    end\n    subgraph "scikit-learn"\n    SK["penalty=\'l2\' (default)<br/>penalty=\'l1\'<br/>penalty=\'elasticnet\'<br/>C = 1/λ (inverse regularization)"]\n    end\n    style L2 fill:#ADD8E6\n    style L1 fill:#90EE90\n    style SK fill:#FFFACD',
                    },
                    {
                        "step_number": 11,
                        "title": "Multi-Class: One-vs-Rest (OvR)",
                        "explanation": 'For K classes, train K binary classifiers: "Class k vs all others". To predict, run all K classifiers and pick the class with highest probability.',
                        "diagram_data": 'flowchart TB\n    subgraph "3-Class Problem"\n    CLS["Classes: A, B, C"]\n    end\n    subgraph "Train 3 Binary Classifiers"\n    M1["Model 1: A vs (B,C)"]\n    M2["Model 2: B vs (A,C)"]\n    M3["Model 3: C vs (A,B)"]\n    end\n    subgraph "Predict"\n    P1["P(A) = 0.7"]\n    P2["P(B) = 0.2"]\n    P3["P(C) = 0.4"]\n    PRED["Predict: Class A (highest)"]\n    end\n    CLS --> M1 & M2 & M3\n    M1 --> P1\n    M2 --> P2\n    M3 --> P3\n    P1 & P2 & P3 --> PRED\n    style PRED fill:#90EE90',
                    },
                    {
                        "step_number": 12,
                        "title": "Multi-Class: Softmax (Multinomial)",
                        "explanation": "**Softmax regression** trains one model with K sets of weights. The softmax function ensures probabilities sum to 1: P(k) = e^(zₖ) / Σe^(zⱼ). More efficient than OvR.",
                        "diagram_data": 'flowchart TB\n    subgraph "Softmax Function"\n    F["P(class k) = e^(zₖ) / Σⱼ e^(zⱼ)"]\n    end\n    subgraph "Example: 3 classes"\n    Z["z₁=2, z₂=1, z₃=0"]\n    E["e²=7.4, e¹=2.7, e⁰=1.0<br/>Sum = 11.1"]\n    P["P₁=7.4/11.1=0.67<br/>P₂=2.7/11.1=0.24<br/>P₃=1.0/11.1=0.09"]\n    SUM["Sum = 1.0 ✓"]\n    end\n    Z --> E --> P --> SUM\n    style SUM fill:#90EE90',
                    },
                    {
                        "step_number": 13,
                        "title": "Interpreting Coefficients",
                        "explanation": "Each coefficient wᵢ is the change in **log-odds** per unit increase in xᵢ. **Odds ratio** = e^(wᵢ) tells you how odds multiply. Positive w → increases probability of class 1.",
                        "diagram_data": 'flowchart TB\n    subgraph "Interpretation"\n    W["Coefficient w₁ = 0.5"]\n    LO["Log-odds increases by 0.5<br/>when x₁ increases by 1"]\n    OR["Odds ratio = e^0.5 ≈ 1.65<br/>Odds multiply by 1.65"]\n    end\n    subgraph "Example"\n    E1["w_age = 0.03<br/>OR = 1.03"]\n    E2["Each year older:<br/>odds increase by 3%"]\n    end\n    W --> LO --> OR\n    style OR fill:#90EE90',
                    },
                    {
                        "step_number": 14,
                        "title": "Feature Scaling Matters!",
                        "explanation": "Logistic regression is sensitive to feature scales. **Always scale features** (StandardScaler or MinMaxScaler) for faster convergence and meaningful coefficient comparison.",
                        "diagram_data": 'flowchart TB\n    subgraph "Without Scaling"\n    WO1["Age: 0-100"]\n    WO2["Income: 0-1,000,000"]\n    WO3["Coefficients not comparable"]\n    WO4["Slow convergence"]\n    end\n    subgraph "With StandardScaler"\n    WS1["Age: mean=0, std=1"]\n    WS2["Income: mean=0, std=1"]\n    WS3["Coefficients comparable"]\n    WS4["Fast convergence"]\n    end\n    style WO4 fill:#FFB6C1\n    style WS4 fill:#90EE90',
                    },
                    {
                        "step_number": 15,
                        "title": "Threshold Tuning",
                        "explanation": "Default threshold is 0.5, but you can adjust it. Lower threshold → more Class 1 predictions (higher recall). Higher threshold → more Class 0 predictions (higher precision).",
                        "diagram_data": 'flowchart TB\n    subgraph "Threshold Effects"\n    T1["Threshold = 0.3<br/>More Class 1 predictions<br/>Higher recall, lower precision"]\n    T2["Threshold = 0.5<br/>Default balance"]\n    T3["Threshold = 0.7<br/>Fewer Class 1 predictions<br/>Lower recall, higher precision"]\n    end\n    subgraph "Use Case"\n    U1["Medical diagnosis: Low threshold<br/>(don\'t miss positives)"]\n    U2["Spam filter: High threshold<br/>(don\'t block good email)"]\n    end\n    style U1 fill:#FFB6C1\n    style U2 fill:#ADD8E6',
                    },
                    {
                        "step_number": 16,
                        "title": "scikit-learn Implementation",
                        "explanation": "Use LogisticRegression with key parameters: C (inverse regularization), penalty, solver, multi_class, max_iter. Access coefficients with coef_ and intercept_.",
                        "diagram_data": 'flowchart TB\n    subgraph "Code"\n    C1["from sklearn.linear_model import<br/>LogisticRegression"]\n    C2["lr = LogisticRegression(<br/>C=1.0,<br/>penalty=\'l2\',<br/>solver=\'lbfgs\',<br/>max_iter=100)"]\n    C3["lr.fit(X_train, y_train)"]\n    C4["predictions = lr.predict(X_test)"]\n    C5["probabilities = lr.predict_proba(X_test)"]\n    C6["coefficients = lr.coef_<br/>intercept = lr.intercept_"]\n    end\n    C1 --> C2 --> C3 --> C4\n    C3 --> C5\n    C3 --> C6\n    style C4 fill:#90EE90\n    style C5 fill:#ADD8E6\n    style C6 fill:#FFFACD',
                    },
                    {
                        "step_number": 17,
                        "title": "When to Use Logistic Regression",
                        "explanation": "Logistic regression works well for linearly separable data, when interpretability matters, as a baseline model, and when you need probability outputs. It struggles with non-linear boundaries.",
                        "diagram_data": 'flowchart TB\n    subgraph "Good For"\n    G1["Linear decision boundaries"]\n    G2["Interpretable coefficients"]\n    G3["Probability estimates"]\n    G4["Baseline model"]\n    G5["High-dimensional sparse data"]\n    end\n    subgraph "Not Good For"\n    B1["Complex non-linear patterns"]\n    B2["Feature interactions (need to add manually)"]\n    B3["When more accuracy needed"]\n    end\n    style G1 fill:#90EE90\n    style G2 fill:#90EE90\n    style B1 fill:#FFB6C1\n    style B3 fill:#FFB6C1',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_isolation_forest_visual(self):
        """Seed Isolation Forest visual topic."""
        subject = self.get_or_create_subject(
            "scikit-learn", "scikit-learn", "ML Frameworks"
        )

        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="isolation-forest",
            defaults={
                "title": "Isolation Forest: Anomaly Detection",
                "description": "Learn how Isolation Forest detects anomalies by isolating observations using random splits",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "intermediate",
                "estimated_time_minutes": 10,
                "tags": [
                    "isolation-forest",
                    "anomaly-detection",
                    "unsupervised-learning",
                    "outliers",
                ],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "The Problem: Anomaly Detection",
                        "explanation": "**Anomaly detection** finds data points that are significantly different from the majority. Use cases include fraud detection, network intrusion, manufacturing defects, and medical diagnosis. Traditional methods struggle with high-dimensional data.",
                        "diagram_data": 'graph TB\n    subgraph "Normal Data (Majority)"\n    N1["Transaction: $50"]\n    N2["Transaction: $75"]\n    N3["Transaction: $60"]\n    N4["Transaction: $45"]\n    end\n    subgraph "Anomalies (Rare)"\n    A1["Transaction: $50,000"]\n    A2["Transaction: $0.01"]\n    end\n    style A1 fill:#FFB6C1\n    style A2 fill:#FFB6C1\n    style N1 fill:#90EE90\n    style N2 fill:#90EE90\n    style N3 fill:#90EE90\n    style N4 fill:#90EE90',
                    },
                    {
                        "step_number": 1,
                        "title": "Key Insight: Anomalies are Easy to Isolate",
                        "explanation": "Isolation Forest is based on a simple observation: **anomalies are few and different**. Because they're rare and have unusual feature values, they can be isolated with fewer random splits than normal points.",
                        "diagram_data": 'graph LR\n    subgraph "2D Feature Space"\n    direction TB\n    Cluster["Normal points<br/>(clustered together)"]\n    Outlier["Anomaly<br/>(isolated)"]\n    end\n    Cluster --> |"Hard to isolate<br/>Many splits needed"| C1["Deep in tree"]\n    Outlier --> |"Easy to isolate<br/>Few splits needed"| O1["Near root"]\n    style Outlier fill:#FFB6C1\n    style Cluster fill:#90EE90\n    style O1 fill:#FFB6C1\n    style C1 fill:#90EE90',
                    },
                    {
                        "step_number": 2,
                        "title": "Building an Isolation Tree",
                        "explanation": "An **Isolation Tree (iTree)** is built by randomly selecting a feature and a random split value between the feature's min and max. This process repeats recursively until each point is isolated or max depth is reached.",
                        "diagram_data": 'graph TB\n    Root["All Data (100 points)"]\n    Root --> |"Random: Feature X < 0.4"| L1["Left: 60 points"]\n    Root --> |"Feature X >= 0.4"| R1["Right: 40 points"]\n    L1 --> |"Random: Feature Y < 0.7"| L2["35 points"]\n    L1 --> |"Feature Y >= 0.7"| R2["25 points"]\n    R1 --> |"Random: Feature Z < 0.2"| L3["15 points"]\n    R1 --> |"Feature Z >= 0.2"| R3["25 points"]\n    style Root fill:#E6E6FA\n    Note["Splits are RANDOM<br/>Not optimized like Decision Trees"]',
                    },
                    {
                        "step_number": 3,
                        "title": "Isolating a Normal Point",
                        "explanation": "A **normal point** lives in a dense region with many similar points. It takes **many random splits** to finally isolate it from its neighbors. This results in a **long path** from root to leaf.",
                        "diagram_data": 'graph TB\n    Root["Start"] --> S1["Split 1"]\n    S1 --> S2["Split 2"]\n    S2 --> S3["Split 3"]\n    S3 --> S4["Split 4"]\n    S4 --> S5["Split 5"]\n    S5 --> S6["Split 6"]\n    S6 --> Leaf["Normal Point<br/>Path Length = 6"]\n    style Leaf fill:#90EE90\n    style Root fill:#E6E6FA',
                    },
                    {
                        "step_number": 4,
                        "title": "Isolating an Anomaly",
                        "explanation": "An **anomaly** has unusual feature values that make it easy to separate from the rest. A random split is likely to isolate it quickly, resulting in a **short path** from root to leaf.",
                        "diagram_data": 'graph TB\n    Root["Start"] --> S1["Split 1"]\n    S1 --> Leaf["Anomaly!<br/>Path Length = 1"]\n    S1 --> Continue["...rest of tree..."]\n    style Leaf fill:#FFB6C1\n    style Root fill:#E6E6FA\n    style Continue fill:#EEEEEE',
                    },
                    {
                        "step_number": 5,
                        "title": "Path Length Comparison",
                        "explanation": "The **path length** (number of edges from root to leaf) is the key metric. Anomalies have **shorter average path lengths** across multiple trees. This is the basis for the anomaly score.",
                        "diagram_data": 'graph LR\n    subgraph "Normal Point"\n    NP["Path lengths:<br/>6, 7, 5, 8, 6<br/>Average: 6.4"]\n    end\n    subgraph "Anomaly"\n    AP["Path lengths:<br/>2, 1, 3, 2, 1<br/>Average: 1.8"]\n    end\n    NP --> N["Low anomaly score"]\n    AP --> A["HIGH anomaly score"]\n    style AP fill:#FFB6C1\n    style A fill:#FFB6C1\n    style NP fill:#90EE90\n    style N fill:#90EE90',
                    },
                    {
                        "step_number": 6,
                        "title": "Building the Forest",
                        "explanation": "Isolation Forest builds **multiple trees** (default: 100), each trained on a random subsample of data (default: 256 points). This ensemble approach reduces variance and improves robustness.",
                        "diagram_data": 'graph TB\n    Data["Full Dataset<br/>10,000 points"]\n    Data --> |"Sample 256"| T1["iTree 1"]\n    Data --> |"Sample 256"| T2["iTree 2"]\n    Data --> |"Sample 256"| T3["iTree 3"]\n    Data --> |"..."| Tn["iTree 100"]\n    T1 --> Ensemble["Isolation Forest"]\n    T2 --> Ensemble\n    T3 --> Ensemble\n    Tn --> Ensemble\n    style Ensemble fill:#ADD8E6',
                    },
                    {
                        "step_number": 7,
                        "title": "Computing the Anomaly Score",
                        "explanation": "The anomaly score is computed from the **average path length** across all trees, normalized by the expected path length for the sample size. Scores range from 0 to 1, where **scores close to 1 indicate anomalies**.",
                        "diagram_data": 'flowchart TB\n    subgraph "For each point"\n    PL["Get path length<br/>from each tree"]\n    AVG["Calculate average<br/>path length E(h)"]\n    NORM["Normalize by<br/>expected length c(n)"]\n    SCORE["Score = 2^(-E(h)/c(n))"]\n    end\n    PL --> AVG --> NORM --> SCORE\n    subgraph "Score Interpretation"\n    S1["Score → 1: Anomaly"]\n    S2["Score → 0.5: Normal"]\n    S3["Score → 0: Very normal"]\n    end\n    style S1 fill:#FFB6C1\n    style S2 fill:#FFFACD\n    style S3 fill:#90EE90',
                    },
                    {
                        "step_number": 8,
                        "title": "Setting the Contamination Parameter",
                        "explanation": "The **contamination** parameter (default: 'auto') sets the expected proportion of anomalies. It determines the threshold for classifying points as anomalies. Set it based on domain knowledge or cross-validation.",
                        "diagram_data": 'graph TB\n    subgraph "contamination=0.1 (10% anomalies)"\n    S1["Scores > threshold → Anomaly"]\n    S2["Top 10% of scores<br/>flagged as anomalies"]\n    end\n    subgraph "Effect on Threshold"\n    C1["contamination=0.01"] --> T1["High threshold<br/>Few anomalies"]\n    C2["contamination=0.1"] --> T2["Medium threshold<br/>More anomalies"]\n    C3["contamination=0.5"] --> T3["Low threshold<br/>Many anomalies"]\n    end\n    style T1 fill:#90EE90\n    style T2 fill:#FFFACD\n    style T3 fill:#FFB6C1',
                    },
                    {
                        "step_number": 9,
                        "title": "scikit-learn Implementation",
                        "explanation": "Using Isolation Forest in scikit-learn is straightforward. Key parameters: **n_estimators** (trees), **max_samples** (subsample size), **contamination** (anomaly proportion), **random_state** (reproducibility).",
                        "diagram_data": 'flowchart LR\n    subgraph "Code Flow"\n    C1["from sklearn.ensemble<br/>import IsolationForest"]\n    C2["clf = IsolationForest(<br/>n_estimators=100,<br/>contamination=0.1)"]\n    C3["clf.fit(X_train)"]\n    C4["predictions = clf.predict(X)<br/>-1 = anomaly, 1 = normal"]\n    C5["scores = clf.score_samples(X)<br/>lower = more anomalous"]\n    end\n    C1 --> C2 --> C3 --> C4\n    C3 --> C5\n    style C4 fill:#90EE90\n    style C5 fill:#ADD8E6',
                    },
                    {
                        "step_number": 10,
                        "title": "Strengths and Limitations",
                        "explanation": "**Strengths**: Fast training O(n), handles high dimensions well, no distance calculations needed, works without labels. **Limitations**: Struggles with local anomalies in dense regions, assumes anomalies are globally isolated.",
                        "diagram_data": 'graph TB\n    subgraph "Strengths"\n    S1["Fast & Scalable"]\n    S2["High-dimensional data"]\n    S3["No labels needed"]\n    S4["Memory efficient"]\n    end\n    subgraph "Limitations"\n    L1["Global isolation assumption"]\n    L2["Axis-parallel splits only"]\n    L3["Sensitive to contamination"]\n    end\n    subgraph "Best Use Cases"\n    U1["Fraud detection"]\n    U2["Network intrusion"]\n    U3["Sensor anomalies"]\n    U4["Data cleaning"]\n    end\n    style S1 fill:#90EE90\n    style S2 fill:#90EE90\n    style S3 fill:#90EE90\n    style S4 fill:#90EE90\n    style L1 fill:#FFB6C1\n    style L2 fill:#FFB6C1\n    style L3 fill:#FFB6C1\n    style U1 fill:#ADD8E6\n    style U2 fill:#ADD8E6\n    style U3 fill:#ADD8E6\n    style U4 fill:#ADD8E6',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_transformers_visuals(self):
        """Seed Transformers visual topics."""
        subject = self.get_or_create_subject(
            "Transformers", "transformers", "Deep Learning"
        )

        # Self-Attention Mechanism
        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="self-attention",
            defaults={
                "title": "Self-Attention Mechanism",
                "description": "Step-by-step visualization of how self-attention works in transformers",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "advanced",
                "estimated_time_minutes": 12,
                "tags": ["attention", "transformers", "nlp", "deep-learning"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "Input Embeddings",
                        "explanation": "Each token in the input sequence is converted to an **embedding vector**. These embeddings capture semantic meaning and are the starting point for attention computation.",
                        "diagram_data": 'graph LR\n    subgraph Input Tokens\n    T1[The]\n    T2[cat]\n    T3[sat]\n    end\n    subgraph Embeddings dim=4\n    E1["[0.1, 0.2, 0.3, 0.4]"]\n    E2["[0.5, 0.6, 0.7, 0.8]"]\n    E3["[0.2, 0.3, 0.4, 0.5]"]\n    end\n    T1 --> E1\n    T2 --> E2\n    T3 --> E3',
                    },
                    {
                        "step_number": 1,
                        "title": "Query, Key, Value Projections",
                        "explanation": "Each embedding is projected into three vectors: **Query (Q)**, **Key (K)**, and **Value (V)** using learned weight matrices. Q asks 'what am I looking for?', K says 'what do I contain?', V says 'what information do I provide?'",
                        "diagram_data": 'graph TB\n    E["Embedding"]\n    E --> |"W_Q"| Q["Query (Q)"]\n    E --> |"W_K"| K["Key (K)"]\n    E --> |"W_V"| V["Value (V)"]\n    style Q fill:#FFB6C1\n    style K fill:#ADD8E6\n    style V fill:#90EE90',
                    },
                    {
                        "step_number": 2,
                        "title": "Computing Attention Scores",
                        "explanation": "For each token, we compute how much it should 'attend' to every other token by taking the **dot product** of its Query with all Keys. Higher scores mean stronger attention.",
                        "diagram_data": 'graph TB\n    subgraph "Query from \'cat\'"\n    Q2["Q_cat"]\n    end\n    subgraph Keys\n    K1["K_The"]\n    K2["K_cat"]\n    K3["K_sat"]\n    end\n    Q2 --> |"Q·K = 0.3"| K1\n    Q2 --> |"Q·K = 0.8"| K2\n    Q2 --> |"Q·K = 0.5"| K3',
                    },
                    {
                        "step_number": 3,
                        "title": "Softmax Normalization",
                        "explanation": "The raw scores are scaled by √d_k (dimension of keys) and passed through **softmax** to get attention weights that sum to 1. This creates a probability distribution over tokens.",
                        "diagram_data": 'graph LR\n    subgraph Raw Scores\n    S1["0.3"]\n    S2["0.8"]\n    S3["0.5"]\n    end\n    subgraph Softmax Weights\n    W1["0.20"]\n    W2["0.45"]\n    W3["0.35"]\n    end\n    S1 --> |softmax| W1\n    S2 --> |softmax| W2\n    S3 --> |softmax| W3\n    Note["Sum = 1.0"]',
                    },
                    {
                        "step_number": 4,
                        "title": "Weighted Sum of Values",
                        "explanation": "The final output for each position is a **weighted sum** of all Value vectors, using the attention weights. Tokens with higher attention weights contribute more to the output.",
                        "diagram_data": 'graph TB\n    subgraph Values\n    V1["V_The"]\n    V2["V_cat"]\n    V3["V_sat"]\n    end\n    subgraph Weights\n    W1["0.20"]\n    W2["0.45"]\n    W3["0.35"]\n    end\n    Output["Output = 0.20·V_The + 0.45·V_cat + 0.35·V_sat"]\n    V1 --> |"× 0.20"| Output\n    V2 --> |"× 0.45"| Output\n    V3 --> |"× 0.35"| Output\n    style Output fill:#FFFACD',
                    },
                    {
                        "step_number": 5,
                        "title": "Multi-Head Attention",
                        "explanation": "In practice, we run **multiple attention heads** in parallel, each with its own Q, K, V projections. This allows the model to attend to different types of information simultaneously.",
                        "diagram_data": 'graph TB\n    Input["Input Embeddings"]\n    Input --> H1["Head 1<br/>Syntax?"]\n    Input --> H2["Head 2<br/>Semantics?"]\n    Input --> H3["Head 3<br/>Position?"]\n    H1 --> Concat["Concatenate"]\n    H2 --> Concat\n    H3 --> Concat\n    Concat --> Output["Final Output"]\n    style H1 fill:#FFB6C1\n    style H2 fill:#ADD8E6\n    style H3 fill:#90EE90',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_lightgbm_visuals(self):
        """Seed LightGBM visual topics."""
        subject = self.get_or_create_subject("LightGBM", "lightgbm", "ML Frameworks")

        # Leaf-wise Tree Growth
        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="lightgbm-leaf-wise-growth",
            defaults={
                "title": "LightGBM Leaf-wise Tree Growth",
                "description": "See how LightGBM builds trees using leaf-wise (best-first) growth strategy",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "advanced",
                "estimated_time_minutes": 10,
                "tags": ["lightgbm", "gradient-boosting", "tree-algorithms"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "Initial Prediction",
                        "explanation": "LightGBM starts with an **initial prediction** for all samples, typically the mean of target values. This becomes the baseline that subsequent trees will improve upon.",
                        "diagram_data": 'graph TB\n    Root["Initial Prediction<br/>F_0 = mean(y) = 0.5<br/>100 samples"]\n    style Root fill:#E6E6FA',
                    },
                    {
                        "step_number": 1,
                        "title": "Calculate Residuals",
                        "explanation": "For each sample, calculate the **residual** (error): actual value minus current prediction. These residuals become the target for the next tree to learn.",
                        "diagram_data": 'graph TB\n    subgraph Current State\n    P["Predictions: 0.5 for all"]\n    end\n    subgraph Residuals\n    R1["Sample 1: 0.8 - 0.5 = 0.3"]\n    R2["Sample 2: 0.2 - 0.5 = -0.3"]\n    R3["Sample 3: 0.9 - 0.5 = 0.4"]\n    Rn["..."]\n    end\n    P --> R1\n    P --> R2\n    P --> R3',
                    },
                    {
                        "step_number": 2,
                        "title": "Find Best Split (Root)",
                        "explanation": "Unlike level-wise growth (XGBoost), LightGBM uses **leaf-wise** growth. It finds the leaf with the **highest potential gain** and splits that leaf, regardless of tree depth.",
                        "diagram_data": 'graph TB\n    Root["Root: All Samples<br/>Find best split across all features<br/>Best: feature_3 < 0.7<br/>Gain: 125.4"]\n    Root --> |"< 0.7"| L1["Left Leaf<br/>40 samples<br/>Potential Gain: 45.2"]\n    Root --> |">= 0.7"| R1["Right Leaf<br/>60 samples<br/>Potential Gain: 78.1"]\n    style Root fill:#90EE90\n    style R1 fill:#FFFACD',
                    },
                    {
                        "step_number": 3,
                        "title": "Split Leaf with Highest Gain",
                        "explanation": "LightGBM picks the leaf with highest potential gain (Right Leaf: 78.1) and splits it. This **greedy approach** often leads to deeper, more accurate trees than level-wise growth.",
                        "diagram_data": 'graph TB\n    Root["feature_3 < 0.7"]\n    Root --> L1["Left Leaf<br/>40 samples"]\n    Root --> R1["feature_1 < 2.3"]\n    R1 --> |"Split!"| RL["30 samples<br/>Gain: 52.3"]\n    R1 --> RR["30 samples<br/>Gain: 38.7"]\n    style R1 fill:#90EE90\n    style RL fill:#FFFACD',
                    },
                    {
                        "step_number": 4,
                        "title": "Continue Leaf-wise Growth",
                        "explanation": "This process continues: evaluate all current leaves, pick the one with highest gain, and split it. The tree grows asymmetrically, focusing on areas with most error.",
                        "diagram_data": 'graph TB\n    Root["feature_3 < 0.7"]\n    Root --> L1["Leaf: 40 samples"]\n    Root --> R1["feature_1 < 2.3"]\n    R1 --> RL["feature_5 < 1.1"]\n    R1 --> RR["Leaf: 30 samples"]\n    RL --> RLL["Leaf: 15 samples"]\n    RL --> RLR["Leaf: 15 samples"]\n    style RL fill:#90EE90',
                    },
                    {
                        "step_number": 5,
                        "title": "Stopping and Predictions",
                        "explanation": "Tree growth stops when: max leaves reached, max depth hit, or min gain threshold. Each leaf predicts a value to **reduce residuals**. The learning rate scales these predictions.",
                        "diagram_data": 'graph TB\n    Root["Tree Complete"]\n    Root --> L1["Predict: +0.15"]\n    Root --> R1["Split Node"]\n    R1 --> RL["Split Node"]\n    R1 --> RR["Predict: -0.22"]\n    RL --> RLL["Predict: +0.31"]\n    RL --> RLR["Predict: +0.08"]\n    Update["F_1 = F_0 + lr × tree_predictions"]\n    style Update fill:#E6E6FA',
                    },
                    {
                        "step_number": 6,
                        "title": "Ensemble of Trees",
                        "explanation": "LightGBM builds many trees sequentially. Each new tree fits the residuals from all previous trees. The final prediction is the sum of initial value plus all tree contributions.",
                        "diagram_data": 'graph LR\n    F0["F_0<br/>Initial"]\n    T1["Tree 1"]\n    T2["Tree 2"]\n    Tn["Tree N"]\n    Final["Final Prediction<br/>F_0 + lr×T1 + lr×T2 + ... + lr×TN"]\n    F0 --> |+| T1\n    T1 --> |+| T2\n    T2 --> |+| Tn\n    Tn --> Final\n    style Final fill:#90EE90',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_lightgbm_tree_growth_visual(self):
        """Seed LightGBM step-by-step tree growth visualization."""
        subject = self.get_or_create_subject("LightGBM", "lightgbm", "ML Frameworks")

        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="lightgbm-tree-growth-steps",
            defaults={
                "title": "LightGBM Tree Growth: Step by Step",
                "description": "Watch a LightGBM tree grow leaf-by-leaf over multiple iterations",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "intermediate",
                "estimated_time_minutes": 10,
                "tags": ["lightgbm", "tree-growth", "leaf-wise", "gradient-boosting"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "Setup: The Dataset",
                        "explanation": "We have a regression dataset with 1000 samples and 10 features. LightGBM will build a tree to predict the residuals (errors) from the current model. Let's watch one tree grow leaf-by-leaf.",
                        "diagram_data": 'flowchart TB\n    subgraph "Dataset"\n    D1["1000 samples"]\n    D2["10 features (X1-X10)"]\n    D3["Target: residuals"]\n    end\n    subgraph "LightGBM Settings"\n    S1["num_leaves = 8"]\n    S2["max_depth = -1 (unlimited)"]\n    S3["min_data_in_leaf = 20"]\n    end\n    style D1 fill:#ADD8E6\n    style S1 fill:#90EE90',
                    },
                    {
                        "step_number": 1,
                        "title": "Step 1: Root Node",
                        "explanation": "The tree starts with a single **root node** containing all 1000 samples. LightGBM calculates the best split across all features using histogram-based splitting. The node predicts the mean residual.",
                        "diagram_data": 'graph TB\n    Root["ROOT<br/>1000 samples<br/>Prediction: 0.0<br/>Gain potential: 156.3"]\n    style Root fill:#E6E6FA',
                    },
                    {
                        "step_number": 2,
                        "title": "Step 2: First Split",
                        "explanation": "LightGBM finds the best split: **X3 < 0.45**. This creates two leaf nodes. Each leaf calculates its optimal prediction value to minimize the loss function (e.g., MSE for regression).",
                        "diagram_data": 'graph TB\n    Root["X3 < 0.45?"]\n    Root -->|Yes| L1["Leaf 1<br/>420 samples<br/>Pred: -0.23<br/>Gain: 45.2"]\n    Root -->|No| L2["Leaf 2<br/>580 samples<br/>Pred: +0.17<br/>Gain: 62.8"]\n    style Root fill:#E6E6FA\n    style L1 fill:#90EE90\n    style L2 fill:#90EE90\n    Note["2 leaves total"]',
                    },
                    {
                        "step_number": 3,
                        "title": "Step 3: Choose Best Leaf to Split",
                        "explanation": "**Key difference from XGBoost**: LightGBM uses **leaf-wise** growth. It evaluates ALL current leaves and splits the one with the **highest gain**. Leaf 2 (gain=62.8) > Leaf 1 (gain=45.2), so Leaf 2 gets split.",
                        "diagram_data": 'graph TB\n    Root["X3 < 0.45?"]\n    Root -->|Yes| L1["Leaf 1<br/>Gain: 45.2"]\n    Root -->|No| L2["Leaf 2<br/>Gain: 62.8<br/>SPLIT THIS!"]\n    style L1 fill:#FFFACD\n    style L2 fill:#FFB6C1',
                    },
                    {
                        "step_number": 4,
                        "title": "Step 4: Second Split",
                        "explanation": "Leaf 2 is split on **X7 < 0.82**. Now we have 3 leaves. Notice the tree is growing **asymmetrically** - we're going deeper on the right side because that's where the gain is highest.",
                        "diagram_data": 'graph TB\n    Root["X3 < 0.45?"]\n    Root -->|Yes| L1["Leaf 1<br/>420 samples<br/>Gain: 45.2"]\n    Root -->|No| N2["X7 < 0.82?"]\n    N2 -->|Yes| L3["Leaf 3<br/>310 samples<br/>Pred: +0.08<br/>Gain: 38.5"]\n    N2 -->|No| L4["Leaf 4<br/>270 samples<br/>Pred: +0.28<br/>Gain: 51.3"]\n    style N2 fill:#E6E6FA\n    style L3 fill:#90EE90\n    style L4 fill:#90EE90\n    Note["3 leaves total"]',
                    },
                    {
                        "step_number": 5,
                        "title": "Step 5: Third Split",
                        "explanation": "Compare gains: Leaf 4 (51.3) > Leaf 1 (45.2) > Leaf 3 (38.5). Leaf 4 wins! It gets split on **X1 < 0.33**. The tree continues to grow where errors are largest.",
                        "diagram_data": 'graph TB\n    Root["X3 < 0.45?"]\n    Root -->|Yes| L1["Leaf 1<br/>420 samples<br/>Gain: 45.2"]\n    Root -->|No| N2["X7 < 0.82?"]\n    N2 -->|Yes| L3["Leaf 3<br/>310 samples<br/>Gain: 38.5"]\n    N2 -->|No| N4["X1 < 0.33?"]\n    N4 -->|Yes| L5["Leaf 5<br/>145 samples<br/>Pred: +0.41<br/>Gain: 28.7"]\n    N4 -->|No| L6["Leaf 6<br/>125 samples<br/>Pred: +0.19<br/>Gain: 33.1"]\n    style N4 fill:#E6E6FA\n    style L5 fill:#90EE90\n    style L6 fill:#90EE90\n    Note["4 leaves total"]',
                    },
                    {
                        "step_number": 6,
                        "title": "Step 6: Fourth Split",
                        "explanation": "Gains: Leaf 1 (45.2) > Leaf 3 (38.5) > Leaf 6 (33.1) > Leaf 5 (28.7). Finally Leaf 1 (the original left branch) gets split on **X5 < 0.67**. The tree is becoming more balanced.",
                        "diagram_data": 'graph TB\n    Root["X3 < 0.45?"]\n    Root -->|Yes| N1["X5 < 0.67?"]\n    N1 -->|Yes| L7["Leaf 7<br/>185 samples<br/>Pred: -0.35"]\n    N1 -->|No| L8["Leaf 8<br/>235 samples<br/>Pred: -0.14"]\n    Root -->|No| N2["X7 < 0.82?"]\n    N2 -->|Yes| L3["Leaf 3<br/>310 samples"]\n    N2 -->|No| N4["X1 < 0.33?"]\n    N4 -->|Yes| L5["Leaf 5<br/>145 samples"]\n    N4 -->|No| L6["Leaf 6<br/>125 samples"]\n    style N1 fill:#E6E6FA\n    style L7 fill:#90EE90\n    style L8 fill:#90EE90\n    Note["5 leaves total"]',
                    },
                    {
                        "step_number": 7,
                        "title": "Step 7: Fifth Split",
                        "explanation": "Leaf 3 has the highest remaining gain. Split on **X9 < 0.51**. We now have 6 leaves. Each split reduces the overall prediction error on training data.",
                        "diagram_data": 'graph TB\n    Root["X3 < 0.45?"]\n    Root -->|Yes| N1["X5 < 0.67?"]\n    N1 -->|Yes| L7["Leaf 7"]\n    N1 -->|No| L8["Leaf 8"]\n    Root -->|No| N2["X7 < 0.82?"]\n    N2 -->|Yes| N3["X9 < 0.51?"]\n    N3 -->|Yes| L9["Leaf 9<br/>165 samples"]\n    N3 -->|No| L10["Leaf 10<br/>145 samples"]\n    N2 -->|No| N4["X1 < 0.33?"]\n    N4 -->|Yes| L5["Leaf 5"]\n    N4 -->|No| L6["Leaf 6"]\n    style N3 fill:#E6E6FA\n    style L9 fill:#90EE90\n    style L10 fill:#90EE90\n    Note["6 leaves total"]',
                    },
                    {
                        "step_number": 8,
                        "title": "Step 8: Sixth Split",
                        "explanation": "Continue splitting the leaf with highest gain. Leaf 8 is split on **X2 < 0.28**. We now have 7 leaves - one more to go to reach our num_leaves=8 limit.",
                        "diagram_data": 'graph TB\n    Root["X3 < 0.45?"]\n    Root -->|Yes| N1["X5 < 0.67?"]\n    N1 -->|Yes| L7["Leaf 7"]\n    N1 -->|No| N8["X2 < 0.28?"]\n    N8 -->|Yes| L11["Leaf 11<br/>98 samples"]\n    N8 -->|No| L12["Leaf 12<br/>137 samples"]\n    Root -->|No| N2["X7 < 0.82?"]\n    N2 -->|Yes| N3["X9 < 0.51?"]\n    N3 -->|Yes| L9["Leaf 9"]\n    N3 -->|No| L10["Leaf 10"]\n    N2 -->|No| N4["X1 < 0.33?"]\n    N4 -->|Yes| L5["Leaf 5"]\n    N4 -->|No| L6["Leaf 6"]\n    style N8 fill:#E6E6FA\n    style L11 fill:#90EE90\n    style L12 fill:#90EE90\n    Note["7 leaves total"]',
                    },
                    {
                        "step_number": 9,
                        "title": "Step 9: Final Split (num_leaves = 8)",
                        "explanation": "Last split! Leaf 5 is split on **X4 < 0.71**. We've reached **num_leaves=8**, so tree growth stops. Each leaf now contains a prediction value that will be scaled by the learning rate.",
                        "diagram_data": 'graph TB\n    Root["X3 < 0.45?"]\n    Root -->|Yes| N1["X5 < 0.67?"]\n    N1 -->|Yes| L7["Leaf 7<br/>pred: -0.35"]\n    N1 -->|No| N8["X2 < 0.28?"]\n    N8 -->|Yes| L11["Leaf 11<br/>pred: -0.21"]\n    N8 -->|No| L12["Leaf 12<br/>pred: -0.08"]\n    Root -->|No| N2["X7 < 0.82?"]\n    N2 -->|Yes| N3["X9 < 0.51?"]\n    N3 -->|Yes| L9["Leaf 9<br/>pred: +0.05"]\n    N3 -->|No| L10["Leaf 10<br/>pred: +0.12"]\n    N2 -->|No| N4["X1 < 0.33?"]\n    N4 -->|Yes| N5["X4 < 0.71?"]\n    N5 -->|Yes| L13["Leaf 13<br/>pred: +0.52"]\n    N5 -->|No| L14["Leaf 14<br/>pred: +0.31"]\n    N4 -->|No| L6["Leaf 6<br/>pred: +0.19"]\n    style L7 fill:#ADD8E6\n    style L11 fill:#ADD8E6\n    style L12 fill:#ADD8E6\n    style L9 fill:#90EE90\n    style L10 fill:#90EE90\n    style L13 fill:#90EE90\n    style L14 fill:#90EE90\n    style L6 fill:#90EE90\n    Note["8 leaves - COMPLETE!"]',
                    },
                    {
                        "step_number": 10,
                        "title": "Tree Complete: Make Predictions",
                        "explanation": "To predict for a new sample, traverse from root to leaf following the split conditions. The leaf's prediction is multiplied by the **learning_rate** (e.g., 0.1) and added to the current model's prediction.",
                        "diagram_data": 'flowchart TB\n    subgraph "New Sample: X3=0.6, X7=0.9, X1=0.4, X4=0.5"\n    Q1["X3 < 0.45?<br/>0.6 < 0.45? NO"] -->|No| Q2["X7 < 0.82?<br/>0.9 < 0.82? NO"]\n    Q2 -->|No| Q3["X1 < 0.33?<br/>0.4 < 0.33? NO"]\n    Q3 -->|No| LEAF["Leaf 6<br/>pred: +0.19"]\n    end\n    LEAF --> FINAL["Final contribution:<br/>0.1 × 0.19 = +0.019"]\n    style LEAF fill:#90EE90\n    style FINAL fill:#FFFACD',
                    },
                    {
                        "step_number": 11,
                        "title": "Leaf-wise vs Level-wise Growth",
                        "explanation": "**Level-wise** (XGBoost default) grows all nodes at same depth before going deeper - creates balanced trees. **Leaf-wise** (LightGBM) always splits the best leaf - creates asymmetric but often more accurate trees.",
                        "diagram_data": 'flowchart LR\n    subgraph "Level-wise (XGBoost)"\n    direction TB\n    XR["Root"]\n    XR --> XL1["L1"]\n    XR --> XL2["L2"]\n    XL1 --> XL3["L3"]\n    XL1 --> XL4["L4"]\n    XL2 --> XL5["L5"]\n    XL2 --> XL6["L6"]\n    end\n    subgraph "Leaf-wise (LightGBM)"\n    direction TB\n    LR["Root"]\n    LR --> LL1["L1"]\n    LR --> LN2["Node"]\n    LN2 --> LN3["Node"]\n    LN2 --> LL4["L4"]\n    LN3 --> LL5["L5"]\n    LN3 --> LL6["L6"]\n    end\n    style XL3 fill:#ADD8E6\n    style XL4 fill:#ADD8E6\n    style XL5 fill:#ADD8E6\n    style XL6 fill:#ADD8E6\n    style LL1 fill:#90EE90\n    style LL4 fill:#90EE90\n    style LL5 fill:#90EE90\n    style LL6 fill:#90EE90',
                    },
                    {
                        "step_number": 12,
                        "title": "Key Parameters for Tree Growth",
                        "explanation": "Control tree growth with these key parameters: **num_leaves** (max leaves per tree), **max_depth** (limit depth to prevent overfitting), **min_data_in_leaf** (minimum samples per leaf), **min_gain_to_split** (minimum gain required).",
                        "diagram_data": 'flowchart TB\n    subgraph "Stopping Conditions"\n    S1["num_leaves reached<br/>(e.g., 31)"]\n    S2["max_depth reached<br/>(e.g., 6)"]\n    S3["min_data_in_leaf<br/>(e.g., 20 samples)"]\n    S4["min_gain_to_split<br/>(e.g., 0.1)"]\n    end\n    subgraph "Overfitting Risk"\n    O1["More leaves = More complex"]\n    O2["Deeper = More specific"]\n    O3["Fewer min samples = Overfit"]\n    end\n    S1 --> O1\n    S2 --> O2\n    S3 --> O3\n    style S1 fill:#90EE90\n    style S2 fill:#ADD8E6\n    style S3 fill:#FFFACD\n    style O1 fill:#FFB6C1\n    style O2 fill:#FFB6C1\n    style O3 fill:#FFB6C1',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_lightgbm_parallel_training_visual(self):
        """Seed LightGBM parallel training visualization."""
        subject = self.get_or_create_subject("LightGBM", "lightgbm", "ML Frameworks")

        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="lightgbm-parallel-training",
            defaults={
                "title": "LightGBM Parallel Training Under the Hood",
                "description": "Understand how LightGBM achieves fast parallel training with histograms and distributed algorithms",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "advanced",
                "estimated_time_minutes": 12,
                "tags": [
                    "lightgbm",
                    "parallel",
                    "distributed",
                    "histograms",
                    "performance",
                ],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "The Challenge: Finding Best Splits",
                        "explanation": "The bottleneck in tree training is finding the **best split point** for each feature. Naive approach: sort all values and try each as threshold. With millions of samples and hundreds of features, this is extremely slow.",
                        "diagram_data": 'flowchart TB\n    subgraph "Naive Split Finding"\n    D["1M samples × 100 features"]\n    S["Sort each feature: O(n log n)"]\n    T["Try each value as split"]\n    C["Calculate gain for each"]\n    end\n    D --> S --> T --> C\n    C --> SLOW["SLOW!<br/>~100M operations per node"]\n    style SLOW fill:#FFB6C1',
                    },
                    {
                        "step_number": 1,
                        "title": "LightGBM's Secret: Histogram-Based Splitting",
                        "explanation": "Instead of using exact values, LightGBM **buckets** continuous features into discrete bins (default: 255). This reduces split candidates from millions to just 255 per feature, enabling massive speedup.",
                        "diagram_data": 'flowchart TB\n    subgraph "Histogram Approach"\n    V["Feature values: 0.123, 0.456, 0.789, ..."]\n    B["Bucket into 255 bins"]\n    H["Histogram: count per bin"]\n    end\n    V --> B --> H\n    subgraph "Benefits"\n    B1["Only 255 split candidates"]\n    B2["O(n) to build histogram"]\n    B3["O(bins) to find best split"]\n    end\n    H --> B1\n    H --> B2\n    H --> B3\n    style B1 fill:#90EE90\n    style B2 fill:#90EE90\n    style B3 fill:#90EE90',
                    },
                    {
                        "step_number": 2,
                        "title": "Building Feature Histograms",
                        "explanation": "For each node, LightGBM builds a **histogram** for every feature. Each bin stores: (1) sum of gradients, (2) sum of hessians, (3) count of samples. These stats enable instant gain calculation.",
                        "diagram_data": 'flowchart LR\n    subgraph "Feature X1 Histogram (8 bins shown)"\n    B1["Bin 0<br/>grad: 2.1<br/>hess: 15<br/>n: 120"]\n    B2["Bin 1<br/>grad: -0.8<br/>hess: 22<br/>n: 180"]\n    B3["Bin 2<br/>grad: 1.5<br/>hess: 18<br/>n: 145"]\n    B4["..."]\n    B5["Bin 254<br/>grad: -1.2<br/>hess: 8<br/>n: 55"]\n    end\n    B1 --> B2 --> B3 --> B4 --> B5\n    style B1 fill:#ADD8E6\n    style B2 fill:#ADD8E6\n    style B3 fill:#ADD8E6\n    style B5 fill:#ADD8E6',
                    },
                    {
                        "step_number": 3,
                        "title": "Histogram Subtraction Trick",
                        "explanation": "**Key optimization**: When splitting a node, the child's histogram = parent's histogram - sibling's histogram. Only compute histogram for the **smaller** child, get the other for free! Cuts work in half.",
                        "diagram_data": 'flowchart TB\n    Parent["Parent Histogram<br/>(already computed)"]\n    Parent --> Left["Left Child<br/>300 samples<br/>COMPUTE"]\n    Parent --> Right["Right Child<br/>700 samples<br/>FREE!"]\n    Calc["Right = Parent - Left"]\n    Left --> Calc\n    Parent --> Calc\n    Calc --> Right\n    style Left fill:#FFFACD\n    style Right fill:#90EE90\n    style Calc fill:#E6E6FA',
                    },
                    {
                        "step_number": 4,
                        "title": "Parallel Training Overview",
                        "explanation": "LightGBM supports multiple parallelism strategies: **Feature Parallel** (split features across workers), **Data Parallel** (split data across workers), and **Voting Parallel** (LightGBM's innovation for large data).",
                        "diagram_data": 'flowchart TB\n    subgraph "Parallelism Strategies"\n    FP["Feature Parallel<br/>Each worker: subset of features<br/>Best for: few features, many samples"]\n    DP["Data Parallel<br/>Each worker: subset of data<br/>Best for: many features"]\n    VP["Voting Parallel<br/>Hybrid approach<br/>Best for: huge datasets"]\n    end\n    style FP fill:#ADD8E6\n    style DP fill:#90EE90\n    style VP fill:#FFFACD',
                    },
                    {
                        "step_number": 5,
                        "title": "Feature Parallel: How It Works",
                        "explanation": "Each worker holds **all data** but only a **subset of features**. Workers build histograms for their features in parallel, then communicate to find the global best split.",
                        "diagram_data": 'flowchart TB\n    subgraph "Worker 1"\n    W1D["All 1M samples"]\n    W1F["Features 1-25"]\n    W1H["Build histograms<br/>Find local best split"]\n    end\n    subgraph "Worker 2"\n    W2D["All 1M samples"]\n    W2F["Features 26-50"]\n    W2H["Build histograms<br/>Find local best split"]\n    end\n    subgraph "Worker 3"\n    W3D["All 1M samples"]\n    W3F["Features 51-75"]\n    W3H["Build histograms<br/>Find local best split"]\n    end\n    W1H --> SYNC["Sync: Find global best"]\n    W2H --> SYNC\n    W3H --> SYNC\n    SYNC --> SPLIT["Apply same split on all workers"]\n    style SYNC fill:#FFB6C1\n    style SPLIT fill:#90EE90',
                    },
                    {
                        "step_number": 6,
                        "title": "Feature Parallel: Communication",
                        "explanation": "After each worker finds its local best split, they exchange split info (feature, threshold, gain). Then **all workers apply the same split** to keep data synchronized. Communication cost: O(workers).",
                        "diagram_data": 'flowchart LR\n    subgraph "Step 1: Local Best"\n    W1["W1: Feature 12<br/>gain=45.2"]\n    W2["W2: Feature 38<br/>gain=52.1"]\n    W3["W3: Feature 67<br/>gain=41.8"]\n    end\n    subgraph "Step 2: Reduce"\n    ALL["All-reduce:<br/>Best = Feature 38<br/>gain=52.1"]\n    end\n    subgraph "Step 3: Apply"\n    APPLY["All workers split<br/>on Feature 38"]\n    end\n    W1 --> ALL\n    W2 --> ALL\n    W3 --> ALL\n    ALL --> APPLY\n    style W2 fill:#90EE90\n    style ALL fill:#E6E6FA',
                    },
                    {
                        "step_number": 7,
                        "title": "Data Parallel: How It Works",
                        "explanation": "Each worker holds **all features** but only a **subset of data**. Workers build local histograms, then **merge histograms** across workers to get global statistics for split finding.",
                        "diagram_data": 'flowchart TB\n    subgraph "Worker 1"\n    W1D["Samples 1-333K"]\n    W1F["All 100 features"]\n    W1H["Local histograms"]\n    end\n    subgraph "Worker 2"\n    W2D["Samples 333K-666K"]\n    W2F["All 100 features"]\n    W2H["Local histograms"]\n    end\n    subgraph "Worker 3"\n    W3D["Samples 666K-1M"]\n    W3F["All 100 features"]\n    W3H["Local histograms"]\n    end\n    W1H --> MERGE["Merge histograms<br/>(sum gradients, hessians)"]\n    W2H --> MERGE\n    W3H --> MERGE\n    MERGE --> GLOBAL["Global histogram<br/>Find best split"]\n    style MERGE fill:#FFB6C1\n    style GLOBAL fill:#90EE90',
                    },
                    {
                        "step_number": 8,
                        "title": "Data Parallel: Reduce-Scatter",
                        "explanation": "LightGBM uses **Reduce-Scatter** for efficient histogram merging. Each worker ends up with the merged histogram for a **portion of features**, reducing memory and enabling parallel split finding.",
                        "diagram_data": 'flowchart TB\n    subgraph "Before Reduce-Scatter"\n    W1B["W1: hist(F1-F100) local"]\n    W2B["W2: hist(F1-F100) local"]\n    W3B["W3: hist(F1-F100) local"]\n    end\n    subgraph "Reduce-Scatter"\n    RS["Each worker sends parts<br/>and receives merged parts"]\n    end\n    subgraph "After Reduce-Scatter"\n    W1A["W1: hist(F1-F33) GLOBAL"]\n    W2A["W2: hist(F34-F66) GLOBAL"]\n    W3A["W3: hist(F67-F100) GLOBAL"]\n    end\n    W1B --> RS\n    W2B --> RS\n    W3B --> RS\n    RS --> W1A\n    RS --> W2A\n    RS --> W3A\n    style RS fill:#E6E6FA\n    style W1A fill:#90EE90\n    style W2A fill:#90EE90\n    style W3A fill:#90EE90',
                    },
                    {
                        "step_number": 9,
                        "title": "Voting Parallel: LightGBM's Innovation",
                        "explanation": "For **huge datasets**, communicating full histograms is expensive. Voting Parallel: each worker votes for its **top-k split candidates**. Only candidates with enough votes get full histogram merge. Reduces communication dramatically.",
                        "diagram_data": 'flowchart TB\n    subgraph "Step 1: Local Top-K"\n    W1["W1 votes:<br/>F12, F38, F45"]\n    W2["W2 votes:<br/>F38, F67, F12"]\n    W3["W3 votes:<br/>F38, F12, F89"]\n    end\n    subgraph "Step 2: Aggregate Votes"\n    V["F38: 3 votes<br/>F12: 3 votes<br/>F45: 1 vote<br/>F67: 1 vote<br/>F89: 1 vote"]\n    end\n    subgraph "Step 3: Merge Winners Only"\n    M["Only merge histograms<br/>for F38 and F12"]\n    end\n    W1 --> V\n    W2 --> V\n    W3 --> V\n    V --> M\n    style V fill:#FFFACD\n    style M fill:#90EE90',
                    },
                    {
                        "step_number": 10,
                        "title": "Communication Comparison",
                        "explanation": "Different strategies have different communication costs. **Voting Parallel** is most efficient for large-scale distributed training where network bandwidth is the bottleneck.",
                        "diagram_data": 'flowchart TB\n    subgraph "Communication Cost per Split"\n    FP["Feature Parallel<br/>O(features × bins)<br/>Send histograms for best splits"]\n    DP["Data Parallel<br/>O(features × bins × workers)<br/>Merge all histograms"]\n    VP["Voting Parallel<br/>O(top_k × workers)<br/>Only vote counts + winners"]\n    end\n    FP --> R1["Good for:<br/>Few features"]\n    DP --> R2["Good for:<br/>Many features, fast network"]\n    VP --> R3["Good for:<br/>Huge data, slow network"]\n    style FP fill:#ADD8E6\n    style DP fill:#90EE90\n    style VP fill:#FFFACD',
                    },
                    {
                        "step_number": 11,
                        "title": "GPU Parallelism",
                        "explanation": "LightGBM also supports **GPU training**. The GPU builds histograms in parallel across thousands of CUDA cores. Histogram bins map perfectly to GPU's SIMD architecture.",
                        "diagram_data": 'flowchart TB\n    subgraph "GPU Histogram Building"\n    DATA["Training data on GPU memory"]\n    KERN["CUDA Kernel: parallel bin counting"]\n    CORES["1000s of cores process<br/>different data chunks"]\n    HIST["Histograms built in parallel"]\n    end\n    DATA --> KERN --> CORES --> HIST\n    subgraph "Speedup"\n    S1["CPU: 10 seconds"]\n    S2["GPU: 0.5 seconds"]\n    S3["20x faster!"]\n    end\n    HIST --> S3\n    style CORES fill:#90EE90\n    style S3 fill:#90EE90',
                    },
                    {
                        "step_number": 12,
                        "title": "End-to-End Parallel Training Flow",
                        "explanation": "Putting it all together: data is distributed, histograms are built in parallel, merged efficiently, best split is found and applied, then repeat for next node. The tree grows across all workers simultaneously.",
                        "diagram_data": 'flowchart TB\n    subgraph "Distributed Training Loop"\n    A["1. Distribute data to workers"] --> B["2. Build local histograms<br/>(parallel on each worker)"]\n    B --> C["3. Merge/vote for splits<br/>(communication)"]\n    C --> D["4. Find global best split"]\n    D --> E["5. All workers apply split"]\n    E --> F{"More leaves<br/>needed?"}\n    F -->|Yes| B\n    F -->|No| G["6. Tree complete!"]\n    end\n    G --> H["Repeat for next tree<br/>(new residuals)"]\n    style B fill:#90EE90\n    style C fill:#FFB6C1\n    style G fill:#ADD8E6',
                    },
                    {
                        "step_number": 13,
                        "title": "Key Parameters for Parallel Training",
                        "explanation": "Control parallel behavior with: **num_threads** (CPU threads), **device_type** (cpu/gpu/cuda), **tree_learner** (serial/feature/data/voting), **max_bin** (histogram resolution vs speed tradeoff).",
                        "diagram_data": 'flowchart TB\n    subgraph "Parallelism Parameters"\n    P1["num_threads=8<br/>CPU threads per worker"]\n    P2["device_type=\'gpu\'"<br/>Enable GPU training"]\n    P3["tree_learner=\'voting\'"<br/>Choose parallel strategy"]\n    P4["max_bin=255<br/>Histogram resolution"]\n    end\n    subgraph "Recommendations"\n    R1["Single machine:<br/>num_threads=-1 (auto)"]\n    R2["Large data:<br/>device_type=\'gpu\'"]\n    R3["Distributed:<br/>tree_learner=\'voting\'"]\n    R4["Speed vs accuracy:<br/>max_bin=63 to 255"]\n    end\n    P1 --> R1\n    P2 --> R2\n    P3 --> R3\n    P4 --> R4\n    style R1 fill:#90EE90\n    style R2 fill:#90EE90\n    style R3 fill:#90EE90\n    style R4 fill:#FFFACD',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_system_design_visuals(self):
        """Seed System Design visual topics."""
        subject = self.get_or_create_subject(
            "System Design", "system-design", "Architecture"
        )

        # ML Model Serving
        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="ml-model-serving-architecture",
            defaults={
                "title": "ML Model Serving Architecture",
                "description": "Learn the components of a production ML model serving system",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "intermediate",
                "estimated_time_minutes": 8,
                "tags": ["system-design", "mlops", "serving", "architecture"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "Client Request",
                        "explanation": "A prediction request starts from a **client** (web app, mobile app, or internal service). The request contains input features needed for the model to make a prediction.",
                        "diagram_data": 'graph LR\n    Client["Client App"]\n    Client --> |"POST /predict<br/>{features: [...]}"| API["API Gateway"]\n    style Client fill:#ADD8E6\n    style API fill:#E6E6FA',
                    },
                    {
                        "step_number": 1,
                        "title": "API Gateway & Load Balancer",
                        "explanation": "The **API Gateway** handles authentication, rate limiting, and request validation. A **Load Balancer** distributes traffic across multiple model servers for high availability.",
                        "diagram_data": 'graph LR\n    Client["Clients"]\n    Client --> GW["API Gateway<br/>Auth, Rate Limit"]\n    GW --> LB["Load Balancer"]\n    LB --> S1["Server 1"]\n    LB --> S2["Server 2"]\n    LB --> S3["Server 3"]\n    style GW fill:#FFB6C1\n    style LB fill:#90EE90',
                    },
                    {
                        "step_number": 2,
                        "title": "Feature Store Lookup",
                        "explanation": "The model server may need additional features from a **Feature Store**. This provides precomputed features (user history, aggregations) that aren't in the request.",
                        "diagram_data": 'graph TB\n    Req["Request: user_id=123"]\n    Req --> Server["Model Server"]\n    Server --> |"Get features"| FS["Feature Store<br/>(Redis/Feast)"]\n    FS --> |"user_embedding,<br/>purchase_history"| Server\n    style FS fill:#FFFACD',
                    },
                    {
                        "step_number": 3,
                        "title": "Preprocessing Pipeline",
                        "explanation": "Raw features go through a **preprocessing pipeline**: normalization, encoding, missing value handling. This must match exactly what was used during training.",
                        "diagram_data": 'graph LR\n    Raw["Raw Features"]\n    Raw --> Norm["Normalize<br/>Numerical"]\n    Norm --> Enc["Encode<br/>Categorical"]\n    Enc --> Fill["Fill<br/>Missing"]\n    Fill --> Vec["Feature<br/>Vector"]\n    style Vec fill:#90EE90',
                    },
                    {
                        "step_number": 4,
                        "title": "Model Inference",
                        "explanation": "The preprocessed features are passed to the **ML model** for inference. The model is loaded in memory (or accessed via a serving framework like TensorFlow Serving, Triton, or custom).",
                        "diagram_data": 'graph TB\n    Features["Feature Vector"]\n    Features --> Model["ML Model<br/>(In Memory)"]\n    Model --> |"Inference"| Pred["Prediction<br/>score: 0.87"]\n    Cache["Model Cache<br/>Version: v2.3"]\n    Cache -.-> Model\n    style Model fill:#ADD8E6\n    style Pred fill:#90EE90',
                    },
                    {
                        "step_number": 5,
                        "title": "Postprocessing & Response",
                        "explanation": "The raw prediction may need **postprocessing**: applying thresholds, formatting output, adding explanations. The final response is sent back through the API.",
                        "diagram_data": 'graph LR\n    Pred["Raw: 0.87"]\n    Pred --> Post["Postprocess<br/>threshold > 0.5"]\n    Post --> Format["Format<br/>Response"]\n    Format --> Resp["{<br/>prediction: \'positive\',<br/>confidence: 0.87<br/>}"]\n    style Resp fill:#90EE90',
                    },
                    {
                        "step_number": 6,
                        "title": "Logging & Monitoring",
                        "explanation": "Every prediction is **logged** for debugging, monitoring, and model retraining. Metrics like latency, throughput, and prediction distribution are tracked.",
                        "diagram_data": 'graph TB\n    Server["Model Server"]\n    Server --> Log["Prediction Logs<br/>(input, output, latency)"]\n    Server --> Metrics["Metrics<br/>(Prometheus)"]\n    Log --> DW["Data Warehouse<br/>(Retraining)"]\n    Metrics --> Alert["Alerting<br/>(PagerDuty)"]\n    Metrics --> Dash["Dashboard<br/>(Grafana)"]\n    style Log fill:#FFFACD\n    style Metrics fill:#E6E6FA',
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_gpu_generations_visual(self):
        """Seed GPU generations visual topic."""
        subject = self.get_or_create_subject("GPU", "gpu", "Hardware & Architecture")

        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="nvidia-gpu-generations",
            defaults={
                "title": "NVIDIA GPU Generations: Volta to Blackwell",
                "description": "Explore the evolution of NVIDIA GPUs for ML/AI, from Volta's introduction of Tensor Cores to Blackwell's latest innovations",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "intermediate",
                "estimated_time_minutes": 12,
                "tags": ["gpu", "nvidia", "tensor-cores", "cuda", "ml-hardware", "deep-learning"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "GPU Generation Timeline",
                        "explanation": "NVIDIA has released several GPU architectures optimized for AI/ML workloads. Each generation brings significant improvements in Tensor Core performance, memory bandwidth, and specialized features for deep learning.",
                        "diagram_data": """timeline
    title NVIDIA GPU Architectures for AI/ML
    2017 : Volta (V100)
         : 1st Gen Tensor Cores
    2018 : Turing (T4, RTX 20)
         : 2nd Gen Tensor Cores
         : RT Cores introduced
    2020 : Ampere (A100, RTX 30)
         : 3rd Gen Tensor Cores
         : TF32 format
    2022 : Ada Lovelace (L40, RTX 40)
         : 4th Gen Tensor Cores
         : FP8 support
    2022 : Hopper (H100)
         : Transformer Engine
         : HBM3 memory
    2024 : Blackwell (B100/B200)
         : 5th Gen Tensor Cores
         : 2nd Gen Transformer Engine""",
                    },
                    {
                        "step_number": 1,
                        "title": "Volta (2017) - The Tensor Core Revolution",
                        "explanation": "**Volta** introduced **Tensor Cores** - specialized matrix multiply units that revolutionized deep learning training. The V100 became the workhorse of AI research, offering mixed-precision (FP16/FP32) training with massive speedups.\n\n**Key Specs (V100):**\n- 5,120 CUDA Cores\n- 640 Tensor Cores (1st Gen)\n- 16GB/32GB HBM2 (900 GB/s)\n- 125 TFLOPS Tensor (FP16)\n- NVLink 2.0 (300 GB/s)",
                        "diagram_data": """graph TB
    subgraph "Volta V100 Architecture"
        SM["80 Streaming Multiprocessors"]
        TC["640 Tensor Cores<br/>(8 per SM)"]
        CUDA["5,120 CUDA Cores"]
        HBM["HBM2 Memory<br/>16/32GB @ 900 GB/s"]
        NVL["NVLink 2.0<br/>300 GB/s"]
    end

    subgraph "Tensor Core Operation"
        Matrix["D = A × B + C<br/>(4×4 matrices)"]
        FP16["FP16 inputs"]
        FP32["FP32 accumulate"]
    end

    SM --> TC
    SM --> CUDA
    TC --> Matrix
    FP16 --> Matrix
    Matrix --> FP32

    style TC fill:#90EE90
    style Matrix fill:#ADD8E6""",
                    },
                    {
                        "step_number": 2,
                        "title": "Turing (2018) - RT Cores & INT8 Inference",
                        "explanation": "**Turing** brought 2nd Gen Tensor Cores with **INT8 inference** support, enabling faster and more efficient model deployment. Also introduced RT Cores for ray tracing (less relevant for ML).\n\n**Key Specs (T4):**\n- 2,560 CUDA Cores\n- 320 Tensor Cores (2nd Gen)\n- 16GB GDDR6 (320 GB/s)\n- 65 TFLOPS (FP16), 130 TOPS (INT8)\n- Popular for inference workloads",
                        "diagram_data": """graph TB
    subgraph "Turing Improvements"
        TC2["2nd Gen Tensor Cores"]
        INT8["INT8 Precision<br/>2x INT8 throughput"]
        RT["RT Cores<br/>(Ray Tracing)"]
        INF["Inference Optimized"]
    end

    subgraph "T4 Use Cases"
        Cloud["Cloud Inference<br/>(AWS, GCP)"]
        Edge["Edge Deployment"]
        Video["Video Processing"]
    end

    TC2 --> INT8
    INT8 --> INF
    INF --> Cloud
    INF --> Edge
    INF --> Video

    style TC2 fill:#90EE90
    style INT8 fill:#FFFACD
    style INF fill:#ADD8E6""",
                    },
                    {
                        "step_number": 3,
                        "title": "Ampere (2020) - TF32 & Sparsity",
                        "explanation": "**Ampere** introduced **TF32** - a new format that provides FP32-level accuracy with Tensor Core speeds (no code changes needed!). Also added **structural sparsity** support for 2x speedups on sparse models.\n\n**Key Specs (A100):**\n- 6,912 CUDA Cores\n- 432 Tensor Cores (3rd Gen)\n- 40GB/80GB HBM2e (2 TB/s)\n- 312 TFLOPS (TF32), 624 TFLOPS (FP16)\n- Multi-Instance GPU (MIG)\n- NVLink 3.0 (600 GB/s)",
                        "diagram_data": """graph TB
    subgraph "Ampere A100 Features"
        TC3["3rd Gen Tensor Cores"]
        TF32["TF32 Format<br/>FP32 range, FP16 speed"]
        BF16["BF16 Support"]
        Sparse["Structural Sparsity<br/>2:4 pattern = 2x speedup"]
        MIG["Multi-Instance GPU<br/>Up to 7 instances"]
    end

    subgraph "Precision Formats"
        direction LR
        F32["FP32: 19 TFLOPS"]
        T32["TF32: 156 TFLOPS"]
        F16["FP16: 312 TFLOPS"]
        I8["INT8: 624 TOPS"]
    end

    TC3 --> TF32
    TC3 --> BF16
    TC3 --> Sparse

    style TC3 fill:#90EE90
    style TF32 fill:#FFD700
    style Sparse fill:#DDA0DD
    style MIG fill:#ADD8E6""",
                    },
                    {
                        "step_number": 4,
                        "title": "Ada Lovelace (2022) - FP8 & Efficiency",
                        "explanation": "**Ada Lovelace** brought 4th Gen Tensor Cores with **FP8 precision** for even faster inference. Focused on efficiency improvements and consumer/professional markets (RTX 40 series, L40).\n\n**Key Specs (L40):**\n- 18,176 CUDA Cores\n- 568 Tensor Cores (4th Gen)\n- 48GB GDDR6 (864 GB/s)\n- 181 TFLOPS (FP16), 362 TFLOPS (FP8)\n- DLSS 3 / AI-accelerated features",
                        "diagram_data": """graph TB
    subgraph "Ada Lovelace Features"
        TC4["4th Gen Tensor Cores"]
        FP8["FP8 Precision<br/>E4M3 & E5M2 formats"]
        DLSS["DLSS 3<br/>AI Frame Generation"]
        EFF["Power Efficiency<br/>2x perf/watt vs Ampere"]
    end

    subgraph "FP8 Benefits"
        Train["Faster Training<br/>(with loss scaling)"]
        Infer["2x Inference Speed"]
        Mem["Lower Memory Usage"]
    end

    TC4 --> FP8
    FP8 --> Train
    FP8 --> Infer
    FP8 --> Mem

    style TC4 fill:#90EE90
    style FP8 fill:#FFD700
    style EFF fill:#98FB98""",
                    },
                    {
                        "step_number": 5,
                        "title": "Hopper (2022) - Transformer Engine",
                        "explanation": "**Hopper** was designed specifically for large language models with the **Transformer Engine** - hardware that automatically manages FP8/FP16 precision per-layer. Features HBM3 memory and massive improvements for LLM training.\n\n**Key Specs (H100 SXM):**\n- 16,896 CUDA Cores\n- 528 Tensor Cores (4th Gen)\n- 80GB HBM3 (3.35 TB/s)\n- 989 TFLOPS (FP16), 1,979 TFLOPS (FP8)\n- Transformer Engine\n- NVLink 4.0 (900 GB/s)",
                        "diagram_data": """graph TB
    subgraph "Hopper H100 Features"
        TE["Transformer Engine<br/>Auto FP8-FP16 per layer"]
        HBM3["HBM3 Memory<br/>3.35 TB/s bandwidth"]
        NVL4["NVLink 4.0<br/>900 GB/s"]
        DPX["DPX Instructions<br/>Dynamic Programming"]
    end

    subgraph "Transformer Engine Detail"
        Layer1["Layer 1: FP8<br/>(stable gradients)"]
        Layer2["Layer 2: FP16<br/>(sensitive layer)"]
        Layer3["Layer 3: FP8<br/>(stable gradients)"]
        Auto["Automatic Selection<br/>Per-layer optimization"]
    end

    TE --> Layer1
    TE --> Layer2
    TE --> Layer3
    TE --> Auto

    style TE fill:#FFD700
    style HBM3 fill:#ADD8E6
    style Auto fill:#90EE90""",
                    },
                    {
                        "step_number": 6,
                        "title": "Blackwell (2024) - The Next Frontier",
                        "explanation": "**Blackwell** represents NVIDIA's latest architecture with 5th Gen Tensor Cores, 2nd Gen Transformer Engine, and unprecedented scale for training frontier models.\n\n**Key Specs (B200):**\n- 208B transistors (2 dies)\n- 5th Gen Tensor Cores\n- 192GB HBM3e (8 TB/s)\n- 4,500 TFLOPS (FP8), 9,000 TFLOPS (FP4)\n- 2nd Gen Transformer Engine\n- NVLink 5.0 (1.8 TB/s)",
                        "diagram_data": """graph TB
    subgraph "Blackwell B200 Features"
        TC5["5th Gen Tensor Cores"]
        TE2["2nd Gen Transformer Engine"]
        FP4["FP4 Precision<br/>New lowest precision"]
        MCM["Multi-Chip Module<br/>2 dies, 208B transistors"]
        HBM3E["HBM3e Memory<br/>192GB @ 8 TB/s"]
    end

    subgraph "Performance Leap"
        Train["4x Training Speed<br/>vs H100"]
        Infer["30x Inference Speed<br/>for LLMs"]
        Power["25x Energy Efficiency<br/>vs H100"]
    end

    TC5 --> Train
    TE2 --> Infer
    FP4 --> Power

    style TC5 fill:#90EE90
    style TE2 fill:#FFD700
    style FP4 fill:#DDA0DD
    style MCM fill:#ADD8E6""",
                    },
                    {
                        "step_number": 7,
                        "title": "Tensor Core Evolution",
                        "explanation": "Tensor Cores have evolved dramatically across generations, with each version adding new precision formats and capabilities. Understanding these helps you choose the right GPU and optimize your code.",
                        "diagram_data": """graph LR
    subgraph Gen1["1st Gen - Volta"]
        V1["FP16 to FP32"]
    end

    subgraph Gen2["2nd Gen - Turing"]
        V2["FP16 to FP32"]
        V2b["INT8, INT4, INT1"]
    end

    subgraph Gen3["3rd Gen - Ampere"]
        V3["TF32, BF16"]
        V3b["FP64 Tensor Cores"]
        V3c["Sparsity Support"]
    end

    subgraph Gen4["4th Gen - Ada/Hopper"]
        V4["FP8 E4M3, E5M2"]
        V4b["Transformer Engine"]
    end

    subgraph Gen5["5th Gen - Blackwell"]
        V5["FP4"]
        V5b["2nd Gen TE"]
        V5c["9 PFLOPS peak"]
    end

    Gen1 --> Gen2 --> Gen3 --> Gen4 --> Gen5

    style Gen1 fill:#E6E6FA
    style Gen2 fill:#FFFACD
    style Gen3 fill:#ADD8E6
    style Gen4 fill:#90EE90
    style Gen5 fill:#FFD700""",
                    },
                    {
                        "step_number": 8,
                        "title": "Memory Bandwidth Progression",
                        "explanation": "Memory bandwidth is often the bottleneck in ML workloads. Each generation has significantly increased bandwidth through faster memory technologies (HBM2 -> HBM2e -> HBM3 -> HBM3e).",
                        "diagram_data": """graph TB
    subgraph "Memory Evolution"
        V["V100<br/>HBM2<br/>900 GB/s"]
        A["A100<br/>HBM2e<br/>2,039 GB/s"]
        H["H100<br/>HBM3<br/>3,350 GB/s"]
        B["B200<br/>HBM3e<br/>8,000 GB/s"]
    end

    V -->|"2.3x"| A
    A -->|"1.6x"| H
    H -->|"2.4x"| B

    subgraph "Capacity Growth"
        VC["16-32 GB"]
        AC["40-80 GB"]
        HC["80 GB"]
        BC["192 GB"]
    end

    style V fill:#E6E6FA
    style A fill:#ADD8E6
    style H fill:#90EE90
    style B fill:#FFD700""",
                    },
                    {
                        "step_number": 9,
                        "title": "Choosing the Right GPU",
                        "explanation": "Different GPUs serve different purposes. Consider your workload (training vs inference), model size, and budget when selecting hardware.",
                        "diagram_data": """flowchart TD
    Start{What is your use case?}

    Start -->|"Training<br/>Large Models"| Train
    Start -->|"Inference<br/>Production"| Infer
    Start -->|"Development<br/>Experimentation"| Dev

    subgraph Train["Training Recommendations"]
        H100T["H100/H200<br/>LLMs, Foundation Models"]
        A100T["A100 80GB<br/>Large CV/NLP Models"]
        A10T["A10G<br/>Medium Models"]
    end

    subgraph Infer["Inference Recommendations"]
        L40["L40/L40S<br/>Balanced perf/cost"]
        T4["T4<br/>Cost-effective"]
        H100I["H100<br/>Latency-critical LLMs"]
    end

    subgraph Dev["Development Recommendations"]
        RTX["RTX 4090<br/>Best consumer GPU"]
        A10D["A10<br/>Cloud dev instance"]
        T4D["T4<br/>Budget option"]
    end

    style H100T fill:#FFD700
    style A100T fill:#90EE90
    style L40 fill:#ADD8E6
    style RTX fill:#DDA0DD""",
                    },
                    {
                        "step_number": 10,
                        "title": "PyTorch GPU Optimization Tips",
                        "explanation": "To leverage these GPU features in PyTorch, use automatic mixed precision (AMP), enable TF32 on Ampere+, and consider torch.compile for additional optimizations.",
                        "diagram_data": """flowchart LR
    subgraph "Enable Mixed Precision"
        AMP["torch.autocast<br/>torch.amp.GradScaler"]
    end

    subgraph "Enable TF32 - Ampere+"
        TF32["torch.backends.cuda<br/>.matmul.allow_tf32 = True"]
    end

    subgraph "Compile - PyTorch 2.0+"
        Compile["model = torch.compile<br/>mode='max-autotune'"]
    end

    subgraph "Results"
        Speed["2-3x Training Speed"]
        Mem["Lower Memory Usage"]
        Easy["No Code Changes<br/>(for TF32)"]
    end

    AMP --> Speed
    TF32 --> Easy
    Compile --> Speed
    AMP --> Mem

    style AMP fill:#90EE90
    style TF32 fill:#FFD700
    style Compile fill:#ADD8E6""",
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")

    def seed_gpu_architecture_visual(self):
        """Seed GPU architecture visual topic."""
        subject = self.get_or_create_subject("GPU", "gpu", "Hardware & Architecture")

        topic, created = VisualTopic.objects.update_or_create(
            subject=subject,
            slug="gpu-architecture-components",
            defaults={
                "title": "GPU Architecture: Components Deep Dive",
                "description": "Understand the key components of a modern GPU - from Streaming Multiprocessors to memory hierarchy",
                "rendering_type": VisualTopic.RenderingType.MERMAID,
                "difficulty": "intermediate",
                "estimated_time_minutes": 15,
                "tags": ["gpu", "architecture", "cuda", "memory-hierarchy", "streaming-multiprocessor", "tensor-cores"],
                "status": VisualTopic.Status.PUBLISHED,
                "source": "manual",
                "steps": [
                    {
                        "step_number": 0,
                        "title": "GPU vs CPU: High-Level View",
                        "explanation": "A **GPU** is designed for massive parallelism with thousands of simple cores, while a **CPU** has fewer but more powerful cores optimized for sequential tasks. GPUs excel at tasks that can be broken into many independent operations.",
                        "diagram_data": """graph TB
    subgraph CPU["CPU - Few Powerful Cores"]
        direction LR
        C1["Core 1<br/>Complex ALU"]
        C2["Core 2<br/>Complex ALU"]
        C3["Core 3<br/>Complex ALU"]
        C4["Core 4<br/>Complex ALU"]
        CC["Large Cache"]
    end

    subgraph GPU["GPU - Many Simple Cores"]
        direction TB
        SM1["SM"]
        SM2["SM"]
        SM3["SM"]
        SM4["SM"]
        SM5["..."]
        SM6["SM"]
        SMN["80+ SMs"]
    end

    CPU -->|"Best for"| Seq["Sequential Tasks<br/>Complex Logic<br/>Branch-Heavy Code"]
    GPU -->|"Best for"| Par["Parallel Tasks<br/>Matrix Operations<br/>Data-Parallel Workloads"]

    style CPU fill:#ADD8E6
    style GPU fill:#90EE90
    style Par fill:#FFFACD""",
                    },
                    {
                        "step_number": 1,
                        "title": "GPU High-Level Architecture",
                        "explanation": "A modern NVIDIA GPU consists of multiple **Graphics Processing Clusters (GPCs)**, each containing multiple **Streaming Multiprocessors (SMs)**. The GPU also has L2 cache, memory controllers, and high-bandwidth memory (HBM or GDDR).",
                        "diagram_data": """graph TB
    subgraph GPU["NVIDIA GPU - e.g. H100"]
        subgraph GPC1["GPC 1"]
            SM1["SM"]
            SM2["SM"]
            SM3["SM"]
        end
        subgraph GPC2["GPC 2"]
            SM4["SM"]
            SM5["SM"]
            SM6["SM"]
        end
        subgraph GPC3["GPC ..."]
            SM7["SM"]
            SM8["SM"]
            SM9["SM"]
        end

        L2["L2 Cache - 50+ MB"]
        MC["Memory Controllers"]
    end

    HBM["HBM3 Memory<br/>80GB @ 3+ TB/s"]
    PCIE["PCIe Gen5<br/>Host Connection"]
    NVL["NVLink<br/>GPU-to-GPU"]

    MC --> HBM
    GPU --> PCIE
    GPU --> NVL

    style L2 fill:#FFFACD
    style HBM fill:#ADD8E6
    style NVL fill:#90EE90""",
                    },
                    {
                        "step_number": 2,
                        "title": "Streaming Multiprocessor (SM)",
                        "explanation": "The **SM** is the fundamental building block of a GPU. Each SM contains CUDA cores for general computation, Tensor Cores for matrix operations, shared memory/L1 cache, and warp schedulers that manage thread execution.",
                        "diagram_data": """graph TB
    subgraph SM["Streaming Multiprocessor"]
        subgraph Compute["Compute Units"]
            CUDA["128 CUDA Cores<br/>FP32/INT32"]
            TC["4 Tensor Cores<br/>Matrix Ops"]
            SFU["Special Function Units<br/>sin, cos, sqrt"]
            LD["Load/Store Units"]
        end

        subgraph Sched["Scheduling"]
            WS1["Warp Scheduler 1"]
            WS2["Warp Scheduler 2"]
            WS3["Warp Scheduler 3"]
            WS4["Warp Scheduler 4"]
        end

        subgraph Mem["Memory"]
            RF["Register File<br/>256 KB"]
            SMEM["Shared Memory<br/>+ L1 Cache<br/>128-228 KB"]
        end
    end

    Sched --> Compute
    Compute --> Mem

    style TC fill:#90EE90
    style CUDA fill:#ADD8E6
    style SMEM fill:#FFFACD""",
                    },
                    {
                        "step_number": 3,
                        "title": "CUDA Cores",
                        "explanation": "**CUDA Cores** are the basic processing units that execute arithmetic operations. Each CUDA core can perform one floating-point or integer operation per clock cycle. Modern GPUs have thousands of CUDA cores distributed across all SMs.",
                        "diagram_data": """graph TB
    subgraph "CUDA Core"
        FPU["FP32 Unit<br/>Floating Point"]
        ALU["INT32 Unit<br/>Integer"]
        Dispatch["Dispatch Port"]
        Result["Result Bus"]
    end

    subgraph "Operations"
        Add["Addition"]
        Mul["Multiplication"]
        FMA["Fused Multiply-Add<br/>a * b + c"]
        Logic["Bitwise Logic"]
    end

    Dispatch --> FPU
    Dispatch --> ALU
    FPU --> Result
    ALU --> Result
    FPU --> Add
    FPU --> Mul
    FPU --> FMA

    subgraph "Scale"
        Count["H100: 16,896 CUDA Cores<br/>A100: 6,912 CUDA Cores<br/>RTX 4090: 16,384 CUDA Cores"]
    end

    style FMA fill:#90EE90
    style Count fill:#ADD8E6""",
                    },
                    {
                        "step_number": 4,
                        "title": "Tensor Cores",
                        "explanation": "**Tensor Cores** are specialized units designed for matrix multiply-accumulate operations (D = A x B + C). They operate on small matrices (e.g., 4x4 or 8x8) and provide massive speedups for deep learning workloads.",
                        "diagram_data": """graph TB
    subgraph "Tensor Core Operation"
        A["Matrix A<br/>4x4 FP16"]
        B["Matrix B<br/>4x4 FP16"]
        C["Matrix C<br/>4x4 FP32"]
        D["Matrix D<br/>4x4 FP32"]
    end

    A --> MMA["Matrix Multiply<br/>Accumulate"]
    B --> MMA
    C --> MMA
    MMA --> D

    subgraph "Supported Precisions"
        FP16["FP16/BF16"]
        TF32["TF32"]
        FP8["FP8"]
        INT8["INT8"]
        FP64["FP64 - A100+"]
    end

    subgraph "Performance - H100"
        TFLOP["FP16: 989 TFLOPS<br/>FP8: 1,979 TFLOPS<br/>vs CUDA: ~60 TFLOPS"]
    end

    style MMA fill:#90EE90
    style D fill:#FFFACD
    style TFLOP fill:#ADD8E6""",
                    },
                    {
                        "step_number": 5,
                        "title": "Warp Schedulers and Execution",
                        "explanation": "Threads on a GPU are organized into **warps** of 32 threads that execute in lockstep (SIMT - Single Instruction, Multiple Threads). **Warp schedulers** select ready warps and issue instructions to the execution units.",
                        "diagram_data": """graph TB
    subgraph "Thread Hierarchy"
        Grid["Grid<br/>All Threads"]
        Block["Thread Block<br/>Up to 1024 threads"]
        Warp["Warp<br/>32 threads"]
        Thread["Thread"]
    end

    Grid --> Block
    Block --> Warp
    Warp --> Thread

    subgraph "Warp Execution"
        WS["Warp Scheduler"]
        Ready["Ready Warps"]
        Stalled["Stalled Warps<br/>waiting for memory"]
        Exec["Execute 1 instruction<br/>across all 32 threads"]
    end

    WS --> Ready
    Ready --> Exec
    Stalled -.->|"data arrives"| Ready

    subgraph "Key Concept"
        SIMT["SIMT: All 32 threads<br/>execute SAME instruction<br/>on DIFFERENT data"]
    end

    style Warp fill:#90EE90
    style SIMT fill:#FFFACD
    style WS fill:#ADD8E6""",
                    },
                    {
                        "step_number": 6,
                        "title": "Memory Hierarchy Overview",
                        "explanation": "GPUs have a complex memory hierarchy optimized for throughput. Understanding it is crucial for writing efficient GPU code. Memory closer to the cores is faster but smaller.",
                        "diagram_data": """graph TB
    subgraph "Memory Hierarchy - Fastest to Slowest"
        R["Registers<br/>~256 KB per SM<br/>~0 cycles latency"]
        SM["Shared Memory / L1<br/>~128-228 KB per SM<br/>~20-30 cycles"]
        L2["L2 Cache<br/>~50 MB total<br/>~200 cycles"]
        HBM["HBM / Global Memory<br/>80 GB<br/>~400-800 cycles"]
    end

    R -->|"Fastest"| SM
    SM --> L2
    L2 -->|"Slowest"| HBM

    subgraph "Bandwidth"
        BW_R["Registers: ~20 TB/s"]
        BW_SM["Shared: ~10 TB/s"]
        BW_L2["L2: ~5 TB/s"]
        BW_HBM["HBM3: ~3 TB/s"]
    end

    style R fill:#90EE90
    style SM fill:#FFFACD
    style L2 fill:#ADD8E6
    style HBM fill:#E6E6FA""",
                    },
                    {
                        "step_number": 7,
                        "title": "Registers",
                        "explanation": "**Registers** are the fastest memory, private to each thread. The compiler allocates registers automatically. Using too many registers per thread reduces **occupancy** (number of concurrent warps).",
                        "diagram_data": """graph TB
    subgraph "Register Allocation"
        Thread1["Thread 1<br/>32 registers"]
        Thread2["Thread 2<br/>32 registers"]
        ThreadN["Thread N<br/>32 registers"]
        Pool["SM Register File<br/>65,536 registers"]
    end

    Pool --> Thread1
    Pool --> Thread2
    Pool --> ThreadN

    subgraph "Trade-off"
        More["More Registers/Thread"]
        Fewer["Fewer Active Warps"]
        Less["Less Latency Hiding"]
    end

    More --> Fewer --> Less

    subgraph "Best Practice"
        Tip["Limit register usage<br/>Use --maxrregcount<br/>Monitor with nvcc -Xptxas -v"]
    end

    style Pool fill:#90EE90
    style Tip fill:#ADD8E6""",
                    },
                    {
                        "step_number": 8,
                        "title": "Shared Memory",
                        "explanation": "**Shared Memory** is fast, programmer-managed memory shared by all threads in a thread block. It's ideal for data reuse within a block and reducing global memory access.",
                        "diagram_data": """graph TB
    subgraph "Thread Block"
        T1["Thread 1"]
        T2["Thread 2"]
        T3["Thread 3"]
        TN["Thread N"]
        SMEM["Shared Memory<br/>Up to 228 KB"]
    end

    T1 <--> SMEM
    T2 <--> SMEM
    T3 <--> SMEM
    TN <--> SMEM

    subgraph "Use Cases"
        Tile["Matrix Tiling"]
        Reduce["Reductions"]
        Comm["Thread Communication"]
        Cache["Manual Caching"]
    end

    SMEM --> Tile
    SMEM --> Reduce
    SMEM --> Comm

    subgraph "Code Example"
        Code["__shared__ float data[256]<br/>data[threadIdx.x] = ...<br/>__syncthreads()<br/>// All threads can read"]
    end

    style SMEM fill:#FFFACD
    style Code fill:#E6E6FA""",
                    },
                    {
                        "step_number": 9,
                        "title": "L2 Cache and Global Memory",
                        "explanation": "**L2 Cache** is shared across all SMs and automatically caches global memory accesses. **Global Memory (HBM)** is the largest but slowest memory, accessible by all threads and the CPU.",
                        "diagram_data": """graph TB
    subgraph "All SMs"
        SM1["SM 1"]
        SM2["SM 2"]
        SMN["SM N"]
    end

    L2["L2 Cache<br/>50+ MB<br/>Automatic Caching"]

    SM1 <--> L2
    SM2 <--> L2
    SMN <--> L2

    subgraph "Memory Controllers"
        MC1["MC 1"]
        MC2["MC 2"]
        MC3["MC 3"]
    end

    L2 <--> MC1
    L2 <--> MC2
    L2 <--> MC3

    HBM["HBM3 Global Memory<br/>80 GB @ 3+ TB/s"]

    MC1 <--> HBM
    MC2 <--> HBM
    MC3 <--> HBM

    style L2 fill:#ADD8E6
    style HBM fill:#E6E6FA""",
                    },
                    {
                        "step_number": 10,
                        "title": "Memory Coalescing",
                        "explanation": "**Memory coalescing** is critical for performance. When threads in a warp access consecutive memory addresses, the GPU combines them into fewer memory transactions. Uncoalesced access wastes bandwidth.",
                        "diagram_data": """graph TB
    subgraph "Coalesced Access - GOOD"
        W1["Warp: 32 Threads"]
        CA["Thread 0 -> addr 0<br/>Thread 1 -> addr 4<br/>Thread 2 -> addr 8<br/>...<br/>Thread 31 -> addr 124"]
        One["1 Memory Transaction<br/>128 bytes"]
    end

    W1 --> CA --> One

    subgraph "Uncoalesced Access - BAD"
        W2["Warp: 32 Threads"]
        UA["Thread 0 -> addr 0<br/>Thread 1 -> addr 512<br/>Thread 2 -> addr 1024<br/>...<br/>Random pattern"]
        Many["32 Memory Transactions<br/>Massive slowdown"]
    end

    W2 --> UA --> Many

    style One fill:#90EE90
    style Many fill:#FFB6C1""",
                    },
                    {
                        "step_number": 11,
                        "title": "NVLink and PCIe",
                        "explanation": "**NVLink** provides high-bandwidth GPU-to-GPU communication (up to 900 GB/s on H100), enabling multi-GPU training. **PCIe** connects the GPU to the CPU/host memory (much slower, ~64 GB/s for Gen5).",
                        "diagram_data": """graph TB
    subgraph "Multi-GPU System"
        GPU1["GPU 1"]
        GPU2["GPU 2"]
        GPU3["GPU 3"]
        GPU4["GPU 4"]
    end

    GPU1 <-->|"NVLink<br/>900 GB/s"| GPU2
    GPU2 <-->|"NVLink"| GPU3
    GPU3 <-->|"NVLink"| GPU4
    GPU4 <-->|"NVLink"| GPU1

    CPU["CPU / Host"]
    RAM["System RAM"]

    GPU1 <-->|"PCIe Gen5<br/>64 GB/s"| CPU
    CPU <--> RAM

    subgraph "Use Cases"
        NVL_Use["NVLink: Tensor Parallelism<br/>All-Reduce, P2P Transfer"]
        PCIe_Use["PCIe: Data Loading<br/>Model Transfer"]
    end

    style GPU1 fill:#90EE90
    style GPU2 fill:#90EE90
    style GPU3 fill:#90EE90
    style GPU4 fill:#90EE90
    style NVL_Use fill:#ADD8E6""",
                    },
                    {
                        "step_number": 12,
                        "title": "Putting It All Together",
                        "explanation": "When you launch a CUDA kernel, the GPU distributes thread blocks across SMs, warps get scheduled, threads access memory through the hierarchy, and results flow back. Understanding this flow helps optimize performance.",
                        "diagram_data": """graph TB
    subgraph "Kernel Launch"
        Host["Host - CPU"]
        Launch["kernel<<<grid, block>>>"]
    end

    Host --> Launch

    subgraph "GPU Execution"
        Dist["Thread Block<br/>Distribution"]
        SM1["SM 1<br/>Blocks 0, 4, 8..."]
        SM2["SM 2<br/>Blocks 1, 5, 9..."]
        SMN["SM N<br/>Blocks 3, 7, 11..."]
    end

    Launch --> Dist
    Dist --> SM1
    Dist --> SM2
    Dist --> SMN

    subgraph "Per-SM Execution"
        WS["Warp Schedulers<br/>Issue Instructions"]
        Cores["CUDA/Tensor Cores<br/>Compute"]
        Mem["Memory Access<br/>Reg->Shared->L2->HBM"]
    end

    SM1 --> WS --> Cores --> Mem

    subgraph "Optimization Goals"
        Occ["High Occupancy<br/>many active warps"]
        Coal["Coalesced Memory"]
        Reuse["Data Reuse<br/>shared memory"]
    end

    style Launch fill:#ADD8E6
    style Cores fill:#90EE90
    style Occ fill:#FFFACD""",
                    },
                ],
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Updated'}: {topic.title}")
