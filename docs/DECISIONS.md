# Engineering decisions

1. The supplied file is lowercase `srs.md`; it is the source of truth and remains unchanged.
2. Start at 0.1.0. Default local retrieval uses deterministic hashed lexical vectors, explicitly
   not a pretrained semantic model. Sentence Transformers enables semantic retrieval. Without
   a configured chat model, return evidence excerpts rather than pretend to generate an answer.
3. IDs are SHA-256 derived from canonical JSON. Asset identity includes owner and content hash;
   document identity includes source, timestamps, content and processing configuration.
4. All time values are finite nonnegative seconds. Both boundaries are present or both absent;
   end >= start. Frame descriptions describe sampled instants, with configurable observation
   windows, not an assertion that the whole interval is visually unchanged.
5. The initial vector path embeds text representations only. Every store operation names a space
   (model + version + dimensions); mismatch is an error. Native image/audio interfaces are extension
   points, not falsely advertised implemented embedding models.
6. Local SQLite is persistent; default vectors are memory-resident and rebuilt from documents after
   restart on first use. Server deployments use PostgreSQL/Qdrant/Redis/ARQ.
7. No cross-database distributed transaction: stage vector rows then atomically replace committed
   documents. Retrieval intersects with committed IDs. Failure can leave unreachable vector rows;
   retry/deletion clears these. Never delete the previous committed generation before staging.
8. SDK paths are trusted local inputs. Remote URL loading requires an explicitly permitted HTTPS
   hostname and rejects redirects/private addresses; the API accepts uploads only. No arbitrary
   client-controlled server paths or fetch URLs.
9. External provider text is untrusted evidence. Context is JSON data, instructions are separate,
   and citations must refer to supplied IDs. Citation validation cannot prove semantic entailment;
   applications requiring stronger guarantees need human review or a verification model.
10. Multi-user cache identity includes asset ownership. Processing/deletion are serialized locally;
    distributed server jobs use a Redis lease. Models are lazy and synchronous inference runs in
    threads. Cancellation stops orchestration/subprocesses, but cannot forcibly interrupt a running
    native model thread.
11. Normalize frame PTS to the container origin and add the first audio stream's offset to
    decoded-audio transcript timestamps. Explicitly map the first audio stream so extraction and
    timestamp calculation agree. Tests include delayed audio.
12. Cache entries use an asset prefix so deletion removes all model/configuration generations,
    including values written before failed indexing. Redis deletion scans only that prefix.
13. Authentication is explicit. API keys map to owners; inaccessible IDs return 404. The optional
    development-owner mode must be selected deliberately. Upload byte limits are enforced while
    receiving the request as well as while copying its file.
14. Base package APIs deliberately expose extractive results without a configured LLM. TTS,
    native media embeddings have a typed extension contract; no fabricated baseline implementation
    is supplied. Hosted diarization and vision-backed scanned-PDF OCR are optional adapters.
15. Foundation validation initially used already-downloaded dependency archives while the native
    development dependencies finished downloading. Full installed-environment checks subsequently
    replaced those preliminary checks; see VALIDATION.md for the final executed commands.
