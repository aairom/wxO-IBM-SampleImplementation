# IBM Bob Skills

Source: https://bob.ibm.com/docs/ide/features/skills

## What are Skills?

Skills are **reusable instruction sets** that teach Bob new workflows and specialized tasks. Think of them as recipes that Bob follows to complete specific types of work in a consistent, repeatable manner.

## How Skills Work

When you activate a skill, Bob receives the skill's instructions and gains access to any supporting files in the skill directory. Bob then follows these instructions to complete your task according to the defined workflow.

Skills load **once per conversation** to avoid duplicate prompts. Bob automatically determines when to activate a skill based on your request and the skill's description.

## Creating a Skill

### Basic Setup

1. Create a folder inside `.bob/skills/` in your project root, or use `~/.bob/skills/` for global skills.
2. Add a `SKILL.md` file inside that folder.

**Example structure:**
```
your-project/
└── .bob/
    └── skills/
        └── code-review/
            └── SKILL.md
```

### SKILL.md Format

The `SKILL.md` file uses YAML front matter followed by the skill instructions:

```markdown
---
name: code-review
description: Review code for bugs, security issues, and best practices
---

When reviewing code, check for:
- Security vulnerabilities
- Performance issues
- Missing error handling at API boundaries
- Unused imports and dead code

Provide a summary with severity levels for each finding.
```

**Required fields:**
- `name` — The skill's display name used in the Bob interface.
- `description` — A clear summary that helps Bob decide when to activate this skill. Skills without descriptions are ignored.

**Instructions section:** Everything below the `---` delimiter becomes the instructions Bob receives when the skill is activated.

## Adding Supporting Files

You can include additional files and subfolders alongside `SKILL.md` to provide reference materials, templates, checklists, scripts, or other resources. Bob can read these files automatically once the skill is activated.

**Example with supporting files:**
```
.bob/skills/
└── code-review/
    ├── SKILL.md
    ├── checklist.md
    ├── severity-guide.md
    └── scripts/
        ├── analyze.sh
        └── report-generator.py
```

Supporting files can include:
- Checklists and templates
- Reference documentation
- Configuration examples
- Scripts and utilities in subfolders
- Style guides

## Skill Locations

Skills can be defined at two levels:

- `<project>/.bob/skills/` — Project-specific; used for workflows unique to this project.
- `~/.bob/skills/` — Global; used for personal or organization-wide workflows.

**Priority:** If both locations contain a skill with the same name, the project-level skill takes precedence.

## Approving Skills

By default, Bob asks for your permission before activating a skill.

To skip the approval prompt:
1. Open Bob Settings.
2. Navigate to the Auto-Approve section.
3. Turn on the toggle for **Skills**.

With this setting enabled, Bob automatically activates skills when appropriate without requesting permission.
