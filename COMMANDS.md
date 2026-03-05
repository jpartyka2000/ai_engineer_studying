# Management Commands Reference

Quick reference for common `python manage.py` commands.

---

## Question Management

### Generate Interview Questions
```bash
# Analyze coverage for a topic (see what's missing)
python manage.py generate_interview_questions git --analyze-only

# Show important interview topics for a subject
python manage.py generate_interview_questions git --show-topics

# Generate 10 questions to fill gaps
python manage.py generate_interview_questions git --num 10

# Generate until full interview coverage (LLM decides when done)
python manage.py generate_interview_questions git --complete

# Generate only advanced questions
python manage.py generate_interview_questions git --num 15 --difficulty advanced
```

### Export Questions (for Git version control)
```bash
# Export all subjects to questions/<subject>.json
python manage.py export_questions --all

# Export single subject
python manage.py export_questions git

# Export to SQL format
python manage.py export_questions git --format sql

# Custom output directory
python manage.py export_questions --all --output-dir backups/
```

### Import Questions
```bash
# Import all JSON files from questions/
python manage.py import_question_export --input-dir questions

# Import single file
python manage.py import_question_export questions/git.json

# Dry run (preview without changes)
python manage.py import_question_export questions/git.json --dry-run

# Update existing questions instead of skipping duplicates
python manage.py import_question_export questions/git.json --update-existing
```

### Import from Study Materials
```bash
# List available subjects in llm_studying/
python manage.py import_questions --list-subjects

# Import questions from study files for a subject
python manage.py import_questions --subject git --max-files 5 --questions-per-file 3

# Create subject records only (no question generation)
python manage.py import_questions --create-subjects-only
```

---

## Database & Migrations

```bash
# Create migrations after model changes
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Show migration plan
python manage.py migrate --plan
```

---

## Development

```bash
# Run development server
python manage.py runserver

# Create superuser for admin access
python manage.py createsuperuser

# Open Django shell
python manage.py shell

# Collect static files (for production)
python manage.py collectstatic
```

---

## Admin Interface

Access at: `http://127.0.0.1:8000/admin/`

### Quick Actions (from Subject list)
- **Analyze question coverage** - See covered/missing topics
- **Generate 10 interview questions** - Quick generation
- **Generate until full coverage** - LLM fills all gaps
- **Export questions to JSON** - Export to `questions/` directory

### Generate Questions Page
Click "Generate Questions" link on any subject for:
- Coverage analysis
- Interview topic breakdown
- Custom generation options

---

## Typical Workflows

### Adding a New Topic
```bash
# 1. Create the subject (via admin or import)
python manage.py import_questions --subject newtopic --create-subjects-only

# 2. Generate interview questions
python manage.py generate_interview_questions newtopic --complete

# 3. Export for version control
python manage.py export_questions newtopic
git add questions/newtopic.json
git commit -m "Add newtopic questions"
```

### Syncing Questions to Another Environment
```bash
# On source machine
python manage.py export_questions --all
git add questions/
git commit -m "Update question exports"
git push

# On target machine
git pull
python manage.py import_question_export --input-dir questions
```

### Filling Coverage Gaps
```bash
# Check what's missing
python manage.py generate_interview_questions python --analyze-only

# Fill the gaps
python manage.py generate_interview_questions python --complete

# Export updated questions
python manage.py export_questions python
```
