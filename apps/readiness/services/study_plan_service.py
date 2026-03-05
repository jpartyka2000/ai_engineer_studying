"""
Study plan generator service for interview readiness recommendations.

Generates personalized study recommendations based on readiness gaps.
"""

import logging
from dataclasses import dataclass, field

from apps.readiness.services.readiness_service import (
    ReadinessAssessment,
    ReadinessCalculatorService,
    StudyRecommendation,
)

logger = logging.getLogger(__name__)


@dataclass
class TrackRecommendations:
    """Recommendations for a specific engineering track."""

    track_id: str
    track_name: str
    track_description: str
    recommendations: list[StudyRecommendation] = field(default_factory=list)
    coverage_score: float = 0.0
    categories_covered: int = 0
    categories_total: int = 0


class StudyPlanGeneratorService:
    """
    Generates personalized study recommendations based on readiness gaps.
    """

    def __init__(self) -> None:
        """Initialize the study plan generator service."""
        self.logger = logging.getLogger(__name__)
        self.role_thresholds = ReadinessCalculatorService.ROLE_THRESHOLDS
        self.engineering_tracks = ReadinessCalculatorService.ENGINEERING_TRACKS
        self._subject_cache: dict[str, dict] = {}

    def _get_subject_info(self, slug: str) -> dict | None:
        """Get subject info (name, category) from cache or database."""
        if slug in self._subject_cache:
            return self._subject_cache[slug]

        from apps.subjects.models import Subject

        try:
            subject = Subject.objects.get(slug=slug, is_active=True)
            info = {"name": subject.name, "category": subject.category, "slug": slug}
            self._subject_cache[slug] = info
            return info
        except Subject.DoesNotExist:
            return None

    def _get_subjects_by_category(self, category: str) -> list[dict]:
        """Get all subjects in a category."""
        from apps.subjects.models import Subject

        subjects = Subject.objects.filter(category=category, is_active=True).values(
            "slug", "name", "category"
        )
        return list(subjects)

    def _get_all_subjects(self) -> dict[str, dict]:
        """Get all active subjects indexed by slug."""
        from apps.subjects.models import Subject

        subjects = Subject.objects.filter(is_active=True).values(
            "slug", "name", "category"
        )
        return {s["slug"]: s for s in subjects}

    def generate_track_recommendations(
        self,
        assessment: ReadinessAssessment,
        max_per_track: int = 5,
    ) -> dict[str, TrackRecommendations]:
        """
        Generate recommendations for each engineering track (ML and AI).

        Args:
            assessment: The readiness assessment.
            max_per_track: Maximum recommendations per track.

        Returns:
            Dict mapping track_id to TrackRecommendations.
        """
        # Clear subject cache for fresh data
        self._subject_cache = {}
        all_subjects = self._get_all_subjects()

        result = {}

        for track_id, track_config in self.engineering_tracks.items():
            track_recs = self._generate_track_specific_recommendations(
                assessment=assessment,
                track_id=track_id,
                track_config=track_config,
                all_subjects=all_subjects,
                max_recommendations=max_per_track,
            )
            result[track_id] = track_recs

        return result

    def _generate_track_specific_recommendations(
        self,
        assessment: ReadinessAssessment,
        track_id: str,
        track_config: dict,
        all_subjects: dict[str, dict],
        max_recommendations: int,
    ) -> TrackRecommendations:
        """Generate recommendations for a specific engineering track."""
        recommendations = []
        threshold = self.role_thresholds[assessment.role_level]["accuracy"]

        track_categories = track_config["categories"]
        priority_topics = track_config.get("priority_topics", [])

        # Track coverage calculation
        categories_covered = 0
        categories_total = len(track_categories)
        total_score = 0.0
        scored_categories = 0

        # Find gaps in track-specific categories
        for cat_name in track_categories:
            cat_ready = assessment.category_readiness.get(cat_name)

            if cat_ready:
                if cat_ready.score > 0:
                    total_score += cat_ready.score
                    scored_categories += 1
                if cat_ready.is_covered:
                    categories_covered += 1

                # Generate recommendations for uncovered/weak categories
                if not cat_ready.is_covered:
                    # Get subjects in this category
                    subjects_in_cat = [
                        s for s in all_subjects.values() if s["category"] == cat_name
                    ]

                    # Prioritize subjects from priority_topics list
                    prioritized = []
                    other = []
                    for subj in subjects_in_cat:
                        if subj["slug"] in priority_topics:
                            prioritized.append(subj)
                        else:
                            other.append(subj)

                    # Sort prioritized by their position in priority_topics
                    prioritized.sort(
                        key=lambda s: (
                            priority_topics.index(s["slug"])
                            if s["slug"] in priority_topics
                            else 999
                        )
                    )

                    gap_subjects = prioritized + other

                    for subj in gap_subjects[:2]:  # Top 2 subjects per category
                        is_attempted = subj["slug"] in cat_ready.subjects_attempted
                        is_priority = subj["slug"] in priority_topics

                        if not is_attempted:
                            recommendations.append(
                                StudyRecommendation(
                                    priority=1 if is_priority else 2,
                                    recommendation_type="uncovered_topic",
                                    category=cat_name,
                                    topic_name=subj["name"],
                                    title=subj["name"],
                                    description=(
                                        f"Essential for {track_config['name']}. "
                                        f"Start learning {subj['name']} fundamentals."
                                    ),
                                    action_url=f"/subject/{subj['slug']}/",
                                    subject_slug=subj["slug"],
                                    mode="exam",
                                    difficulty="beginner",
                                    estimated_sessions=3,
                                )
                            )
                        elif cat_ready.score < threshold:
                            recommendations.append(
                                StudyRecommendation(
                                    priority=2 if is_priority else 3,
                                    recommendation_type="weak_topic",
                                    category=cat_name,
                                    topic_name=subj["name"],
                                    title=subj["name"],
                                    description=(
                                        f"Improve your {subj['name']} skills. "
                                        f"Target {threshold:.0f}% accuracy."
                                    ),
                                    action_url=f"/subject/{subj['slug']}/",
                                    subject_slug=subj["slug"],
                                    mode="exam",
                                    difficulty="intermediate",
                                    estimated_sessions=4,
                                )
                            )
            else:
                # Category not in assessment (no subjects attempted)
                subjects_in_cat = [
                    s for s in all_subjects.values() if s["category"] == cat_name
                ]

                # Prioritize by priority_topics
                for subj in subjects_in_cat:
                    is_priority = subj["slug"] in priority_topics
                    if is_priority or len(recommendations) < max_recommendations:
                        recommendations.append(
                            StudyRecommendation(
                                priority=1 if is_priority else 3,
                                recommendation_type="uncovered_topic",
                                category=cat_name,
                                topic_name=subj["name"],
                                title=subj["name"],
                                description=(
                                    f"Key topic for {track_config['name']}. "
                                    f"No sessions yet - start here!"
                                ),
                                action_url=f"/subject/{subj['slug']}/",
                                subject_slug=subj["slug"],
                                mode="exam",
                                difficulty="beginner",
                                estimated_sessions=3,
                            )
                        )
                        if is_priority:
                            break  # Only add one priority topic per missing category

        # Calculate coverage score
        coverage_score = (total_score / scored_categories) if scored_categories else 0.0

        # Sort by priority and deduplicate
        seen_slugs = set()
        unique_recs = []
        recommendations.sort(key=lambda r: (r.priority, r.category, r.topic_name))
        for rec in recommendations:
            if rec.subject_slug and rec.subject_slug not in seen_slugs:
                seen_slugs.add(rec.subject_slug)
                unique_recs.append(rec)
            elif not rec.subject_slug:
                unique_recs.append(rec)

        return TrackRecommendations(
            track_id=track_id,
            track_name=track_config["name"],
            track_description=track_config["description"],
            recommendations=unique_recs[:max_recommendations],
            coverage_score=round(coverage_score, 1),
            categories_covered=categories_covered,
            categories_total=categories_total,
        )

    def generate_recommendations(
        self,
        assessment: ReadinessAssessment,
        max_recommendations: int = 10,
    ) -> list[StudyRecommendation]:
        """
        Generate combined recommendations (legacy method for compatibility).

        Args:
            assessment: The readiness assessment to generate recommendations for.
            max_recommendations: Maximum number of recommendations to return.

        Returns:
            List of prioritized study recommendations.
        """
        track_recs = self.generate_track_recommendations(
            assessment, max_per_track=max_recommendations // 2
        )

        # Combine recommendations from both tracks
        all_recs = []
        for track in track_recs.values():
            all_recs.extend(track.recommendations)

        # Deduplicate by subject_slug
        seen_slugs = set()
        unique_recs = []
        for rec in sorted(all_recs, key=lambda r: r.priority):
            if rec.subject_slug and rec.subject_slug not in seen_slugs:
                seen_slugs.add(rec.subject_slug)
                unique_recs.append(rec)
            elif not rec.subject_slug:
                unique_recs.append(rec)

        return unique_recs[:max_recommendations]


# Singleton instance
_study_plan_service: StudyPlanGeneratorService | None = None


def get_study_plan_service() -> StudyPlanGeneratorService:
    """Get the singleton study plan service instance."""
    global _study_plan_service
    if _study_plan_service is None:
        _study_plan_service = StudyPlanGeneratorService()
    return _study_plan_service
