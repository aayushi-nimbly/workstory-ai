# Step 1 — Turn raw PRs into PR records

You are given raw pull requests authored by one engineer (`data/raw/prs/*.json`:
title, description, dates, state, changed file paths, size). For each PR, write
one **PR record** describing what the engineer did.

## Output

A JSON array of objects, one per PR:

```json
{
  "id": "pr-<repo-name>-<number>",
  "repo": "<repo name without the owner>",
  "number": 123,
  "title": "<cleaned PR title>",
  "status": "merged | open | closed",
  "created_at": "YYYY-MM-DD",
  "merged_at": "YYYY-MM-DD or null",
  "url": "<PR url>",
  "summary": "1-3 sentences: what changed and why",
  "contribution": "What the engineer personally did in this PR",
  "problem": "The problem addressed, or null if unclear",
  "technologies": ["Canonical names, e.g. PostgreSQL, Node.js, TypeScript"],
  "work_type": "feature | bugfix | performance | refactor | infra | test | docs | chore",
  "significance": "high | medium | low",
  "topic": "short label for the larger piece of work, e.g. 'report export queue'",
  "decisions": [{"decision": "...", "reasoning": "...", "alternatives": ["..."]}],
  "metrics": [{"name": "...", "before": 0, "after": 0, "unit": "...", "evidence": "PR description"}],
  "confidence": "high | medium | low"
}
```

## Rules

1. **Use only what the PR says.** Title, description, file paths and size are the
   only evidence. Never invent behaviour, numbers or outcomes.
2. **Decisions and metrics only when explicitly stated** in the description.
   Otherwise use empty lists. Metrics need real numbers from the PR.
3. **Technologies:** infer from file paths only when obvious (`*.ts` → TypeScript,
   `migrations/*.sql` → SQL). Use canonical names (PostgreSQL, not postgres).
4. **significance:** `high` = substantial feature/design/performance work;
   `medium` = normal feature or meaningful fix; `low` = trivial (version bumps,
   typos, config tweaks, merges of release branches).
5. **confidence:** `low` when the description is empty or vague and the title is
   all there is.
6. **status:** `merged` if mergedAt is set; `closed` if closed without merge; else `open`.
   Closed-unmerged work was attempted, not shipped — say so in the summary.
7. **Sanitise.** Never copy secrets, tokens, passwords, connection strings,
   internal hostnames/IPs, customer or client names, or personal data. Replace
   customer names with "a customer". Ticket IDs (e.g. ABC-123) may stay.
8. **topic** should be the same wording for PRs that are clearly part of the same
   feature, so they can be grouped into projects in the next step.
9. Be concise and concrete. Prefer "Added a BullMQ job to generate PDF reports
   asynchronously" over "Improved reporting".
