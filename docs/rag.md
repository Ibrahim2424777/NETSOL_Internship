# Document RAG (Phase 12)

## What RAG is, and why this app uses it

Retrieval-Augmented Generation (RAG) is a technique for grounding an LLM's
answer in specific external text it wasn't trained on: instead of asking
Gemini a question directly, the system first searches a document collection
for passages relevant to that question, then hands Gemini both the question
and those passages, and asks it to answer using them.

This matters because Gemini's training data doesn't include this
application's own documents - without RAG, it can only answer from general
pretrained knowledge (or make something up). RAG lets the chatbot answer
questions about a specific, private document accurately, and lets it say
"I don't know" honestly when the document doesn't cover something, instead
of guessing.

## Why a fictional test document

The bundled document (`backend/data/documents/university_ai_research_handbook.pdf`,
a 13-page "Northbridge Institute AI Research Handbook") is deliberately
fictional, with invented specifics: a fictional institution, fictional form
numbers, and specific numeric rules (e.g. "Stage 2 requires a minimum of 10
working days"). A real-world or well-known document wouldn't prove
anything - Gemini might already know the answer from pretraining, so a
correct answer wouldn't demonstrate that retrieval actually happened. Because
these facts exist nowhere except this one PDF, a correct, specific answer is
only possible if the retrieval pipeline actually found and returned the
right passage.

## Architecture

```mermaid
flowchart TD
    User[User message] --> API[FastAPI /chats/{id}/messages]
    API --> Graph[LangGraph: chat_id = thread_id]

    subgraph Graph[LangGraph chat_graph]
        direction TB
        Retriever[Retriever node] --> Model[Model node]
    end

    Checkpointer[(Postgres checkpointer<br/>Phase 11 - conversation memory)] <-.-> Graph
    Retriever --> VectorSearch[Embed query -&gt; similarity search]
    VectorSearch --> LanceDB[(LanceDB<br/>local, persistent)]
    LanceDB --> Chunks[Top-K relevant chunks<br/>+ source, page, score]
    Chunks --> Model
    Model --> Gemini[Gemini API<br/>grounded prompt]
    Gemini --> Stream[SSE stream to client]
    Stream --> Postgres[(Postgres messages table<br/>+ sources column)]

    Ingest[Ingestion CLI<br/>uv run python -m app.rag.ingest_cli] -.offline, one-time.-> LanceDB
    PDF[PDF document] --> Ingest
```

Request-time flow (every chat message, unconditionally - there is no RAG
on/off toggle in this phase):

1. `chat_id` doubles as the LangGraph `thread_id` (unchanged from Phase 11).
2. The **retriever node** runs first: it takes the latest user message,
   embeds it, and searches the vector store for the most relevant chunks.
3. The **model node** runs second: it builds the Gemini prompt from trimmed
   conversation history (Phase 11) *plus* the current turn's retrieved
   chunks (Phase 12), then streams Gemini's reply exactly as before.
4. The reply is cached/persisted exactly as before - with one addition, a
   `sources` field recording which document chunks were used.

Ingestion is a separate, offline pipeline (see below) - it never runs as
part of a chat request, and embeddings are only ever generated once, when a
document is ingested.

## Ingestion pipeline

`app/rag/ingestion.py`, invoked via the CLI (`app/rag/ingest_cli.py`), does:

1. **Load** - `pypdf` extracts text page by page, keeping each page's number.
2. **Chunk** - `langchain-text-splitters`' `RecursiveCharacterTextSplitter`
   splits each page's text into overlapping chunks (paragraph/sentence/word
   boundaries, in that preference order - never mid-word). Applied per page
   so every chunk keeps an accurate page number.
   - `RAG_CHUNK_SIZE` (default 800 characters, ~150-200 words): large enough
     that a chunk usually contains a whole rule or paragraph - most facts in
     this kind of policy document span 2-4 sentences.
   - `RAG_CHUNK_OVERLAP` (default 120, ~15%): enough that a fact split across
     a chunk boundary still appears whole in at least one of the two chunks.
3. **Embed** - each chunk's text is turned into a 384-dimension vector (see
   Embeddings below). Generated once here, never regenerated per query.
4. **Store** - chunks + vectors + metadata (source filename, page, chunk id)
   are written to the vector store, replacing any existing chunks for that
   source first (idempotent - re-running ingestion after editing a document
   doesn't accumulate duplicates).

### How to ingest the document

```powershell
cd backend
uv run python -m app.rag.ingest_cli
```

Ingests the bundled handbook by default, or pass a path to ingest a
different PDF: `uv run python -m app.rag.ingest_cli path\to\file.pdf`.

This is a standalone CLI, not an HTTP endpoint - there's no multi-user
document upload flow in this phase (one fixed document ships with the repo),
so an ingestion endpoint would be pure unauthenticated-filesystem-access
attack surface for no functional gain. It mirrors how Alembic migrations
are already a CLI-driven, developer-run process in this project.

## Embeddings

`app/services/embedding_service.py` defines `EmbeddingService`, an
abstraction mirroring `ModelService`'s pattern (Phase 4) - the rest of the
RAG code depends only on this interface, never on a specific embedding
provider.

**Model used**: `BAAI/bge-small-en-v1.5` via
[`fastembed`](https://github.com/qdrant/fastembed) (`RAG_EMBEDDING_MODEL`).

**Why**: fastembed runs a quantized ONNX model on CPU - free, fully local,
no external API call or per-request cost, and no PyTorch dependency (which
`sentence-transformers`, the more commonly-reached-for option, would pull
in at 600MB+). This is the same reasoning that ruled out a heavier
dependency for the Phase 11 checkpointer. The model is asymmetric (BGE
models expect different handling for indexed text vs. search queries),
which is why `EmbeddingService` exposes `embed_documents()` and
`embed_query()` separately rather than one generic method.

The ~130MB model downloads once from Hugging Face and is cached in
`data/embedding_cache/` (pinned there explicitly - fastembed's default
cache location is the OS temp directory, which can be cleared at any time).

## Vector storage

[`LanceDB`](https://lancedb.github.io/lancedb/), an embedded, file-backed
vector database - `RAG_VECTOR_DB_PATH` (default `./data/vector_store`) is
just a directory on disk. No server process, so it survives backend
restarts on its own, exactly like the Phase 11 checkpointer surviving on
Postgres.

Chosen over Chroma (the option named in the original spec) purely for
dependency weight: a dry-run install comparison showed Chroma pulling in 52
packages - including a Kubernetes client, gRPC, and OpenTelemetry, baggage
from its optional server mode that goes unused here - versus LanceDB's 9,
for equivalent embedded/persistent local functionality. LanceDB also stores
arbitrary metadata (source, page, chunk id) directly alongside each vector,
so no separate metadata store was needed.

This is a storage layer entirely separate from PostgreSQL and Redis:
PostgreSQL remains the source of truth for users/chats/messages, Redis keeps
its existing cache responsibilities, and neither is used to store or
substitute for document embeddings.

## Retrieval

`app/rag/retriever.py`'s `Retriever` is deliberately independent of
LangGraph - `app/langgraph/nodes/retriever_node.py` is a thin wrapper around
it, not the other way around, so a future router (Phase 14) can call
retrieval directly without going through the graph.

For each query: embed it, run cosine-similarity search, keep the top
`RAG_TOP_K` (default 4) results, then filter out anything below
`RAG_MIN_SCORE` (default 0.6). The filter matters because a vector search
always returns its *k* nearest neighbors even for a completely unrelated
query, just with a low score - without it, an off-topic question would
still get document text stuffed into the prompt and incorrectly show
"Sources used". (Calibrated empirically against this project's test
document: genuinely relevant queries scored ~0.76-0.82, off-topic ones
~0.37-0.54.)

## LangGraph integration

The graph (`app/langgraph/graphs/chat_graph.py`) changed from Phase 11's
`messages -> [model] -> END` to:

```
messages -> [retriever] -> [model] -> END
```

`ChatState` (`app/langgraph/state.py`) gained one field:

```python
class ChatState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]  # Phase 11
    retrieved_context: list[RetrievedChunk]               # Phase 12
```

`retrieved_context` is a **plain field, no reducer** - unlike `messages`
(which accumulates via `add_messages`), it's fully overwritten by the
retriever node on every run. Retrieval is per-question, not cumulative
conversation history, so there is nothing to accumulate.

## Interaction with Phase 11 conversational memory

Phase 11 memory and Phase 12 retrieval solve different problems and stay
architecturally separate:

- `messages` / the Postgres checkpointer: unchanged. Still the only thing
  giving conversational continuity, thread-scoped by `chat_id`.
- `retrieved_context`: computed fresh every turn from the *current*
  question only.

The model node combines them by rewriting only the **current** turn's
content before calling Gemini - a `Retrieved Context: ... / User Question:
...` block, with instructions to prefer the retrieved context, not invent
facts, and say when the context is insufficient. Earlier turns in history
are left as plain text: they were already answered (grounded on their own
retrieval at the time), and re-injecting retrieval boilerplate into every
historical turn on every call would both bloat the prompt and duplicate
context Gemini already responded to. Because only `state["messages"]`
itself (never this augmented copy) gets checkpointed, the retrieval framing
never leaks into persisted conversation history.

This is what makes a follow-up like "How long does *that* process take?"
work correctly after "Explain the dataset approval process": pronoun
resolution comes from conversational memory, the specific numeric fact
comes from a fresh retrieval against the follow-up question.

## Source attribution

Retrieved chunks' metadata (source filename, page) is retained end-to-end,
not just shown transiently during streaming:

1. The retriever node writes chunks (with scores) to `ChatState`.
2. After the graph run completes, `ChatExecutionService.get_retrieved_sources()`
   reads the final checkpointed state back and collapses the chunks to one
   entry per distinct (source, page).
3. This is attached to the assistant's `MessageResponse` (`sources` field,
   sent in the `done` SSE event) and persisted to a nullable `sources` JSONB
   column on the `messages` table (migration `365c72a508f3`) - so it
   survives a page refresh, not just the live stream.
4. The frontend (`MessageBubble.tsx`) shows a small "Sources used" list
   under any assistant reply that has them.

`sources` is `null`/absent on any reply that didn't retrieve anything above
`RAG_MIN_SCORE` - a plain conversational answer never gets a spurious
citation.

## Configuration reference

| Variable | Default | Meaning |
|---|---|---|
| `RAG_VECTOR_DB_PATH` | `./data/vector_store` | LanceDB directory |
| `RAG_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | fastembed model id |
| `RAG_TOP_K` | `4` | Chunks returned per query, before score filtering |
| `RAG_MIN_SCORE` | `0.6` | Minimum cosine similarity to count as relevant |
| `RAG_CHUNK_SIZE` | `800` | Characters per chunk |
| `RAG_CHUNK_OVERLAP` | `120` | Character overlap between adjacent chunks |

## How to run the RAG tests

There's no permanent automated test suite for this phase (the project has
none yet for earlier phases either) - verification was done with throwaway
scripts driving the live server end-to-end, covering all 7 scenarios the
spec calls for: direct retrieval, grounded answers, refusal to fabricate
for out-of-scope questions, multi-turn memory+retrieval together, vector
store survival across a real backend process restart, unbroken SSE
streaming, and source metadata correctness. To re-verify manually:

1. Start Postgres/Redis, then the backend (see the main run instructions),
   with the handbook already ingested (`uv run python -m app.rag.ingest_cli`).
2. Ask a question with a specific, checkable answer from the handbook (e.g.
   "How many working days does Stage 2 of dataset approval take?") and
   confirm the reply cites the exact figure (10 working days) with a
   `university_ai_research_handbook.pdf` source.
3. Ask something the handbook doesn't cover (e.g. "What's the lab's coffee
   budget?") and confirm the model says it doesn't know, with no sources
   attached.
4. Ask a follow-up using a pronoun ("How long does *that* stage take?") and
   confirm it resolves correctly using conversation memory.
5. Restart the backend process and repeat step 2 - the answer should still
   be correct without re-running ingestion.
