"""Tests for the argument app."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.argument.models import ArgumentAnalysis, ArgumentMessage, ArgumentSession
from apps.subjects.models import Subject

User = get_user_model()


class ArgumentSessionModelTest(TestCase):
    """Tests for the ArgumentSession model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
        )
        self.subject = Subject.objects.create(
            name="Python",
            slug="python",
            category="Programming",
        )
        self.session = ArgumentSession.objects.create(
            user=self.user,
            subject=self.subject,
            difficulty="intermediate",
            heat_level=ArgumentSession.HeatLevel.COLLEAGUE,
            initial_prompt="Should Python use tabs or spaces?",
        )

    def test_session_str(self):
        """Test string representation of session."""
        self.assertIn(self.user.username, str(self.session))
        self.assertIn(self.subject.name, str(self.session))

    def test_session_get_absolute_url(self):
        """Test get_absolute_url returns correct URL."""
        url = self.session.get_absolute_url()
        self.assertIn(self.subject.slug, url)
        self.assertIn(str(self.session.pk), url)

    def test_session_default_status(self):
        """Test default status is IN_PROGRESS."""
        self.assertEqual(self.session.status, ArgumentSession.Status.IN_PROGRESS)

    def test_get_conversation_history_empty(self):
        """Test conversation history for session with no messages."""
        history = self.session.get_conversation_history()
        self.assertEqual(history, [])

    def test_get_conversation_history_with_messages(self):
        """Test conversation history includes messages in order."""
        ArgumentMessage.objects.create(
            session=self.session,
            role=ArgumentMessage.Role.USER,
            content="I think spaces are better.",
        )
        ArgumentMessage.objects.create(
            session=self.session,
            role=ArgumentMessage.Role.OPPONENT,
            content="Tabs are more efficient.",
        )

        history = self.session.get_conversation_history()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["role"], "assistant")


class ArgumentMessageModelTest(TestCase):
    """Tests for the ArgumentMessage model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
        )
        self.subject = Subject.objects.create(
            name="Python",
            slug="python",
            category="Programming",
        )
        self.session = ArgumentSession.objects.create(
            user=self.user,
            subject=self.subject,
            difficulty="intermediate",
            heat_level=ArgumentSession.HeatLevel.COLLEAGUE,
            initial_prompt="Test prompt",
        )

    def test_message_str(self):
        """Test string representation of message."""
        message = ArgumentMessage.objects.create(
            session=self.session,
            role=ArgumentMessage.Role.USER,
            content="This is my argument.",
        )
        self.assertIn("User", str(message))

    def test_message_ordering(self):
        """Test messages are ordered by created_at."""
        msg1 = ArgumentMessage.objects.create(
            session=self.session,
            role=ArgumentMessage.Role.USER,
            content="First message",
        )
        msg2 = ArgumentMessage.objects.create(
            session=self.session,
            role=ArgumentMessage.Role.OPPONENT,
            content="Second message",
        )

        messages = list(self.session.messages.all())
        self.assertEqual(messages[0], msg1)
        self.assertEqual(messages[1], msg2)


class ArgumentAnalysisModelTest(TestCase):
    """Tests for the ArgumentAnalysis model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
        )
        self.subject = Subject.objects.create(
            name="Python",
            slug="python",
            category="Programming",
        )
        self.session = ArgumentSession.objects.create(
            user=self.user,
            subject=self.subject,
            difficulty="intermediate",
            heat_level=ArgumentSession.HeatLevel.COLLEAGUE,
            initial_prompt="Test prompt",
            status=ArgumentSession.Status.COMPLETED,
        )
        self.analysis = ArgumentAnalysis.objects.create(
            session=self.session,
            technical_score=8,
            temperament_score=7,
            focus_score=9,
            technical_feedback="Good technical knowledge.",
            temperament_feedback="Stayed calm.",
            focus_feedback="On topic.",
            overall_feedback="Well done!",
        )

    def test_average_score(self):
        """Test average score calculation."""
        expected = round((8 + 7 + 9) / 3, 1)
        self.assertEqual(self.analysis.average_score, expected)

    def test_analysis_str(self):
        """Test string representation of analysis."""
        self.assertIn("Tech: 8/10", str(self.analysis))


class ArgumentViewsTest(TestCase):
    """Tests for argument views."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
        )
        self.subject = Subject.objects.create(
            name="Python",
            slug="python",
            category="Programming",
            is_active=True,
        )

    def test_config_view_requires_login(self):
        """Test config view requires authentication."""
        url = reverse("argument:config", kwargs={"subject_slug": self.subject.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_config_view_authenticated(self):
        """Test config view for authenticated user."""
        self.client.login(username="testuser", password="testpass123")
        url = reverse("argument:config", kwargs={"subject_slug": self.subject.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Argument Mode")

    def test_session_view_requires_ownership(self):
        """Test session view only accessible by owner."""
        other_user = User.objects.create_user(
            username="otheruser",
            password="otherpass123",
        )
        session = ArgumentSession.objects.create(
            user=other_user,
            subject=self.subject,
            difficulty="intermediate",
            heat_level=ArgumentSession.HeatLevel.COLLEAGUE,
            initial_prompt="Test prompt",
        )

        self.client.login(username="testuser", password="testpass123")
        url = reverse(
            "argument:session",
            kwargs={"subject_slug": self.subject.slug, "pk": session.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
