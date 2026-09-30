"""Rubric calibration: grade known submissions and compare against human judgment.

The workspace rubric decides a letter from four dimension scores, three of which are
model judgment. Nothing in the test suite can tell you whether those judgments match
a human's -- only a human can. This package exists to make that comparison cheap
enough to actually do.

The method is blind grading of *synthetic but realistic* submissions. Each exercise
gets a small set of personas -- deliberately different quality tiers, derived from the
"Watch for" list in the exercise's own ``grading_notes`` -- which are applied to a real
scaffolded workspace and graded by the real pipeline: real containers, real acceptance
checks, real model call. The human then grades the same evidence the model saw, with
the system's verdict withheld, and :mod:`~apps.workspace.calibration.report` shows
where the two disagree.

Why synthetic rather than the user's own attempts: a person grading their own work
knows what they meant, which is exactly the bias that would hide a documentation
miscalibration. Personas also let the set span tiers on purpose, so the question
becomes "does the rubric *discriminate* the way a human does" rather than "did it
happen to like this one submission".
"""
