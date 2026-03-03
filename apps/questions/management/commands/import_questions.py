"""Management command to import questions from llm_studying directory."""

import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from apps.questions.services import get_question_generator
from apps.subjects.models import Subject


class Command(BaseCommand):
    """Import questions from llm_studying files into the database."""

    help = "Import questions from llm_studying directory using Claude API"

    # Mapping of folder names to display names and categories
    FOLDER_MAPPINGS = {
        "python": ("Python", "Python Core"),
        "pandas": ("Pandas", "Data Science"),
        "pyspark": ("PySpark", "Data Engineering"),
        "sql": ("SQL", "Data Engineering"),
        "git": ("Git", "DevOps & Tooling"),
        "lightgbm": ("LightGBM", "ML Frameworks"),
        "scikit-learn": ("scikit-learn", "ML Frameworks"),
        "machine_learning": ("Machine Learning", "ML Concepts"),
        "statistics": ("Statistics & Probability", "ML Concepts"),
        "generative_ai": ("Generative AI", "AI/ML"),
        "reinforcement_learning": ("Reinforcement Learning", "ML Concepts"),
        "agents": ("AI Agents", "AI/ML"),
        "databricks": ("Databricks", "Data Engineering"),
        "mlflow": ("MLflow", "ML Ops"),
        "testing": ("Testing", "Software Engineering"),
        "software_engineering": ("Software Engineering", "Software Engineering"),
        "async_programming": ("Async Programming", "Python Core"),
        "pydantic": ("Pydantic", "Python Libraries"),
        "logging": ("Python Logging", "Python Core"),
        "pathlib": ("Pathlib", "Python Core"),
        "numpy": ("NumPy", "Data Science"),
        "visualizations": ("Data Visualization", "Data Science"),
        "container_management": ("Docker & Containers", "DevOps & Tooling"),
        "linux": ("Linux", "DevOps & Tooling"),
        "aws": ("AWS", "Cloud"),
        "modal": ("Modal", "Cloud"),
        "api_development": ("API Development", "Software Engineering"),
        "explainability": ("ML Explainability", "ML Concepts"),
        "feature_engineering": ("Feature Engineering", "ML Concepts"),
        "eda": ("Exploratory Data Analysis", "Data Science"),
        "text_processing": ("Text Processing", "Python Core"),
        "argparse": ("Argparse", "Python Core"),
        "claude_code": ("Claude Code", "AI/ML"),
        "vscode": ("VS Code", "DevOps & Tooling"),
        "pkg_management": ("Package Management", "Python Core"),
        "google_tools": ("Google Tools", "Cloud"),
        "gpu": ("GPU Computing", "ML Ops"),
        "latex": ("LaTeX", "Documentation"),
        "excel_and_friends": ("Excel & Spreadsheets", "Data Science"),
        "mac": ("macOS", "DevOps & Tooling"),
        "xgboost": ("XGBoost", "ML Frameworks"),
        "architecture": ("System Architecture", "Software Engineering"),
        "computer_architecture": ("Computer Architecture", "Fundamentals"),
        "data_engineering": ("Data Engineering", "Data Engineering"),
        "diagramming_tools": ("Diagramming Tools", "Documentation"),
        "mllib": ("MLlib", "ML Frameworks"),
        "notion": ("Notion", "Productivity"),
        "slack": ("Slack", "Productivity"),
        "metabase": ("Metabase", "Data Science"),
        "microsoft_excel": ("Microsoft Excel", "Data Science"),
    }

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--source-dir",
            type=str,
            default="llm_studying",
            help="Path to the llm_studying directory (relative to project root)",
        )
        parser.add_argument(
            "--subject",
            type=str,
            help="Only import questions for a specific subject (folder name)",
        )
        parser.add_argument(
            "--max-files",
            type=int,
            default=5,
            help="Maximum number of files to process per subject",
        )
        parser.add_argument(
            "--questions-per-file",
            type=int,
            default=2,
            help="Number of questions to generate per file",
        )
        parser.add_argument(
            "--difficulty",
            type=str,
            default="intermediate",
            choices=["beginner", "intermediate", "advanced"],
            help="Difficulty level for generated questions",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without actually importing",
        )
        parser.add_argument(
            "--list-subjects",
            action="store_true",
            help="List available subjects and exit",
        )
        parser.add_argument(
            "--create-subjects-only",
            action="store_true",
            help="Only create subject records, don't import questions",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=1.0,
            help="Delay in seconds between API calls to avoid rate limiting",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        source_dir = Path(settings.BASE_DIR) / options["source_dir"]

        if not source_dir.exists():
            raise CommandError(f"Source directory not found: {source_dir}")

        # List subjects mode
        if options["list_subjects"]:
            self.list_subjects(source_dir)
            return

        # Get subject folders
        subject_folders = self.get_subject_folders(source_dir, options.get("subject"))

        if not subject_folders:
            self.stdout.write(self.style.WARNING("No subject folders found"))
            return

        self.stdout.write(f"Found {len(subject_folders)} subject folder(s)")

        # Create or get subjects
        subjects = self.create_subjects(subject_folders, options["dry_run"])

        if options["create_subjects_only"]:
            self.stdout.write(self.style.SUCCESS("Subjects created successfully"))
            return

        if options["dry_run"]:
            self.show_dry_run_summary(subject_folders, options)
            return

        # Import questions
        self.import_questions(
            subjects=subjects,
            source_dir=source_dir,
            max_files=options["max_files"],
            questions_per_file=options["questions_per_file"],
            difficulty=options["difficulty"],
            delay=options["delay"],
        )

    def get_subject_folders(
        self, source_dir: Path, subject_filter: str | None
    ) -> list[Path]:
        """Get list of subject folders to process."""
        folders = []

        for item in source_dir.iterdir():
            if not item.is_dir():
                continue
            if item.name.startswith("."):
                continue
            if subject_filter and item.name != subject_filter:
                continue
            folders.append(item)

        return sorted(folders, key=lambda x: x.name)

    def folder_to_subject_info(self, folder_name: str) -> tuple[str, str, str]:
        """Convert folder name to (name, slug, category)."""
        if folder_name in self.FOLDER_MAPPINGS:
            name, category = self.FOLDER_MAPPINGS[folder_name]
        else:
            # Convert folder name to display name
            name = folder_name.replace("_", " ").title()
            category = "Other"

        slug = slugify(folder_name)
        return name, slug, category

    def create_subjects(self, folders: list[Path], dry_run: bool) -> dict[str, Subject]:
        """Create Subject records for each folder."""
        subjects = {}

        for folder in folders:
            name, slug, category = self.folder_to_subject_info(folder.name)

            if dry_run:
                self.stdout.write(f"  Would create subject: {name} ({category})")
                subjects[folder.name] = None
                continue

            subject, created = Subject.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "category": category,
                    "description": f"Study materials for {name}",
                    "is_active": True,
                },
            )

            if created:
                self.stdout.write(self.style.SUCCESS(f"  Created subject: {name}"))
            else:
                self.stdout.write(f"  Subject exists: {name}")

            subjects[folder.name] = subject

        return subjects

    def list_subjects(self, source_dir: Path):
        """List available subjects in the source directory."""
        self.stdout.write("\nAvailable subjects in llm_studying:\n")

        for folder in sorted(source_dir.iterdir()):
            if not folder.is_dir() or folder.name.startswith("."):
                continue

            name, slug, category = self.folder_to_subject_info(folder.name)
            file_count = len(list(folder.glob("*.txt")))
            self.stdout.write(
                f"  {folder.name:30} -> {name:25} ({category}) [{file_count} files]"
            )

    def show_dry_run_summary(self, folders: list[Path], options: dict):
        """Show summary of what would be imported."""
        self.stdout.write("\n" + self.style.WARNING("DRY RUN - No changes made"))
        self.stdout.write(f"\nWould process {len(folders)} subject(s):")

        for folder in folders:
            files = list(folder.glob("*.txt"))[: options["max_files"]]
            self.stdout.write(f"\n  {folder.name}:")
            for f in files:
                self.stdout.write(f"    - {f.name}")

    def import_questions(
        self,
        subjects: dict[str, Subject],
        source_dir: Path,
        max_files: int,
        questions_per_file: int,
        difficulty: str,
        delay: float,
    ):
        """Import questions from files for each subject."""
        generator = get_question_generator()
        total_imported = 0

        for folder_name, subject in subjects.items():
            if subject is None:
                continue

            folder = source_dir / folder_name
            files = list(folder.glob("*.txt"))[:max_files]

            self.stdout.write(f"\nProcessing {subject.name} ({len(files)} files)...")

            for file_path in files:
                self.stdout.write(f"  Importing: {file_path.name}")

                try:
                    questions = generator.import_from_file(
                        file_path=file_path,
                        subject=subject,
                        num_questions=questions_per_file,
                        difficulty=difficulty,
                    )
                    total_imported += len(questions)
                    self.stdout.write(
                        self.style.SUCCESS(f"    Generated {len(questions)} questions")
                    )
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"    Error: {e}"))

                # Delay to avoid rate limiting
                if delay > 0:
                    time.sleep(delay)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nImport complete! Total questions imported: {total_imported}"
            )
        )
