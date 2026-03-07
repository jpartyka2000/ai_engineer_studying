# Planned Features

## Q&A Response-to-Topic Feature

**Status:** Not started

### Description

Add a feature to Q&A mode where each LLM response has a clickable UI option. When clicked, it triggers:

1. **File Creation**: A new file (appropriately named) is inserted into the topic directory within `llm_studying/` for that topic

2. **Question Generation**: Creates 3 new questions for this new topic

### Requirements

- Add clickable UI element on each LLM response in Q&A sessions
- Backend endpoint to handle the click action
- File system operations to create topic files in `llm_studying/<topic>/`
- Integration with question generation to create 3 questions for the new topic
- Appropriate naming convention for generated files

### Questions to Clarify

- What should the file contain? (The LLM response text? A summary? Formatted notes?)
- What format should the file be? (Markdown, JSON, plain text?)
- How should the filename be generated? (From topic keywords? Timestamp? User input?)
- Should the 3 questions be multiple choice, free text, or mixed?
- Where should the questions be stored? (Database via Question model? JSON fixture?)

### Files to Explore

- `apps/qanda/` - Existing Q&A implementation
- `apps/questions/` - Question models and generation
- `llm_studying/` - Directory structure for topic files
- `templates/qanda/` - Q&A templates for UI modifications
