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

    # Supported file extensions
    TEXT_EXTENSIONS = [".txt", ".md"]
    IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp"]

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
        parser.add_argument(
            "--provider",
            type=str,
            choices=["claude", "openai"],
            default=None,
            help="LLM provider for question generation (default: uses LLM_PROVIDER setting)",
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
                provider=options.get("provider"),
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
        """Get all document files (text and images) from the topic directory."""
        all_extensions = self.TEXT_EXTENSIONS + self.IMAGE_EXTENSIONS
        files = []

        for ext in all_extensions:
            files.extend(topic_dir.glob(f"*{ext}"))

        # Sort by name for consistent ordering
        files = sorted(files, key=lambda x: x.name)

        if max_files:
            files = files[:max_files]

        return files

    def is_image_file(self, file_path: Path) -> bool:
        """Check if a file is an image based on extension."""
        return file_path.suffix.lower() in self.IMAGE_EXTENSIONS

    def show_dry_run(
        self, files: list[Path], subject: Subject | None, options: dict
    ) -> None:
        """Show what would be ingested in dry run mode."""
        self.stdout.write("\n" + self.style.WARNING("DRY RUN - No changes made"))
        self.stdout.write(f"\nWould ingest {len(files)} document(s):\n")

        text_count = 0
        image_count = 0
        for f in files:
            if self.is_image_file(f):
                size_kb = f.stat().st_size / 1024
                self.stdout.write(f"  - {f.name} (image, {size_kb:.1f} KB)")
                image_count += 1
            else:
                content = f.read_text(encoding="utf-8", errors="ignore")
                tokens = len(content) // 4
                self.stdout.write(f"  - {f.name} ({tokens:,} tokens)")
                text_count += 1

        self.stdout.write(f"\n  Text files: {text_count}, Image files: {image_count}")

        if not options["skip_questions"]:
            total_questions = len(files) * options["questions_per_file"]
            self.stdout.write(f"\nWould generate ~{total_questions} questions")

    def ingest_documents(
        self, files: list[Path], subject: Subject
    ) -> list[StudyMaterial]:
        """Ingest document files (text and images) as StudyMaterial records."""
        materials = []

        for file_path in files:
            is_image = self.is_image_file(file_path)

            try:
                if is_image:
                    # For images, read binary and use placeholder content
                    image_bytes = file_path.read_bytes()
                    content_hash = hashlib.sha256(image_bytes).hexdigest()
                    content = f"[Image file: {file_path.name}]"
                    token_estimate = 0  # Images don't have tokens
                    size_info = f"{len(image_bytes) / 1024:.1f} KB"
                else:
                    # For text files, read content
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    if not content.strip():
                        self.stdout.write(f"  Skipping empty file: {file_path.name}")
                        continue
                    content_hash = hashlib.sha256(content.encode()).hexdigest()
                    token_estimate = len(content) // 4
                    size_info = f"{token_estimate:,} tokens"
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  Error reading {file_path.name}: {e}")
                )
                continue

            # Check for existing material
            try:
                material, created = StudyMaterial.objects.get_or_create(
                    subject=subject,
                    content_hash=content_hash,
                    defaults={
                        "title": file_path.stem.replace("_", " ").title(),
                        "content": content,
                        "source_file": str(file_path),
                        "token_estimate": token_estimate,
                    },
                )

                if created:
                    file_type = "image" if is_image else "text"
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  + {file_path.name} ({file_type}, {size_info})"
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
        provider: str | None = None,
    ) -> None:
        """Generate questions from study materials (text and images)."""
        if not materials:
            return

        generator = get_question_generator(provider)
        total_generated = 0

        self.stdout.write(
            f"\nGenerating questions from {len(materials)} document(s) "
            f"using {generator.provider_name}..."
        )

        for material in materials:
            source_path = Path(material.source_file)
            is_image = self.is_image_file(source_path)
            file_type = "image" if is_image else "text"
            self.stdout.write(f"  Processing ({file_type}): {material.title}")

            try:
                if is_image:
                    # Use vision API for images
                    questions = generator.import_from_image(
                        image_path=source_path,
                        subject=subject,
                        num_questions=questions_per_file,
                        difficulty=None,  # Let LLM assign difficulty
                    )
                else:
                    # Use text API for documents
                    questions = generator.import_from_file(
                        file_path=source_path,
                        subject=subject,
                        num_questions=questions_per_file,
                        difficulty=None,  # Let LLM assign difficulty
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
