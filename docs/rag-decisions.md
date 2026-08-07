# RAG Decisions

This file records the concrete Stage 2 ingestion and Stage 3 retrieval/generation choices for Know Your Lease.

## Extraction and source fidelity

**PyMuPDF** extracts sorted text blocks page by page. Page numbers are stored starting at 1, empty pages remain represented during extraction, and normalization only fixes line endings, horizontal whitespace, and repeated blank lines. Legal text is not summarized or paraphrased.

Chunks do not cross page boundaries. This can leave a smaller final chunk on a page, but it gives every chunk one unambiguous `page_number` for later citations. `paragraph_index` is populated from detected blank-line boundaries; `section_title` remains nullable because the current deterministic parser cannot identify headings reliably enough to claim them.

Image-only/scanned documents with fewer than 50 non-whitespace extracted characters fail with an OCR-specific message. OCR is a future extraction implementation, not a reason to weaken source provenance now.

## Chunking

The local chunker builds units from paragraphs, then sentence boundaries, and only falls back to word boundaries for an oversized sentence. It targets **600 estimated tokens**, enforces a **750-token maximum**, uses a **75-token sentence-unit overlap**, and avoids flushing below **120 tokens** when possible.

Token size is a conservative lexical estimate with a small multiplier rather than a provider tokenizer dependency. Final counts are useful operational estimates, not billing-authoritative token counts. This keeps preprocessing transparent and avoids adding an orchestration framework.

## Embeddings

- Provider: **Voyage AI**
- Model: **`voyage-law-2`**
- Dimensions: **1024**
- Stored chunk input type: **`document`**
- Question input type: **`query`**

Chunks are counted with Voyage's model tokenizer and batched in original order, with at most 128 inputs and 9,500 safety-adjusted tokens per request. Because the safety-adjusted value includes 10% headroom, a full batch represents at most about 8,636 provider tokens and remains below the 10K TPM ceiling. A conservative 2.5× estimate is used only if the tokenizer is unavailable. Returned count, order alignment, and 1024-dimensional shape are validated before persistence. The process-local service serializes embedding work and applies a rolling 60-second window to every initial/retry request against the configured **3 requests/minute and 10,000 tokens/minute** limits. Provider `Retry-After` is honored, and transient 429/5xx/timeout failures receive at most two retries.

The official Voyage client is pinned below 0.3 because that compatible API supports `voyage-law-2`, `input_type`, and truncation control without pulling an unused LangChain stack. No LangChain or LlamaIndex code is used.

Question answering reuses the same cached embedding service and rolling provider budget as ingestion. One trimmed question produces one `voyage-law-2` vector using `input_type="query"`; the returned vector must have exactly 1024 dimensions. Query and document input modes are deliberately asymmetric because Voyage optimizes them for their respective sides of retrieval.

## Vector persistence and retrieval scope

PostgreSQL + pgvector stores relational metadata and vectors together. `DocumentChunk.embedding` is `vector(1024)`. Every chunk has a required `document_id`, and `(document_id, chunk_index)` is unique. Indexes on `document_id` and `(document_id, page_number)` support isolation and inspection.

Retrieval uses pgvector's exact **cosine distance** operator (`<=>`), appropriate for comparing the Voyage query and document vectors. Similarity exposed by the service is `1 - cosine_distance`. The SQL selects chunk metadata plus distance, filters by `DocumentChunk.document_id` before ordering, orders by ascending distance, and never selects or returns raw embeddings.

The baseline retrieves **10 candidates** and returns at most **5 final evidence chunks**. This leaves room for broad questions to draw from separate lease sections without sending excessive context to Gemini. A lightweight five-word-shingle comparison removes obvious near-duplicates using a 0.78 overlap threshold for adjacent same-page chunks and 0.92 otherwise. Distinct adjacent chunks remain eligible. Retrieval and orchestration both defensively enforce the requested `document_id`; unscoped cross-document retrieval would violate the product contract and data isolation.

There is no ANN index yet. Typical leases produce tens of chunks, so exact search over one document is simpler and sufficiently fast. HNSW/IVFFlat should be added only after corpus size and measured latency justify it.

## Grounded generation and citations

- Provider: **Google Gemini**, through the official `google-genai` SDK
- Model: **`gemini-3.5-flash`**
- Maximum output: **2,048 tokens**
- Thinking level: **low**
- Response: strict JSON containing `answer` and source objects with `source_id` and `quote`

The final retrieved chunks receive deterministic identifiers (`SOURCE_1`, `SOURCE_2`, and so on). Gemini receives only these excerpts and the question as JSON-encoded untrusted data. Its system instruction prohibits outside legal knowledge, invented lease terms, legal advice, and following instructions embedded in either the document or the user's question. It also asks Gemini to synthesize qualifying or apparently conflicting provisions instead of presenting an unqualified yes/no or resolving enforceability itself.

The backend validates every returned source ID against the supplied evidence map. Unknown IDs reject the provider response, duplicate valid IDs are removed in order, and page numbers are never accepted from Gemini. Citations are built from database-owned chunk IDs, page numbers, nullable section titles, exact chunk text, and retrieval scores.

Gemini 429/5xx/timeout failures receive at most one application-level retry after a short two-second backoff. Permanent errors are not retried, and provider messages remain in sanitized internal logs rather than API responses. This bounded retry handled a real transient `503 UNAVAILABLE` during Stage 3 evaluation without adding a queue or changing the provider boundary.

If Gemini returns no source IDs, any prose it generated is discarded and replaced with: “I couldn't find enough information in this lease to answer that confidently.” No retrieval-score cutoff is applied yet because no representative labeled evaluation set has established a defensible threshold. Conservative prompt abstention and source validation are the current baseline; threshold calibration belongs in retrieval evaluation.

Reranking is deliberately deferred. Direct Voyage embeddings plus exact pgvector search should be evaluated first, and a reranker would add provider latency, cost, and rate-limit pressure. Hybrid/full-text retrieval is also deferred until evaluation demonstrates a concrete failure mode.

## Stage 5 retrieval evaluation

Stage 5 adds a repeatable 27-question, page-labeled evaluation dataset for the representative 34-page lease: 24 supported lease questions and three deliberately unsupported questions. `backend/scripts/evaluate_retrieval.py` uses the real document-scoped retrieval path but batches its independent Voyage query embeddings so an evaluation does not spend one request per question. It never invokes Gemini or mutates the document index.

The first baseline achieved **Hit@1 91.7%, Hit@3 95.8%, Hit@5 100.0%, and average first relevant rank 1.17**. The two non-top-one supported cases were a page-3 NSF clause at rank 2 behind signature noise and a lease-specific late-rent clause at rank 4 behind broader rent material. Since every expected source appeared in the existing top five, the system remains **vector-only, exact cosine, candidate_k=10, final_k=5**. No hybrid search, reranker, threshold, or tuning was added merely to improve a benchmark number.

Unsupported-query top scores averaged 0.228, but this overlaps weak supported evidence, so there is no defensible relevance cutoff yet. Keep conservative evidence-bound generation/abstention and revisit threshold calibration only with a larger multi-lease labeled set.

## Citation presentation and source inspection

Retrieval chunks remain intentionally larger than user-facing citations. Larger chunks preserve clause context and retrieval quality; shrinking them merely to improve card readability would harm that boundary. Gemini now returns only the source IDs it used plus a short `quote` for each source. The backend normalizes whitespace and verifies that each quote is contained in its corresponding retrieval chunk. It never trusts a model quote that cannot be found in the chunk.

When the quote is omitted, invalid, or too broad, a deterministic extractor scores chunk sentences by lexical overlap with the user's question and returns the best sentence plus a fitting neighbor, normally below **480 characters**. It avoids sending another model request, retains source fidelity, and keeps the full chunk out of the default citation UI. A light lettered-heading heuristic can expose a title such as `Pets` only when that heading appears in the stored chunk; otherwise `section_title` remains null.

The frontend uses **React-PDF** with its PDF.js worker in a client-only Next.js component. The original PDF is served through the document-scoped `GET /documents/{id}/pdf` endpoint, not from a filesystem path. At ready state, desktop uses a two-column workspace: document viewer on the left and question/citation panel on the right. Clicking **View in lease** selects the source card, moves the viewer to its backend-owned page number, and attempts a whitespace-normalized match against the rendered PDF text layer. Only matching spans are highlighted; a failed match intentionally leaves just the correct page navigation. Coordinate-level highlighting remains deferred because ingestion does not store PDF bounding boxes.

## Question API and user experience

`POST /documents/{document_id}/retrieve` returns the diversified retrieval results without generation for development diagnosis. `POST /documents/{document_id}/questions` runs the full single-turn pipeline and returns an answer with citations. Both accept the same non-blank question request of at most 1,000 characters, require `status=ready`, and omit embeddings from responses.

The frontend unlocks its question panel after indexing reaches `ready`, provides static suggested questions, prevents duplicate submissions while loading, and renders compact citation cards with a page-jump action. Each question is independent; chat memory and follow-up rewriting are intentionally deferred.

## Storage, atomicity, and execution

Development PDFs are written atomically to `backend/storage/uploads/<document-uuid>.pdf`; the original filename is stored separately and never used as a path. `DocumentStorage` isolates this policy so object storage can replace it later.

FastAPI schedules ingestion with an in-process background task. Chunks are inserted only after extraction, chunking, and all embeddings succeed. The final transaction removes stale chunks, inserts the full replacement index, and marks the document `ready`; failures remove chunks and mark it `failed` with a safe message.

This is appropriate for the portfolio MVP but not durable: a process crash can interrupt an in-flight job. A production version should use a durable worker queue and cross-process rate limiter.

## Current limitations

OCR, authentication/user ownership, durable ingestion jobs, cross-process provider coordination, chat history, reranking, hybrid retrieval, calibrated relevance thresholds, and coordinate-level PDF highlights are not implemented. The debug chunks and retrieval endpoints expose lease excerpts and must be restricted before production use.
