# RAG Decisions

This file records the concrete Stage 2 choices for Know Your Lease.

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
- Stage 3 question input type: **`query`** (not implemented yet)

Chunks are counted with Voyage's model tokenizer and batched in original order, with at most 128 inputs and 9,500 safety-adjusted tokens per request. Because the safety-adjusted value includes 10% headroom, a full batch represents at most about 8,636 provider tokens and remains below the 10K TPM ceiling. A conservative 2.5× estimate is used only if the tokenizer is unavailable. Returned count, order alignment, and 1024-dimensional shape are validated before persistence. The process-local service serializes embedding work and applies a rolling 60-second window to every initial/retry request against the configured **3 requests/minute and 10,000 tokens/minute** limits. Provider `Retry-After` is honored, and transient 429/5xx/timeout failures receive at most two retries.

The official Voyage client is pinned below 0.3 because that compatible API supports `voyage-law-2`, `input_type`, and truncation control without pulling an unused LangChain stack. No LangChain or LlamaIndex code is used.

## Vector persistence and retrieval scope

PostgreSQL + pgvector stores relational metadata and vectors together. `DocumentChunk.embedding` is `vector(1024)`. Every chunk has a required `document_id`, and `(document_id, chunk_index)` is unique. Indexes on `document_id` and `(document_id, page_number)` support isolation and inspection.

There is no ANN index yet. Typical leases produce tens of chunks, so exact vector distance over one document will be the clearest correct Stage 3 baseline. An HNSW/IVFFlat index should only be added after corpus size and measured latency justify it.

All future retrieval must filter by the selected `document_id`. Unscoped cross-document retrieval would violate both the product contract and data isolation.

## Storage, atomicity, and execution

Development PDFs are written atomically to `backend/storage/uploads/<document-uuid>.pdf`; the original filename is stored separately and never used as a path. `DocumentStorage` isolates this policy so object storage can replace it later.

FastAPI schedules ingestion with an in-process background task. Chunks are inserted only after extraction, chunking, and all embeddings succeed. The final transaction removes stale chunks, inserts the full replacement index, and marks the document `ready`; failures remove chunks and mark it `failed` with a safe message.

This is appropriate for the portfolio MVP but not durable: a process crash can interrupt an in-flight job. A production version should use a durable worker queue and cross-process rate limiter.
