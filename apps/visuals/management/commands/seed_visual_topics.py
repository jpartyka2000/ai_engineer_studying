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
        self.seed_sklearn_visuals()
        self.seed_isolation_forest_visual()
        self.seed_transformers_visuals()
        self.seed_lightgbm_visuals()
        self.seed_system_design_visuals()

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
