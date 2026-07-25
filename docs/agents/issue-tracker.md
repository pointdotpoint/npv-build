# Issue tracker: GitHub

Issues and PRDs for this repository live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- Create an issue with `gh issue create --title "..." --body "..."`.
- Read an issue with `gh issue view <number> --comments`.
- List issues with `gh issue list`, selecting the fields needed for the task.
- Comment with `gh issue comment <number> --body "..."`.
- Apply or remove labels with `gh issue edit`.
- Close issues with `gh issue close`.

Infer the repository from `git remote -v`; `gh` does this automatically when run inside the clone.

When a skill says to publish to the issue tracker, create a GitHub issue. When it says to fetch the relevant ticket, read the GitHub issue and its comments.
