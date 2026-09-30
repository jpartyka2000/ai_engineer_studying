# Rubric calibration

The workspace grading rubric turns four dimension scores into a letter. Three of those
four are model judgment, and no test can tell you whether they match a human's — only a
human can. This directory is where that comparison happens.

## What is here

| path | what it is |
|---|---|
| `packets/` | One blind grading packet per submission. Regenerable; gitignored. |
| `scoresheet.md` | **Your input.** One block per item; fill in `letter:` at minimum. |
| `answer-key.json` | Item id → persona and the system's verdict. **Do not open until you have finished the scoresheet.** Gitignored. |
| `grades.json` | Every round ever recorded. Committed — these letters cannot be regenerated, and they are the regression corpus. |

## How to run a round

```bash
# 1. Build: scaffold a real workspace per persona, replay it, grade it for real.
#    Slow, and one Claude call each.
python manage.py calibrate_workspace build              # all personas
python manage.py calibrate_workspace build --exercise ex-005

# 2. Render blind packets and a fresh scoresheet.
python manage.py calibrate_workspace packet

# 3. Grade by hand. Read a packet, write a letter in scoresheet.md. Repeat.

# 4. Reveal and compare.
python manage.py calibrate_workspace report --save

# At any point: what is built, what is graded, what is outstanding.
python manage.py calibrate_workspace status
```

## What you are grading

Each packet is the **verbatim prompt the grader was sent** — same brief, same definition
of done, same private grading notes, same acceptance check results, same diff, same
truncation. Nothing is summarised, so a disagreement can only come from judgment rather
than from you and the model having read different things.

What the packet does not contain is the system's verdict, the persona's label, or its
quality tier. Item ids are hashes, so reading order tells you nothing either.

Grade it as you would a colleague's pull request. Weights are correctness 40,
engineering 25, documentation 25, completeness 10; the anchors in the evaluator prompt
are 70 = competent junior, 85 = solid mid-level, 95+ = what a staff engineer ships.

The dimension scores on the scoresheet are optional. Do them on at least a few: a letter
tells you *that* the rubric disagrees, the dimensions tell you *which* one is
miscalibrated — which is the part you would actually change.

## What the report tells you, and what to do about it

Three findings, in descending order of how much they should worry you:

1. **Collapsed pairs** — you separated two submissions clearly, the rubric gave them the
   same letter. The rubric has no opinion where you had one.
2. **Inversions** — the rubric ranked a pair backwards. No amount of shifting anchors
   fixes this; it is a judgment problem in the evaluator prompt.
3. **Letter offsets** — a consistent bias in one direction is a calibration-anchor
   problem. Raise or lower the 70/85/95 anchors in
   `apps/workspace/services/exercise_evaluator.py::SYSTEM_PROMPT`.

The report also separates a dimension that is *biased* (consistently off, so move its
guidance) from one that is *noisy* (off in both directions, so its definition is
ambiguous). Those want different fixes and a signed average hides the second.

**Do not fix a disagreement by editing the gates or the letter cutoffs.** The gates are
mechanical and unambiguous; the cutoffs are the standard 13-point scale and only mean
something if they mean the same thing every time. Change the prompt.

## The personas

Each exercise has three, defined in
`apps/workspace/calibration/personas_tenantsaas.py` and derived from the "Watch for"
list in that exercise's own `grading_notes`:

- **root-cause** — the reference fix, cleanly committed, with a real writeup. The upper
  anchor.
- **silent** — byte-for-byte the same code, one terse commit, NOTES.md untouched. The
  gap between this and root-cause *is* the rubric's price for not explaining your work.
- **a third tier that stresses judgment** — a symptom patch, a green-but-wrong fix, a
  defensible-but-worse approach, or honest partial work. These are the ones worth your
  time: they are where the acceptance checks cannot help and only judgment decides.

Each persona records the letter its author predicted, withheld until the reveal. It is a
third opinion for context, not the ground truth. **You are the ground truth.**
