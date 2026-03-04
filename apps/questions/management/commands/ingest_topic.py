"""Management command to ingest all documents for a topic and generate questions."""

import hashlib
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError
from django.utils.text import slugify

from apps.questions.models import StudyMaterial
from apps.questions.services import get_question_generator
from apps.subjects.models import Subject


class Command(BaseCommand):
    """Ingest all documents from a topic folder into StudyMaterial and generate questions."""

    help = "Ingest all documents from llm_studying folder and generate questions"

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
            "topic",
            type=str,
            help="Topic folder name (e.g., 'git', 'lightgbm')",
        )
        parser.add_argument(
            "--source-dir",
            type=str,
            default="llm_studying",
            help="Path to the llm_studying directory (relative to project root)",
        )
        parser.add_argument(
            "--questions-per-file",
            type=int,
            default=2,
            help="Number of questions to generate per file (default: 2)",
        )
        parser.add_argument(
            "--skip-questions",
            action="store_true",
            help="Only store documents, skip question generation",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be ingested without making changes",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=1.0,
            help="Delay in seconds between API calls (default: 1.0)",
        )
        parser.add_argument(
            "--max-files",
            type=int,
            default=None,
            help="Maximum number of files to process (default: all)",
        )
        parser.add_argument(
            "--generate-missing",
            action="store_true",
            help="Generate questions for existing materials that have none",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        topic = options["topic"]
        source_dir = Path(settings.BASE_DIR) / options["source_dir"]
        topic_dir = source_dir / topic

        # Validate topic directory exists
        if not topic_dir.exists():
            raise CommandError(f"Topic directory not found: {topic_dir}")

        if not topic_dir.is_dir():
            raise CommandError(f"Not a directory: {topic_dir}")

        # Get or create subject
        subject = self.get_or_create_subject(topic, options["dry_run"])

        # Get all document files
        files = self.get_document_files(topic_dir, options.get("max_files"))

        if not files:
            self.stdout.write(self.style.WARNING(f"No documents found in {topic_dir}"))
            return

        self.stdout.write(f"Found {len(files)} document(s) in {topic}")

        if options["dry_run"]:
            self.show_dry_run(files, subject, options)
            return

        # Ingest documents
        materials = self.ingest_documents(files, subject)

        self.stdout.write(
            self.style.SUCCESS(f"Stored {len(materials)} document(s) as StudyMaterial")
        )

        # Generate questions if not skipped
        if not options["skip_questions"]:
            # If --generate-missing, include existing materials without questions
            if options["generate_missing"]:
                existing_without_questions = StudyMaterial.objects.filter(
                    subject=subject,
                    questions_generated=0,
                    is_active=True,
                ).exclude(id__in=[m.id for m in materials])

                if existing_without_questions.exists():
                    count = existing_without_questions.count()
                    self.stdout.write(
                        f"Found {count} existing material(s) without questions"
                    )
                    materials = list(materials) + list(existing_without_questions)

            self.generate_questions(
                materials=materials,
                subject=subject,
                questions_per_file=options["questions_per_file"],
                delay=options["delay"],
            )

        self.stdout.write(self.style.SUCCESS("Ingestion complete!"))

    def get_or_create_subject(self, folder_name: str, dry_run: bool) -> Subject | None:
        """Get or create the Subject record for this topic."""
        if folder_name in self.FOLDER_MAPPINGS:
            name, category = self.FOLDER_MAPPINGS[folder_name]
        else:
            name = folder_name.replace("_", " ").title()
            category = "Other"

        slug = slugify(folder_name)

        if dry_run:
            self.stdout.write(f"Subject: {name} ({category})")
            return None

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
            self.stdout.write(self.style.SUCCESS(f"Created subject: {name}"))
        else:
            self.stdout.write(f"Using existing subject: {name}")

        return subject

    def get_document_files(self, topic_dir: Path, max_files: int | None) -> list[Path]:
        """Get all document files from the topic directory."""
        extensions = [".txt", ".md"]
        files = []

        for ext in extensions:
            files.extend(topic_dir.glob(f"*{ext}"))

        # Sort by name for consistent ordering
        files = sorted(files, key=lambda x: x.name)

        if max_files:
            files = files[:max_files]

        return files

    def show_dry_run(
        self, files: list[Path], subject: Subject | None, options: dict
    ) -> None:
        """Show what would be ingested in dry run mode."""
        self.stdout.write("\n" + self.style.WARNING("DRY RUN - No changes made"))
        self.stdout.write(f"\nWould ingest {len(files)} document(s):\n")

        for f in files:
            content = f.read_text(encoding="utf-8", errors="ignore")
            tokens = len(content) // 4
            self.stdout.write(f"  - {f.name} ({tokens:,} tokens)")

        if not options["skip_questions"]:
            total_questions = len(files) * options["questions_per_file"]
            self.stdout.write(f"\nWould generate ~{total_questions} questions")

    def ingest_documents(
        self, files: list[Path], subject: Subject
    ) -> list[StudyMaterial]:
        """Ingest document files as StudyMaterial records."""
        materials = []

        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  Error reading {file_path.name}: {e}")
                )
                continue

            # Skip empty files
            if not content.strip():
                self.stdout.write(f"  Skipping empty file: {file_path.name}")
                continue

            # Generate content hash
            content_hash = hashlib.sha256(content.encode()).hexdigest()

            # Check for existing material
            try:
                material, created = StudyMaterial.objects.get_or_create(
                    subject=subject,
                    content_hash=content_hash,
                    defaults={
                        "title": file_path.stem.replace("_", " ").title(),
                        "content": content,
                        "source_file": str(file_path),
                        "token_estimate": len(content) // 4,
                    },
                )

                if created:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  + {file_path.name} ({material.token_estimate:,} tokens)"
                        )
                    )
                    materials.append(material)
                else:
                    self.stdout.write(f"  = {file_path.name} (already exists)")

            except IntegrityError:
                self.stdout.write(f"  = {file_path.name} (duplicate)")

        return materials

    def generate_questions(
        self,
        materials: list[StudyMaterial],
        subject: Subject,
        questions_per_file: int,
        delay: float,
    ) -> None:
        """Generate questions from study materials."""
        if not materials:
            return

        generator = get_question_generator()
        total_generated = 0

        self.stdout.write(
            f"\nGenerating questions from {len(materials)} document(s)..."
        )

        for material in materials:
            self.stdout.write(f"  Processing: {material.title}")

            try:
                questions = generator.import_from_file(
                    file_path=Path(material.source_file),
                    subject=subject,
                    num_questions=questions_per_file,
                    difficulty=None,  # Let Claude assign difficulty
                )

                # Update material with question count
                material.questions_generated = len(questions)
                material.save(update_fields=["questions_generated"])

                total_generated += len(questions)
                self.stdout.write(
                    self.style.SUCCESS(f"    Generated {len(questions)} question(s)")
                )

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"    Error: {e}"))

            # Delay between API calls
            if delay > 0:
                time.sleep(delay)

        self.stdout.write(
            self.style.SUCCESS(f"\nTotal questions generated: {total_generated}")
        )
