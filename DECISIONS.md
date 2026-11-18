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

## Open decisions

- LLM provider and model.
- TTS provider, model, and voices for both languages.
- Exact AssemblyAI streaming model, audio format, and turn-detection configuration.
- Browser/backend audio transport and whether to use a voice orchestration framework.
- Storage for transcripts, timestamps, settings, and structured summaries.
- Interview state management, summary schema, and whether to use tool calling.
- Demonstration environment.

## How to maintain this log

Add the date, choice, reason, alternatives, tradeoff, and relevant validation when a new decision is agreed. If a choice changes, mark the earlier decision as superseded and explain why. Keep proposals distinct from agreed decisions and measured results distinct from expectations.
