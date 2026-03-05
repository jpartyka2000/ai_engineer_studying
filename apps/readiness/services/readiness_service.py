"""
Readiness calculator service for interview preparation assessment.

Calculates weighted readiness scores across study modes and categories.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING, Literal

from django.utils import timezone

if TYPE_CHECKING:
    from django.contrib.auth.models import User

logger = logging.getLogger(__name__)

RoleLevelType = Literal["entry", "senior", "principal"]
DifficultyType = Literal["beginner", "intermediate", "advanced"]


@dataclass
class ModePerformance:
    """Performance in a single study mode."""

    mode_name: str
    sessions_count: int
    total_correct: int
    total_attempted: int
    accuracy: float  # 0-100
    weighted_score: float  # After applying mode weight
    difficulty_breakdown: dict[DifficultyType, dict] = field(default_factory=dict)


@dataclass
class CategoryReadiness:
    """Readiness assessment for a subject category."""

    category_name: str
    required: bool
    subjects_in_category: list[str]
    subjects_attempted: list[str]
    subjects_required: int
    score: float  # 0-100
    is_covered: bool
    gap_subjects: list[str]  # Subjects needing more work


@dataclass
class DifficultyReadiness:
    """Performance by difficulty level."""

    difficulty: str
    correct: int
    total: int
    accuracy: float
    meets_threshold: bool
    required_threshold: float


@dataclass
class StudyRecommendation:
    """A specific study recommendation."""

    priority: int  # 1 = highest
    recommendation_type: str
    category: str  # Category name (e.g., "ML Frameworks")
    topic_name: str  # Topic/subject display name (e.g., "LightGBM")
    title: str
    description: str
    action_url: str
    subject_slug: str | None
    mode: str | None
    difficulty: str | None
    estimated_sessions: int


@dataclass
class ReadinessAssessment:
    """Complete readiness assessment result."""

    user_id: int
    role_level: RoleLevelType
    assessment_date: date
    period_start: date
    period_end: date

    # Overall status
    overall_score: float
    is_ready: bool
    threshold: float

    # Mode breakdown
    mode_performances: dict[str, ModePerformance]

    # Category coverage
    category_readiness: dict[str, CategoryReadiness]
    required_categories_met: int
    required_categories_total: int

    # Difficulty analysis
    difficulty_readiness: dict[str, DifficultyReadiness]

    # Study plan
    recommendations: list[StudyRecommendation] = field(default_factory=list)

    # Activity summary
    total_sessions: int = 0
    total_questions: int = 0
    study_days: int = 0


class ReadinessCalculatorService:
    """
    Core service for calculating interview readiness scores.

    Implements the weighted scoring algorithm and category coverage checks.
    """

    # Mode weights (must sum to 1.0)
    MODE_WEIGHTS = {
        "coding": 0.40,
        "exam": 0.25,
        "argument": 0.20,
        "lightning": 0.15,
    }

    # Required categories for interview readiness (combined)
    REQUIRED_CATEGORIES = [
        "ML Frameworks",
        "Python Core",
        "Data Science",
        "Data Engineering",  # Contains SQL
        "Software Engineering",  # Contains System Design
    ]

    # Engineering track definitions
    ENGINEERING_TRACKS = {
        "ml_engineering": {
            "name": "ML Engineering",
            "description": "Building and deploying machine learning models at scale",
            "categories": [
                # Core ML categories
                "ML Frameworks",
                "ML Concepts",
                "Deep Learning",
                "Data Science",
                "Data Engineering",
                # Shared core categories
                "Python Core",
                "Python Libraries",
                "Fundamentals",
                # Deployment & operations
                "ML Ops",
            ],
            "priority_topics": [
                # ML Frameworks
                "scikit-learn",
                "lightgbm",
                "pytorch",
                "tensorflow",
                # Data & processing
                "pandas",
                "sql",
                "pyspark",
                "numpy",
                # ML operations
                "mlflow",
                "feature-engineering",
                "model-evaluation",
                # Statistics & fundamentals
                "statistics",
                "probability",
                "linear-algebra",
            ],
        },
        "ai_engineering": {
            "name": "AI Engineering",
            "description": "Building AI-powered applications and systems",
            "categories": [
                # Core AI categories
                "AI/ML",
                "Deep Learning",
                "Architecture",
                "Software Engineering",
                # Shared core categories
                "Python Core",
                "Python Libraries",
                "Fundamentals",
                # Infrastructure & deployment
                "DevOps & Tooling",
                "Cloud",
                "ML Ops",
            ],
            "priority_topics": [
                # AI/LLM specific
                "generative-ai",
                "ai-agents",
                "prompt-engineering",
                "langchain",
                "claude-code",
                # Software engineering
                "api-development",
                "system-architecture",
                "pydantic",
                "fastapi",
                # DevOps & cloud
                "docker",
                "kubernetes",
                "aws",
                "git",
            ],
        },
    }

    # Role thresholds
    ROLE_THRESHOLDS = {
        "entry": {
            "accuracy": 70.0,
            "difficulties": ["beginner", "intermediate"],
            "min_sessions_per_category": 3,
        },
        "senior": {
            "accuracy": 80.0,
            "difficulties": ["beginner", "intermediate", "advanced"],
            "min_sessions_per_category": 5,
        },
        "principal": {
            "accuracy": 90.0,
            "difficulties": ["beginner", "intermediate", "advanced"],
            "min_sessions_per_category": 8,
        },
    }

    ASSESSMENT_PERIOD_DAYS = 30

    def __init__(self) -> None:
        """Initialize the readiness calculator service."""
        self.logger = logging.getLogger(__name__)

    def calculate_readiness(
        self,
        user: "User",
        role_level: RoleLevelType = "entry",
    ) -> ReadinessAssessment:
        """
        Calculate complete readiness assessment for a user.

        Args:
            user: The user to assess.
            role_level: Target interview role level.

        Returns:
            Complete ReadinessAssessment with scores and recommendations.
        """
        # Calculate assessment period
        today = timezone.now().date()
        period_start = today - timedelta(days=self.ASSESSMENT_PERIOD_DAYS)
        period_end = today

        # Get sessions from period
        sessions_by_mode = self._get_period_sessions(user, period_start, period_end)

        # Calculate mode performances
        mode_performances = {}
        for mode_name in ["exam", "lightning", "coding", "argument"]:
            mode_performances[mode_name] = self._calculate_mode_performance(
                mode_name,
                sessions_by_mode.get(mode_name, []),
                role_level,
            )

        # Calculate overall weighted score
        overall_score = self._calculate_weighted_overall_score(mode_performances)

        # Get category readiness
        category_readiness = self._calculate_category_readiness(
            user,
            sessions_by_mode,
            role_level,
        )

        # Count required categories met
        required_met = sum(
            1 for cat in category_readiness.values() if cat.required and cat.is_covered
        )
        required_total = sum(1 for cat in category_readiness.values() if cat.required)

        # Get difficulty readiness
        difficulty_readiness = self._calculate_difficulty_readiness(
            sessions_by_mode,
            role_level,
        )

        # Determine overall readiness
        threshold = self.ROLE_THRESHOLDS[role_level]["accuracy"]
        is_ready = self._determine_readiness(
            overall_score,
            category_readiness,
            difficulty_readiness,
            role_level,
        )

        # Calculate activity summary
        total_sessions = sum(perf.sessions_count for perf in mode_performances.values())
        total_questions = sum(
            perf.total_attempted for perf in mode_performances.values()
        )

        # Count unique study days
        study_days = self._count_study_days(sessions_by_mode, period_start, period_end)

        return ReadinessAssessment(
            user_id=user.id,
            role_level=role_level,
            assessment_date=today,
            period_start=period_start,
            period_end=period_end,
            overall_score=overall_score,
            is_ready=is_ready,
            threshold=threshold,
            mode_performances=mode_performances,
            category_readiness=category_readiness,
            required_categories_met=required_met,
            required_categories_total=required_total,
            difficulty_readiness=difficulty_readiness,
            total_sessions=total_sessions,
            total_questions=total_questions,
            study_days=study_days,
        )

    def _get_period_sessions(
        self,
        user: "User",
        start_date: date,
        end_date: date,
    ) -> dict[str, list]:
        """Get all completed sessions in the assessment period by mode."""
        from apps.argument.models import ArgumentSession
        from apps.coding.models import CodingSession
        from apps.exam.models import ExamSession
        from apps.lightning.models import LightningSession

        sessions = {}

        # Exam sessions
        sessions["exam"] = list(
            ExamSession.objects.filter(
                user=user,
                status=ExamSession.Status.COMPLETED,
                completed_at__date__gte=start_date,
                completed_at__date__lte=end_date,
            ).select_related("subject")
        )

        # Lightning sessions
        sessions["lightning"] = list(
            LightningSession.objects.filter(
                user=user,
                status__in=[
                    LightningSession.Status.COMPLETED,
                    LightningSession.Status.TIMED_OUT,
                ],
                completed_at__date__gte=start_date,
                completed_at__date__lte=end_date,
            ).select_related("subject")
        )

        # Coding sessions
        sessions["coding"] = list(
            CodingSession.objects.filter(
                user=user,
                status=CodingSession.Status.COMPLETED,
                completed_at__date__gte=start_date,
                completed_at__date__lte=end_date,
            )
            .select_related("subject")
            .prefetch_related("responses")
        )

        # Argument sessions
        sessions["argument"] = list(
            ArgumentSession.objects.filter(
                user=user,
                status=ArgumentSession.Status.COMPLETED,
                completed_at__date__gte=start_date,
                completed_at__date__lte=end_date,
            ).select_related("subject", "analysis")
        )

        return sessions

    def _calculate_mode_performance(
        self,
        mode: str,
        sessions: list,
        role_level: RoleLevelType,
    ) -> ModePerformance:
        """Calculate performance metrics for a single mode."""
        if mode == "exam":
            return self._calculate_exam_performance(sessions)
        elif mode == "lightning":
            return self._calculate_lightning_performance(sessions)
        elif mode == "coding":
            return self._calculate_coding_performance(sessions)
        elif mode == "argument":
            return self._calculate_argument_performance(sessions)
        else:
            return ModePerformance(
                mode_name=mode,
                sessions_count=0,
                total_correct=0,
                total_attempted=0,
                accuracy=0.0,
                weighted_score=0.0,
            )

    def _calculate_exam_performance(self, sessions: list) -> ModePerformance:
        """Calculate exam mode performance."""
        if not sessions:
            return ModePerformance(
                mode_name="exam",
                sessions_count=0,
                total_correct=0,
                total_attempted=0,
                accuracy=0.0,
                weighted_score=0.0,
            )

        total_correct = sum(s.score for s in sessions)
        total_attempted = sum(s.total_answered for s in sessions)
        accuracy = (total_correct / total_attempted * 100) if total_attempted > 0 else 0

        return ModePerformance(
            mode_name="exam",
            sessions_count=len(sessions),
            total_correct=total_correct,
            total_attempted=total_attempted,
            accuracy=round(accuracy, 1),
            weighted_score=0.0,  # Set later during weighted calculation
        )

    def _calculate_lightning_performance(self, sessions: list) -> ModePerformance:
        """Calculate lightning mode performance."""
        if not sessions:
            return ModePerformance(
                mode_name="lightning",
                sessions_count=0,
                total_correct=0,
                total_attempted=0,
                accuracy=0.0,
                weighted_score=0.0,
            )

        total_correct = sum(s.questions_correct for s in sessions)
        total_attempted = sum(s.questions_answered for s in sessions)
        accuracy = (total_correct / total_attempted * 100) if total_attempted > 0 else 0

        return ModePerformance(
            mode_name="lightning",
            sessions_count=len(sessions),
            total_correct=total_correct,
            total_attempted=total_attempted,
            accuracy=round(accuracy, 1),
            weighted_score=0.0,
        )

    def _calculate_coding_performance(self, sessions: list) -> ModePerformance:
        """
        Calculate coding mode performance.

        Uses average of 4 scores: correctness, style, completeness, efficiency.
        """
        if not sessions:
            return ModePerformance(
                mode_name="coding",
                sessions_count=0,
                total_correct=0,
                total_attempted=0,
                accuracy=0.0,
                weighted_score=0.0,
            )

        total_score = 0.0
        evaluated_count = 0

        for session in sessions:
            # Get the latest response for each session
            latest_response = session.responses.order_by("-submission_number").first()
            if latest_response and latest_response.overall_score is not None:
                total_score += latest_response.overall_score
                evaluated_count += 1

        accuracy = (total_score / evaluated_count) if evaluated_count > 0 else 0

        return ModePerformance(
            mode_name="coding",
            sessions_count=len(sessions),
            total_correct=int(total_score / 100 * evaluated_count)
            if evaluated_count
            else 0,
            total_attempted=evaluated_count,
            accuracy=round(accuracy, 1),
            weighted_score=0.0,
        )

    def _calculate_argument_performance(self, sessions: list) -> ModePerformance:
        """
        Calculate argument mode performance.

        Uses average of 3 scores: technical, temperament, focus (scale 1-10 -> 0-100).
        """
        if not sessions:
            return ModePerformance(
                mode_name="argument",
                sessions_count=0,
                total_correct=0,
                total_attempted=0,
                accuracy=0.0,
                weighted_score=0.0,
            )

        total_score = 0.0
        scored_count = 0

        for session in sessions:
            if hasattr(session, "analysis") and session.analysis:
                # Average of three scores (1-10 scale), convert to 0-100
                avg_score = session.analysis.average_score * 10
                total_score += avg_score
                scored_count += 1

        accuracy = (total_score / scored_count) if scored_count > 0 else 0

        return ModePerformance(
            mode_name="argument",
            sessions_count=len(sessions),
            total_correct=int(total_score / 100 * scored_count) if scored_count else 0,
            total_attempted=scored_count,
            accuracy=round(accuracy, 1),
            weighted_score=0.0,
        )

    def _calculate_weighted_overall_score(
        self,
        mode_performances: dict[str, ModePerformance],
    ) -> float:
        """
        Calculate weighted readiness score.

        Algorithm:
        1. Start with base weights: Coding 40%, Exam 25%, Argument 20%, Lightning 15%
        2. Only include modes where user has activity
        3. Redistribute weights proportionally among active modes
        4. Calculate: sum(mode_accuracy * adjusted_weight)
        """
        active_modes = {
            mode: perf
            for mode, perf in mode_performances.items()
            if perf.sessions_count > 0
        }

        if not active_modes:
            return 0.0

        # Calculate total weight of active modes
        total_active_weight = sum(self.MODE_WEIGHTS[mode] for mode in active_modes)

        # Calculate weighted score
        weighted_sum = 0.0
        for mode, perf in active_modes.items():
            adjusted_weight = self.MODE_WEIGHTS[mode] / total_active_weight
            perf.weighted_score = perf.accuracy * adjusted_weight
            weighted_sum += perf.weighted_score

        return round(weighted_sum, 1)

    def _calculate_category_readiness(
        self,
        user: "User",
        sessions_by_mode: dict[str, list],
        role_level: RoleLevelType,
    ) -> dict[str, CategoryReadiness]:
        """Calculate readiness for each category."""
        from apps.subjects.models import Subject

        # Get all subjects grouped by category
        subjects = Subject.objects.filter(is_active=True).values(
            "slug", "name", "category"
        )
        category_subjects = {}
        for subject in subjects:
            cat = subject["category"]
            if cat not in category_subjects:
                category_subjects[cat] = []
            category_subjects[cat].append(subject["slug"])

        # Count sessions per subject
        subject_sessions: dict[str, int] = {}
        subject_scores: dict[str, list[float]] = {}

        for mode, sessions in sessions_by_mode.items():
            for session in sessions:
                slug = session.subject.slug
                if slug not in subject_sessions:
                    subject_sessions[slug] = 0
                    subject_scores[slug] = []
                subject_sessions[slug] += 1

                # Get accuracy for this session
                if mode == "exam":
                    if session.total_answered > 0:
                        subject_scores[slug].append(session.score_percentage)
                elif mode == "lightning":
                    if session.questions_answered > 0:
                        subject_scores[slug].append(session.accuracy_percentage)
                elif mode == "coding":
                    latest = session.responses.order_by("-submission_number").first()
                    if latest and latest.overall_score is not None:
                        subject_scores[slug].append(latest.overall_score)
                elif mode == "argument":
                    if hasattr(session, "analysis") and session.analysis:
                        subject_scores[slug].append(session.analysis.average_score * 10)

        # Build category readiness
        min_sessions = self.ROLE_THRESHOLDS[role_level]["min_sessions_per_category"]
        threshold = self.ROLE_THRESHOLDS[role_level]["accuracy"]
        result = {}

        for category, subject_slugs in category_subjects.items():
            is_required = category in self.REQUIRED_CATEGORIES
            subjects_attempted = [s for s in subject_slugs if s in subject_sessions]

            # Calculate average score across all subjects in category
            all_scores = []
            for slug in subjects_attempted:
                all_scores.extend(subject_scores.get(slug, []))

            avg_score = sum(all_scores) / len(all_scores) if all_scores else 0.0

            # Determine coverage
            total_sessions = sum(subject_sessions.get(s, 0) for s in subject_slugs)
            is_covered = (
                len(subjects_attempted) > 0
                and total_sessions >= min_sessions
                and avg_score >= threshold
            )

            # Find gap subjects (not attempted or low score)
            gap_subjects = []
            for slug in subject_slugs:
                if slug not in subject_sessions:
                    gap_subjects.append(slug)
                elif (
                    subject_scores.get(slug)
                    and sum(subject_scores[slug]) / len(subject_scores[slug])
                    < threshold
                ):
                    gap_subjects.append(slug)

            result[category] = CategoryReadiness(
                category_name=category,
                required=is_required,
                subjects_in_category=subject_slugs,
                subjects_attempted=subjects_attempted,
                subjects_required=min_sessions,
                score=round(avg_score, 1),
                is_covered=is_covered,
                gap_subjects=gap_subjects[:3],  # Top 3 gap subjects
            )

        return result

    def _calculate_difficulty_readiness(
        self,
        sessions_by_mode: dict[str, list],
        role_level: RoleLevelType,
    ) -> dict[str, DifficultyReadiness]:
        """Calculate performance by difficulty level."""
        from apps.exam.models import ExamAnswer
        from apps.lightning.models import LightningAnswer

        difficulty_stats: dict[str, dict] = {
            "beginner": {"correct": 0, "total": 0},
            "intermediate": {"correct": 0, "total": 0},
            "advanced": {"correct": 0, "total": 0},
        }

        # Aggregate from exam sessions
        for session in sessions_by_mode.get("exam", []):
            answers = ExamAnswer.objects.filter(session=session).select_related(
                "question"
            )
            for answer in answers:
                if answer.is_correct is not None:
                    diff = answer.question.difficulty
                    if diff in difficulty_stats:
                        difficulty_stats[diff]["total"] += 1
                        if answer.is_correct:
                            difficulty_stats[diff]["correct"] += 1

        # Aggregate from lightning sessions
        for session in sessions_by_mode.get("lightning", []):
            answers = LightningAnswer.objects.filter(session=session).select_related(
                "question"
            )
            for answer in answers:
                diff = answer.question.difficulty
                if diff in difficulty_stats:
                    difficulty_stats[diff]["total"] += 1
                    if answer.is_correct:
                        difficulty_stats[diff]["correct"] += 1

        # Build result
        threshold = self.ROLE_THRESHOLDS[role_level]["accuracy"]
        required_difficulties = self.ROLE_THRESHOLDS[role_level]["difficulties"]
        result = {}

        for diff, stats in difficulty_stats.items():
            accuracy = (
                (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0
            )
            meets = (
                diff in required_difficulties
                and stats["total"] >= 5  # Minimum questions to evaluate
                and accuracy >= threshold
            ) or diff not in required_difficulties

            result[diff] = DifficultyReadiness(
                difficulty=diff,
                correct=stats["correct"],
                total=stats["total"],
                accuracy=round(accuracy, 1),
                meets_threshold=meets,
                required_threshold=threshold if diff in required_difficulties else 0,
            )

        return result

    def _determine_readiness(
        self,
        overall_score: float,
        category_readiness: dict[str, CategoryReadiness],
        difficulty_readiness: dict[str, DifficultyReadiness],
        role_level: RoleLevelType,
    ) -> bool:
        """
        Determine if user is interview-ready.

        Requirements:
        1. Overall score >= role threshold
        2. All required categories covered (min sessions + accuracy)
        3. Required difficulty levels met (entry: beg+int, senior+: all)
        """
        threshold = self.ROLE_THRESHOLDS[role_level]["accuracy"]

        # Check overall score
        if overall_score < threshold:
            return False

        # Check required categories
        for cat in category_readiness.values():
            if cat.required and not cat.is_covered:
                return False

        # Check difficulty requirements
        required_diffs = self.ROLE_THRESHOLDS[role_level]["difficulties"]
        for diff in required_diffs:
            if (
                diff in difficulty_readiness
                and not difficulty_readiness[diff].meets_threshold
            ):
                return False

        return True

    def _count_study_days(
        self,
        sessions_by_mode: dict[str, list],
        start_date: date,
        end_date: date,
    ) -> int:
        """Count unique days with study activity."""
        study_dates = set()

        for sessions in sessions_by_mode.values():
            for session in sessions:
                if hasattr(session, "completed_at") and session.completed_at:
                    study_dates.add(session.completed_at.date())
                elif hasattr(session, "started_at"):
                    study_dates.add(session.started_at.date())

        return len(study_dates)


# Singleton instance
_readiness_service: ReadinessCalculatorService | None = None


def get_readiness_service() -> ReadinessCalculatorService:
    """Get the singleton readiness service instance."""
    global _readiness_service
    if _readiness_service is None:
        _readiness_service = ReadinessCalculatorService()
    return _readiness_service
