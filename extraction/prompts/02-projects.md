# Step 2 — Group PR records into projects

Input: all PR records from step 1. Output: the `projects`, `skills` and
`categories` sections of `workstory-experience.json` (see `extraction/schema.json`),
plus `project_id` for each PR.

## How to group

- A **project** is a larger piece of engineering work: one feature, migration,
  integration or initiative. It often spans several repos (API + admin UI +
  shared library) and weeks of PRs.
- Group by shared `topic`, overlapping time and related repos/files.
- Do **not** merge unrelated work just because it is in the same repo.
- Small, unrelated PRs (`significance: low`) stay standalone (`project_id: null`).
- Aim for projects that are meaningful to talk about in an interview.

## For each project

Follow the schema exactly. In particular:

- `my_contributions`: what the engineer did, from the PR `contribution` fields.
- `decisions`, `metrics`: only those present in the PR records. Never invent.
- `skills[].involvement`: `implemented` (built it), `collaborated`, `modified`
  (changed existing code), `used` (integrated something existing),
  `discussed`, `mentioned`.
- `confidence`: `low` if most PRs had vague descriptions; list what is unclear in
  `uncertainties`.
- `complexity`: by the challenge solved, not by size — see `03-complexity.md`.

## Rules

- Same sanitisation rules as step 1.
- Use consistent, canonical skill names; put alternative spellings in `aliases`.
- Every skill and category used by a project must appear in the top-level lists.
- Run `uv run workstory-validate <file>` and fix every error.
