# Retrieval evaluation

- Question set: `eval-questions.json` (16 positive, 4 negative)
- Run at: 2026-11-27 19:24 UTC

## Retrieval (positive questions)

| Mode | Hit@5 | Recall@5 | MRR | Median latency |
|---|---|---|---|---|
| vector | 0.94 | 0.91 | 0.91 | 16 ms |
| keyword | 1.00 | 0.97 | 0.92 | 3 ms |
| hybrid | 0.94 | 0.91 | 0.95 | 26 ms |

## Misses in hybrid search (no expected project in top 5)

- **q09** Have I used vector search? — expected proj-support-docs-assistant; first relevant at rank 6; got proj-shipment-search-performance

## Answers (full assistant)

| Kind | Passed | Median time |
|---|---|---|
| positive | 15/16 | 6.0 s |
| negative | 4/4 | 7.0 s |

### Failed answers

- **q09** (positive) Have I used vector search? — support `none`, cited nothing
