# RAG Decisions

This log records decisions made specifically for Know Your Lease. Items marked TBD are intentionally unresolved until the stage where they can be evaluated with real lease documents.

## PostgreSQL + pgvector is the vector store

**Chosen:** Keep document metadata, future chunks, source metadata, and embeddings in PostgreSQL, with pgvector providing vector search.

**Why:** Document ownership filters and vector retrieval can share one transactionally consistent datastore. The project already needs relational metadata, and the expected portfolio-scale workload does not justify another database service.

**Alternative considered:** A dedicated vector database. It adds operational complexity without a demonstrated Stage 1 requirement and can be revisited if scale or retrieval features demand it.

## Retrieval will always be scoped to one document ID

**Chosen:** Every future chunk retrieval query must filter by the uploaded `document_id` before content is supplied to answer generation.

**Why:** The product promise is to answer from the lease the user is viewing. Cross-document retrieval would create both grounding errors and a data-isolation risk.

**Can change later:** A deliberate multi-document comparison mode could accept an explicit allow-list of document IDs; unscoped retrieval should still never be used.

## Page-aware source metadata will be preserved

**Chosen:** Stage 2 extraction and chunking must retain page number and section information when available, alongside the exact source text.

**Why:** The UI must show verifiable citations and later jump to the relevant place in the lease. Reconstructing page provenance after chunking is unreliable.

**Alternative considered:** Store only chunk text. Rejected because it cannot support the citation experience promised by the product.

## Generated answers will be lease-grounded

**Chosen:** The future answer model may use only passages retrieved from the selected lease and must decline when the retrieved evidence is insufficient.

**Why:** This is a document assistant, not a general legal advice system. Traceability is more important than producing an answer for every question.

**Can change later:** General explanatory context could be added as a separately labeled mode, never presented as lease content.

## Raw PDF retention is deferred

**Chosen:** Stage 1 validates the upload stream and stores metadata only; it does not persist the PDF bytes.

**Why:** No current feature needs retained bytes, and avoiding storage keeps data handling minimal. Stage 2 will choose a local/object storage lifecycle together with extraction jobs.

**Alternative considered:** Save uploads on the API filesystem. Rejected for now because it is fragile across deployments and would pre-empt the storage/privacy design.

## Decisions deferred to Stage 2

- PDF extraction library and handling of image-only leases: **TBD**
- Chunk boundaries, target size, and overlap: **TBD**, to be tested on representative leases
- Embedding model and vector dimensions: **TBD**, based on retrieval evaluation and cost
- Exact vs. approximate pgvector index strategy: **TBD**, after corpus size and latency are measured
- Hybrid retrieval and reranking: **TBD**, only if baseline semantic retrieval evaluation shows a need
