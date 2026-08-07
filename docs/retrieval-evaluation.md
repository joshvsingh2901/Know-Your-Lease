# Retrieval Evaluation

## Methodology

Stage 5 evaluates retrieval separately from answer generation. The evaluator accepts an existing `ready` document UUID, batches the evaluation questions through the existing Voyage `voyage-law-2` query-embedding service using `input_type=query`, and passes every returned vector through the production `RetrievalService` with its existing `candidate_k=10`, cosine ranking, document scope, and diversification settings. It never uploads, extracts, chunks, indexes, or calls Gemini.

The dataset is `backend/evaluation/retrieval_dataset.json`. It contains 24 supported questions across pets, fees, utilities, assignment/sublet, entry, termination, insurance, guests, locks, modifications, damage, and smoking, plus three unsupported questions. Each supported question has lightweight expected page numbers and a topic. The generated optional JSON report records only ranks, pages, chunk indexes, and scores—not lease text.

`Hit@K` is the fraction of supported questions for which at least one expected page appears in the first K diversified results. Average first relevant rank is calculated only for supported queries with a hit. Unsupported questions are excluded from Hit@K because they have no expected evidence.

## Baseline result

The representative 34-page lease (50 indexed chunks) was evaluated once on 2026-08-07 using the unchanged production baseline.

| Metric | Result |
| --- | ---: |
| Supported questions | 24 |
| Unsupported questions | 3 |
| Hit@1 | 91.7% |
| Hit@3 | 95.8% |
| Hit@5 | 100.0% |
| Average first relevant rank | 1.17 |
| Average top score for unsupported queries | 0.228 |

The real run took about seven seconds end to end. The evaluator used one Voyage query-embedding batch for all 27 questions (plus local tokenization), no Gemini request, and no document mutation.

## Failure analysis

- **“What happens if my cheque bounces?”** — the page 3 NSF clause ranked second (score 0.214) behind a low-score signature-detail chunk on page 24 (0.218). This is a low-margin semantic-ranking issue caused by a noisy signature artifact, not a missing clause; the correct evidence remains within top 3.
- **“What happens if rent is late?”** — the lease-specific page 4 late-payment consequence ranked fourth (0.423). Broader rent and termination text on pages 10, 3, and 20 ranked ahead. This is a broad-query/multiple-clause issue: page 10 is relevant general rent-on-time guidance, while page 4 carries the lease-specific $25 consequence. The expected evidence remains within top 5.

An initial Internet label omitted a valid page 21 Internet clause. The dataset was corrected after inspecting the source chunk; this was a ground-truth correction, not a retrieval failure.

## Decision and comparison

No retrieval change was justified. The baseline already retrieves expected evidence for every supported evaluation query at top 5 and has a 1.17 average first-relevant rank. Increasing candidate/final limits would not improve the recorded Hit@5, while hybrid retrieval or reranking would add latency, cost, and rate-limit pressure without evidence of a material user-facing gap.

Therefore before/after metrics are intentionally identical:

| Metric | Baseline | Final |
| --- | ---: | ---: |
| Hit@1 | 91.7% | 91.7% |
| Hit@3 | 95.8% | 95.8% |
| Hit@5 | 100.0% | 100.0% |
| Average first relevant rank | 1.17 | 1.17 |

## Negative queries and remaining weaknesses

The unsupported cabinet, refrigerator, and swimming-pool questions had top cosine similarities of 0.203, 0.264, and 0.216 respectively. These were lower than the strong supported-query matches but overlap with low-confidence supported cases such as NSF. That is not enough evidence to introduce a production relevance threshold. The system should retain its evidence-bound generation and abstention behavior until a larger labeled set permits threshold calibration.

The evaluation is page-level rather than clause-level, is based on one representative lease, and does not evaluate answer faithfulness. Signature and audit-page chunks can occasionally compete with weakly worded queries. Future work should add leases, clause-level labels, and a threshold calibration study before considering lexical hybrid search or reranking.
