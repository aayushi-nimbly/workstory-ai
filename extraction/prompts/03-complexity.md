# Step 3 — Score project complexity by the challenge solved

Complexity measures **how hard the problem was**, not how much work it took.

## Ignore

- Number of PRs, repos or services touched.
- Volume of UI, CRUD endpoints or dashboard work.
- Mechanical, repetitive changes rolled out widely (version bumps, flag removals, renames).

## Count (signals of real difficulty)

1. **Data correctness and migration risk** — moving or transforming live data without loss,
   dual writes, backfills, cutovers, consistency between stores.
2. **Distributed systems and failure handling** — timeouts, retries, partial failures,
   idempotency, queues and dead-letter handling, behaviour when dependencies are down.
3. **Architectural change** — moving responsibilities between services, new
   service-to-service contracts or authentication, changing how a core flow works.
4. **Concurrency and performance under load** — race conditions, parallelism, query and
   pipeline performance, especially with measured improvements.
5. **Hard correctness logic** — subtle edge cases, matching or deduplication, scoring rules,
   time zones, anything where "almost right" causes real bugs.
6. **Trade-off decisions** — real alternatives weighed, with consequences.

## Levels

- **high** — at least one signal is central to the project and the evidence shows it was
  handled (e.g. a zero-loss data cutover, fleet-wide failure handling, a core flow re-architected).
- **medium** — some signals present but limited in scope, or a solid feature with
  non-trivial logic.
- **low** — mostly UI, CRUD, dashboards, configuration, or wide but mechanical changes.

When evidence is thin (low-confidence project), do not score above **medium**.

## Output

For each project: `complexity` and a one-sentence `reason` naming the specific challenge
(or why it is not complex). Reasons must be supported by the project's own text.
