# Project decision log

This document records the choices for the HTGF AI voice-agent coding challenge. It is intended to support implementation and the explanation during the live demonstration.

Decisions recorded: **18 November 2026**. These are design choices, not claims that the features have already been implemented or tested.

## Context and constraints

- Source requirements: `Coding_Challenge_AI-Voice-Agent.pdf`.
- Deadline: **24 November 2026**.
- Available development time: approximately **5–10 hours**, with no availability from Friday afternoon until Monday.
- The developer has a computer science and AI background, prefers Python, and has little frontend experience.
- Work proceeds incrementally, with architectural choices discussed together. Understanding and explaining the result are explicit goals.
- Prioritize the required conversation flow, browser audio, transcript/history, configuration, and structured summary. Visual polish and other bonuses come afterward.

## Agreed decisions

### 01 — Docker for the runtime environment

**Choice:** Use Docker, with Docker Desktop and its WSL 2 backend for local Windows development.

**Reason:** Make application dependencies and startup reproducible, and reduce differences between development and demonstration environments.

**Tradeoff:** Adds container configuration and requires a running Docker engine. External API availability and credentials remain dependencies outside the container.

**Verified:** Docker client/server communication, Docker Compose availability, and the `hello-world` container succeeded on the developer's machine.

**Initial application setup:** One service packages the FastAPI backend and static frontend together, using Python 3.13, a non-root process, a local port mapping, and an HTTP health check. Source changes require rebuilding the image for now; live reload can be added later.

### 02 — Git for version control

**Choice:** Use Git to record small, meaningful increments.

**Reason:** Preserve the development history, make changes reviewable, and allow us to return to a working version.

**Tradeoff:** Commits require deliberate scope and useful messages. Credentials and generated runtime data must be excluded.

**Verified (18 November 2026):** The local repository is initialized on `main`. A `.gitignore` excludes credentials, Python environments/caches, generated artifacts, and local runtime data; `.env.example` templates remain trackable. Ignore rules were checked against representative paths.

**Backup decision (18 November 2026):** Use GitHub for an online backup. The user created [HTGF_coding_challenge](https://github.com/KarlFreiwald/HTGF_coding_challenge), which is configured as `origin`. The first commit (`43379fd`), containing the challenge PDF, this decision log, and `.gitignore`, was successfully pushed; local `main` tracks `origin/main`. Private visibility was recommended but has not been independently verified. Local commits must be pushed to update the online backup.

### 03 — Separate STT → LLM → TTS pipeline

**Choice:** Start with separate speech-to-text, language-model, and text-to-speech stages.

**Reason:** Expose intermediate results, investigate failures and latency per stage, and understand the complete voice pipeline. Providers can be selected independently.

**Alternative considered:** A native speech-to-speech API, attractive for reducing separate integrations and preserving vocal information.

**Tradeoff:** More integration work and latency coordination. Transcription errors can affect the LLM's answer. The PDF's ideal 1–2-second end-of-input-to-first-audio target must be measured, not assumed.

### 04 — Python backend and plain browser frontend

**Choice:** Python for backend logic; plain HTML, CSS, and JavaScript for the frontend.

**Reason:** Use the developer's preferred backend language and keep the small interface understandable without learning a frontend framework. JavaScript provides direct access to browser audio APIs.

**Alternatives considered:** React for component-based UI development; Streamlit for a mostly Python interface. Neither was selected: React adds concepts and tooling, while Streamlit's built-in recording widget does not by itself provide continuous conversational audio.

**Tradeoff:** UI state, browser audio, and updates must be managed explicitly. Simple styling is acceptable; reliable microphone access, playback, controls, and status feedback remain essential.

**AI assistance:** Use AI coding assistance for implementation, particularly layout and styling. Review and test the browser/backend integration so it can be explained during the demonstration. The challenge explicitly permits AI coding tools.

### 05 — External model APIs

**Choice:** Paid external APIs are acceptable for STT, LLM, and TTS; use available trial credits during development.

**Reason:** Avoid local model deployment and GPU requirements within the available time.

**Tradeoff:** Audio/text is sent to providers; network availability, service limits, and usage charges affect operation. Trial terms should be checked when creating accounts.

### 06 — Two user-configurable settings

**Choice:** Conversation language (**German / English**) and tone (**Professional / Conversational**).

**Reason:** Language is useful for the intended users; tone changes the interview experience without changing the required topics. Together these address the PDF's minimum of two adjustable settings.

**Intended behavior:** Language controls recognition configuration, the agent's responses, spoken output, and final summary. Tone changes phrasing while preserving the same information-gathering objectives.

**Proposed implementation details:** Select settings before starting, save them with each conversation, and defer switching during an active conversation. Initially keep UI labels in English. In German, use “Sie” for professional and “du” for conversational tone. Confirm these details before implementation.

### 07 — AssemblyAI for speech-to-text

**Choice:** Use AssemblyAI's streaming STT service. The exact model and configuration remain to be selected.

**Reason:** German/English streaming support and content-aware turn detection fit an interview in which founders may hesitate or give longer answers. Signup credits make initial testing accessible.

**Alternatives considered:** Deepgram Nova-3 and Deepgram Flux Multilingual. Nova-3 offers configurable pause-based endpointing; Flux also offers contextual turn detection, including optional early turn-ending signals for speculative generation. AssemblyAI was selected for its fit to our first implementation, not on the basis of a proven accuracy or latency advantage over Flux.

**Tradeoff:** Turn boundaries depend partly on provider behavior. An early boundary can interrupt an unfinished answer; waiting longer increases perceived latency. We must tune and test this with German and English speech.

**Validation planned:** Test hesitation before a financing amount, a long answer with internal pauses, and a short completed answer. Inspect transcription accuracy, premature turn endings, and delay after the actual end of speech. End-of-turn detection alone does not implement playback cancellation or interruption handling.

**Trial information checked on 18 November 2026:** AssemblyAI documents $50 in signup credits, no credit card required to start, streaming STT access, and non-expiring credits. Account eligibility and terms remain subject to the provider.

Sources:

- [AssemblyAI streaming language support](https://www.assemblyai.com/docs/streaming/multilingual-transcription)
- [AssemblyAI turn detection](https://www.assemblyai.com/docs/streaming/turn-detection)
- [AssemblyAI free trial](https://support.assemblyai.com/articles/5370767329-can-i-sign-up-for-free)
- [AssemblyAI account and credit documentation](https://www.assemblyai.com/docs/faq/how-to-get-your-api-key)
- [Deepgram Flux turn-detection configuration](https://developers.deepgram.com/docs/flux/configuration)

### 08 — FastAPI for the web backend

**Choice (18 November 2026):** Use FastAPI, served by Uvicorn. Serve plain frontend files from the same application in one Docker container initially.

**Reason:** Native asynchronous and WebSocket support fit the planned audio connections and external API calls. Typed validation and generated API documentation will help with settings and structured results. A shared frontend/backend origin simplifies local development.

**Alternative considered:** Flask, a small and flexible framework. Its standard WSGI request model is less convenient for our expected long-lived asynchronous connections and requires additional tooling for WebSockets.

**Tradeoff:** Introduces ASGI, asynchronous application code, and Pydantic conventions. FastAPI itself does not guarantee the voice latency target; provider latency, turn detection, and audio handling still need measurement.

**First implementation scope:** Static page, browser health check, `/health` endpoint, Docker build/run configuration, and startup documentation. Voice integration is the next checkpoint.

**Validation (18 November 2026):** The Docker image built successfully and Compose reported a healthy service. Host HTTP checks passed for `/`, `/health`, both static assets, `/docs`, and `/openapi.json`; `/health` returned `{"status":"ok"}`. Browser rendering and JavaScript interaction have not yet been manually verified.

### 09 — Follow HTGF's visual identity

**Choice (18 November 2026):** All UI styling must relate to the colors and style of [HTGF's website](https://www.htgf.de/), as requested by the developer. This is a standing rule for future UI changes.

**Reason:** Make the demonstration visually relevant to the company while keeping the interface simple.

**Implementation:** `UI_STYLE.md` records the observed website colors, sources, and styling guidance. `app/static/styles.css` centralizes the palette in reusable CSS variables. Replace the provisional green theme with warm neutrals, black text/buttons, coral/lime/mint accents, and pill-shaped controls.

**Tradeoff:** Colors are taken from the actual website theme; typography and the small decorative gradient are approximations. Local font fallbacks keep the prototype self-contained. Exact brand assets and a complete visual reproduction are not part of this change.

**Prior checkpoint confirmation:** The developer opened the initial page and confirmed that its browser health check displayed the expected connected status.

### 10 — Stream microphone audio through FastAPI

**Choice (18 November 2026):** The browser streams audio to FastAPI, which opens the authenticated AssemblyAI connection and returns normalized transcript events.

**Reason:** Keep credentials and conversation coordination in Python, with completed turns available to the future LLM stage.

**Alternative considered:** Connect the browser directly to AssemblyAI using short-lived tokens. This removes a relay hop but adds token handling and a separate route for transcripts to reach the backend.

**Tradeoff:** The relay adds a network hop and requires concurrent audio/transcript tasks and explicit session cleanup.

**Initial implementation details:** Web Audio with an AudioWorklet, 100 ms mono PCM chunks at the browser's actual sample rate, provider model `assemblyai-stt-3-7-realtime-agent`, `balanced` turn detection, and `language_codes` steering toward the selected language. The API key comes from a Git-ignored `.env` injected by Compose at runtime. No voice framework is introduced for this bounded transcription step. The global provider endpoint is used; deployment region can be revisited later.

**Session behavior:** Stop flushes the last audio chunk and waits for the last transcript before closing. Disconnects terminate the provider session, which is billed by connected duration. A 10-minute session limit and a missing-audio timeout bound abandoned sessions. Transcript updates reuse turn IDs. Data remains in the current browser view, with persistence deferred.

**Validation:** Nine backend lifecycle tests and six JavaScript audio/UI tests passed using simulated peers. A real AssemblyAI connection accepted the key and model, streamed one second of synthetic silence through the relay, and terminated cleanly. Real microphone capture, speech accuracy, and end-of-turn timing still require the developer's browser test.

Sources: [AssemblyAI message sequence](https://www.assemblyai.com/docs/streaming/message-sequence), [streaming API](https://www.assemblyai.com/docs/streaming/api-spec/streaming-websocket), and [model selection](https://www.assemblyai.com/docs/streaming/select-the-speech-model).

### 11 — One recording control and newest turns first

**Choice (18 November 2026):** Use one button that switches between **Start recording** and **Stop recording**. Show new transcript turns at the top while keeping their original turn numbers.

**Reason:** Only one recording action is relevant at a time, and the latest speech should be visible without scrolling through older turns.

**Behavior:** The button can also cancel startup. It briefly shows **Stopping…** and is disabled while the final transcript is received, then resets on completion or error. Partial/final updates change the existing row rather than moving or duplicating it.

**Prior checkpoint confirmation:** The developer reported that microphone transcription works in their browser. Detailed accuracy and turn-detection evaluation remain open.

### 12 — Selectable models with a separate provider adapter

**Choice (18 November 2026):** Start with OpenAI via its Responses API. Add model
selection alongside language and tone. The developer selected GPT-5.4 mini as
the initial default and GPT-5.4 as a comparison option, and requested the ability
to add other providers later.

**Reason:** Compare response quality, latency, and cost using the same interview.
Keep provider SDK details outside interview instructions and frontend behavior.

**Implementation:** A backend model registry supplies the UI dropdown and validates
requests. A small asynchronous `TextProvider` interface separates interview logic
from the OpenAI adapter. Another provider needs an adapter, credentials, and model
entries; the interview endpoint and UI can remain the same. Only OpenAI is wired
up now. Model access is checked by the provider at request time, with no fallback.

**Checkpoint scope:** Completed transcript turns trigger written replies. The
browser owns temporary history and serializes requests; Python owns the interview
instructions. Settings are fixed per recording. The prompt covers the required
topics, uses German/English and professional/conversational phrasing, and asks one
question at a time. German tone uses the previously proposed Sie/du mapping.
Topic coverage and the one-follow-up rule need live evaluation.

**Tradeoffs:** Full-history requests are simple and make switching providers easier,
but input cost grows with conversation length and a page reload loses context.
Prompt-based progression is faster to build than a state machine but less
deterministic. Non-streamed text replies are easier to inspect at this checkpoint;
they do not establish the eventual spoken-response latency target. Both initial
models use reasoning effort `none`, short output limits, and no automatic retries.
OpenAI response storage is disabled, which does not guarantee zero provider retention.

**Alternatives:** Hard-code one model (simpler, cannot compare in the UI), put SDK
calls directly in the route (less separation), or introduce an orchestration
framework now (more dependencies before requirements justify them).

**Validation:** 17 Python and 10 JavaScript tests passed. Simulated-provider and
browser-logic tests cover dispatch, settings, context, failures, duplicate turns,
and cancellation, including dispatch to a simulated second provider. The
rebuilt Docker service is healthy; local HTTP checks confirmed the model catalog
and an actionable missing-key response without a provider call. The
developer will configure the OpenAI API key and billing the following morning;
live response quality, account access, and latency remain unverified.

Sources: [OpenAI text generation](https://developers.openai.com/api/docs/guides/text),
[GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini),
[GPT-5.4](https://developers.openai.com/api/docs/models/gpt-5.4).

### 13 — Add Gemini as the second interview provider

**Choice (19 November 2026):** Add Google's `gemini-3.8-flash` using the Interactions
API and make it the default selection. The developer configured `GEMINI_API_KEY`
after difficulties obtaining an OpenAI API key. Keep both OpenAI model choices.
This supersedes decision 12's initial default, while retaining its provider interface.

**Reason:** Make progress using the available API account and exercise the provider
boundary with a real second implementation. Model choice is practical here; no
comparative quality or latency advantage over OpenAI has been established.

**Implementation:** Add `GeminiProvider` and a model catalog entry in `app/llm.py`.
Use the async Google SDK so provider I/O does not block audio handling. Translate
our generic user/assistant history to Interactions user_input/model_output steps.
Keep interview instructions and browser request logic unchanged. The existing
model endpoint automatically exposes the additional dropdown option.

**Tradeoffs:** Another pinned SDK dependency and provider-specific request/error
handling. Stateless full-history calls preserve our simple cross-provider design;
provider-managed continuation and potential caching benefits remain deferred.
Use `store=False`, `thinking_level=low`, a 1,024-token output budget, one attempt,
and no automatic continuation. The shared prompt requests short spoken-style
answers. Response storage settings do not imply zero provider data retention.

**Validation:** 24 Python tests passed. Gemini tests use the actual pinned SDK with
a fake HTTP transport to verify serialized history, extracted text, sanitized
errors, missing keys, timeout handling, cancellation, and no retries/continuations.
The rebuilt service is healthy and exposes all three model choices. The first
live check returned the expected missing-key error before contacting Google:
the saved project `.env` did not yet contain `GEMINI_API_KEY`.

**Live follow-up (19 November 2026):** After the developer saved the key and the
container was recreated, authenticated metadata access for `gemini-3.8-flash`
succeeded in 0.38 seconds. Two interview-generation requests timed out. A minimal
"say hello" Interactions request, isolated from the interview prompt and given
a 45-second diagnostic timeout, returned HTTP 503 after 4.23 seconds. This points
to generation-service unavailability; successful generation and its quality or
latency remain unverified. No application timeout or model was changed.

Sources: [Google Interactions API](https://aistudio.google.com/docs/interactions-overview),
[thinking levels](https://aistudio.google.com/docs/thinking),
[Google Gen AI Python SDK](https://googleapis.github.io/python-genai/).

### 14 — Low-cost Anthropic model as the proof-of-concept default

**Choice (19 November 2026):** Add Anthropic using the configured `ANTHROPIC_API_KEY`
and select `claude-haiku-5-5` as the default. The developer has Anthropic API credit
and explicitly prioritizes a very cheap proof of concept. This supersedes decision
13's default; existing Gemini and OpenAI selections remain available.

**Reason:** Haiku 5.5 is the lowest-priced model in the current published Claude
lineup for short prompts. Standard prices checked today are $0.10 per million
input tokens and $0.50 per million output tokens for prompts up to 100,000 tokens;
longer prompts cost more. A 1,000-input/200-output-token request is approximately
$0.0002 before any other charges. Interview quality still requires evaluation.

**Implementation:** A third `TextProvider` implementation uses async Anthropic
Messages, the same generic message history, and the existing interview prompt.
Set thinking disabled, effort low, a 500-token output limit, and zero automatic
retries. Read only text content blocks and reject incomplete/refused responses.
No more expensive fallback is configured. API keys remain server-side.

**Tradeoffs:** Short, inexpensive replies may be less capable on nuanced answers.
Disabling thinking fits the existing text-only history format and avoids reasoning
token costs; richer reasoning or tool use would require revisiting this design.
History is resent per request, so input usage grows over the conversation.

**Validation:** 31 Python tests passed, including seven new Anthropic SDK/HTTP
transport tests for history, budget settings, missing keys, sanitized errors,
timeouts, refusals/truncation, cancellation, and default model selection.
The Docker service is healthy. One live request through our interview endpoint
returned a German professional-tone follow-up about a synthetic robot startup's
pilot deployments in 1.48 seconds. This is a single text-reply measurement, not
the complete voice latency or a broad assessment of interview quality.

Sources: [Haiku overview](https://platform.claude.com/docs/en/models/haiku-5-5/overview),
[pricing](https://platform.claude.com/docs/en/about-claude/pricing),
[thinking configuration](https://platform.claude.com/docs/en/models/haiku-5-5/whats-new-haiku-5-5),
[Python SDK](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python).

### 15 — ElevenLabs spoken replies with configurable Eric voice

**Choice (19 November 2026):** Use ElevenLabs Flash v2.5 (`eleven_flash_v2_5`)
and Eric (`cjVigY5qzO86Huf0OWal`) for both German and English initially. The developer
selected ElevenLabs, saved a key, enabled Text to Speech and Voices Read permissions,
and chose Eric as a starting voice. Set the voice/model through environment variables.

**Reason and alternatives:** We compared ElevenLabs, Cartesia, and Google TTS.
ElevenLabs offers a short integration path for multilingual conversational speech.
The voice choice is reversible; listen to German before deciding whether separate
language-specific voices are worthwhile.

**Implementation:** Add a small backend REST adapter and `/api/speech` endpoint.
Keep credentials server-side, bound text/audio size and timeouts, sanitize errors,
and avoid automatic paid retries. Use the existing `httpx2` dependency directly.
Show the text immediately, fetch a complete MP3, then play it through the microphone's
already-open AudioContext. Keep the next model request queued until playback finishes.

**Turn-taking:** Pause microphone forwarding from synthesis through playback and a
300 ms echo tail. Send silence frames to maintain the STT session. Stop cancels
pending replies and local audio immediately; final transcription can still complete.
This supersedes the earlier behavior that allowed written replies to finish after Stop.
TTS failure preserves the written reply and resumes listening.

**Tradeoffs:** Buffering is easier to understand/debug but adds latency; streaming
and voice interruptions are deferred. The user cannot talk over the agent at this
checkpoint. Silence still counts as STT session time. Cancelling a browser request
does not guarantee cancellation of provider billing. Eric's German pronunciation
and the full speech-to-speech latency need manual evaluation. Provider retention
is not overridden by our application.

**Validation:** 38 Python and 18 JavaScript tests passed. Two short synthetic
requests through the running `/api/speech` endpoint returned HTTP 200 and MP3
audio with Eric: German took 4.00 seconds and English 0.60 seconds. These single
full-download measurements do not establish language-specific performance or
end-to-end voice latency. Browser playback and pronunciation remain manual checks.

Source: [ElevenLabs text-to-speech API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert).

### 16 — Persist conversation text and structured results, without audio

**Choice:** Save conversations with start/end timestamps and settings (language,
tone, selected model), ordered messages identifying each speaker, and a structured
interview summary. Do not persist microphone recordings or generated speech as
part of conversation history. The developer explicitly agreed to this scope.

**Reason:** Page 1 of the challenge requires visible speaker-attributed transcripts,
accessible past conversations with timestamps, and a saved structured result.
Audio recordings are not requested. Text is sufficient for reviewing interviews
and generating summaries, while avoiding additional audio storage. Saving settings
supports reproducibility and is our design choice, rather than an explicit requirement.

**Summary scope:** Startup identity, team, product/development stage, traction,
market/competition, financing needs and planned round, plus sector and next step.
Missing information should remain explicitly unknown. Page 2 suggests example
fields under the tool-calling bonus; tool calling and those exact field names
are not mandatory. The precise schema and extraction approach remain to be agreed.

**Tradeoff:** We cannot replay the original interview audio to investigate a
transcription error. Audio is still processed temporarily by the pipeline;
this application storage decision does not change external provider retention.
The previously generated synthetic voice-test samples are local diagnostic files,
not saved conversation recordings.

**Status:** Scope agreed; persistence is not implemented. Database choice is
resolved by decision 17; the storage lifecycle remains open.

### 17 — SQLite for conversation persistence

**Choice:** Use SQLite for conversations, ordered messages, settings, and structured
summaries. The developer selected SQLite after comparing JSON files and PostgreSQL.

**Why it fits:** This prototype runs as one local FastAPI service with modest data
volume and short, infrequent writes. SQLite provides transactions, relational
constraints, indexes, and SQL queries without a separate database server, network
connection, database credentials, or another Compose service. Relationships between
conversations, messages, and summaries map naturally to relational storage. Its
small operational footprint fits the limited development time and local demonstration.

**Compared with JSON files:** Files are human-readable and useful for exports, but
we would need to implement safe concurrent updates, cross-record consistency, and
history lookup ourselves. SQLite supplies these database capabilities while retaining
local file-based storage. JSON remains a possible summary format or export format;
the database choice does not rule it out for structured content.

**Compared with PostgreSQL:** PostgreSQL is a stronger candidate for many concurrent
writers, multiple application servers, and a shared network database. For this
checkpoint, those benefits do not justify another service, connection configuration,
credentials, and operational setup. It remains a reasonable future migration target.

**Accepted limitations:** SQLite permits only one writer at a time; writes must stay
short, and external API calls must not run inside write transactions. Multiple users
are possible, but sustained write contention or deployment across multiple hosts
would trigger reassessment. A later PostgreSQL migration would still require schema,
query, and data migration work; it is not assumed to be automatic.

**Persistence:** Store the database outside the container's disposable writable layer
using persistent Docker storage. This preserves it across app container replacement,
and requires a separate backup. We chose a bind mount from `./data` to `/app/data`
so the developer can open `data/interviews.sqlite` directly on Windows. Conversation
data stays out of Git; the existing ignore rules cover database files and local data.

**Status:** Database engine selected; implementation has not started.

Reference: [SQLite appropriate uses and concurrency limits](https://www.sqlite.org/whentouse.html).

### 18 — Use the saved transcript as interview context

The transcription relay commits each finalized founder turn to SQLite before
notifying the browser. The browser requests a reply by conversation and turn ID.
FastAPI loads settings and ordered messages, releases the database connection,
calls the model, and commits its answer before playback. A failed model request
leaves the founder's words available. When a newer final turn arrives during
generation, the queued request uses the updated transcript. A superseded model
request can still incur a charge.

### 19 — Read-only interview history

Open past interviews in a separate browser tab so the live recording can continue.
List ended and interrupted sessions by start time, newest first. The archive shows
saved messages in speaking order with speaker labels and the original session
settings. Refreshing reads SQLite again. Viewing a transcript makes no provider calls.

## Open decisions

- Evaluate Haiku interview quality and latency; compare other providers when available.
- Evaluate Eric in German/English and decide whether separate voices are needed.
- Tune AssemblyAI turn detection against actual German/English founder answers.
- Whether a voice orchestration framework will help once LLM/TTS and interruptions are added.
- Backup approach for the local database.
- Interview state management, summary schema, and whether to use tool calling.
- Demonstration environment.

## How to maintain this log

Add the date, choice, reason, alternatives, tradeoff, and relevant validation when a new decision is agreed. If a choice changes, mark the earlier decision as superseded and explain why. Keep proposals distinct from agreed decisions and measured results distinct from expectations.
