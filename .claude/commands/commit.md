---
description: Analyze git changes and craft a conventional commit message following Clogem's git conventions
---

You need to help craft a git commit message following Clogem's git conventions.

Use the `git-commit-helper` agent to:
1. Analyze the current git changes (staged and unstaged)
2. Determine the appropriate commit type and scope
3. Generate a conventional commit message with GitHub issue reference
4. Recommend whether to commit directly to main or use a feature branch

The git-commit-helper agent will examine `git status` and `git diff` to understand what has changed, then provide a properly formatted commit message that follows the conventional commits format defined in the project's CLAUDE.md.
