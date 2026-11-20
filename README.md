# HTGF startup interview agent

An incremental implementation of the AI voice-agent coding challenge.

**Current checkpoint:** microphone transcription plus written and spoken interview replies.
The browser sends PCM audio through FastAPI to AssemblyAI. Completed turns go
to the selected Anthropic, Gemini, or OpenAI model with conversation context, language, and tone.
ElevenLabs reads each reply aloud using Eric and Flash v2.5.
The UI follows HTGF's palette (see `UI_STYLE.md`).

FastAPI saves finalized turns, generated replies and session settings to
`data/interviews.sqlite`. Docker mounts the project's data folder at `/app/data`.
Use **Past interviews** to open the read-only history in a separate tab. Select a
timestamp to see the saved settings and transcript, including interrupted sessions.
Use **Refresh history** to pick up newly ended sessions. Structured summaries are
the next checkpoint.

## Run locally with Docker

Start Docker Desktop, then open PowerShell in the project directory:

```powershell
cd C:\Users\kfrei\Code\HTGF_coding_challenge
```

If `.env` does not exist yet, copy the placeholder template:

```powershell
Copy-Item .env.example .env
```

Edit `.env` locally and set `ASSEMBLYAI_API_KEY` for transcription, plus
`ANTHROPIC_API_KEY` for Claude, `GEMINI_API_KEY` for Gemini, and/or
`OPENAI_API_KEY` for OpenAI replies. Set `ELEVENLABS_API_KEY` for spoken replies
(Text to Speech permission; Voices Read is useful for browsing voices). You only
need the key for the selected interview provider. If you already have `.env`, add the missing entry
without copying over the existing file. Keep the keys private. Compose loads
them into the backend at runtime; `.gitignore` excludes
it from Git and `.dockerignore` excludes it from the image. The page can load
without keys. A missing AssemblyAI key prevents transcription; a missing key for
the selected interview provider produces a clear reply error while transcription continues.

```powershell
docker compose up --build
```

The first build downloads Python and installs dependencies. Once Uvicorn reports
that it is running, open:

- Application: <http://localhost:8000>
- Health response: <http://localhost:8000/health>
- Interactive HTTP API documentation: <http://localhost:8000/docs>

Select language, tone, and model, click **Start recording**, allow microphone
access, and wait for **Listening** before speaking. The same button switches to
**Stop recording**; click it to release the
microphone and finish the final transcript. The browser microphone indicator
should turn off. Use a current Chrome or Edge browser for the first manual test.
Microphone capture requires localhost or HTTPS.

The button briefly shows **Stopping…** while the last transcript is received,
then returns to **Start recording**. New turns appear at the top; updates to an
existing turn replace its text in place without changing its position.
Introduce your startup first, then listen to the interviewer's question and answer
aloud once the status returns to **Listening**. Replies also appear in the conversation
with an **Interviewer** label. Microphone forwarding pauses while speech is generated
and played; this checkpoint does not support interrupting the interviewer by speaking.
Settings stay fixed during recording and apply to the next recording when changed.
Stopping releases the microphone, stops playback, and cancels pending replies.
The final transcript still arrives, but does not trigger a new reply after Stop.

The health endpoint returns `{"status":"ok"}`. It checks only our application,
not provider availability or whether the API key is valid. HTTP API docs do not
describe the WebSocket protocol; see the flow below.

Stop with `Ctrl+C`, then remove the stopped service container and its network:

```powershell
docker compose down
```

After editing source files, rerun `docker compose up --build`. This initial setup
copies source into the image; it has no live-reload bind mount.

After changing only `.env`, recreate the container so it receives the new values:

```powershell
docker compose up -d --force-recreate
```

## How the pieces fit together

```text
Browser on localhost:8000
    -> Docker's published port 8000
    -> Uvicorn (the HTTP/ASGI server)
    -> FastAPI (routing and application logic)
         /            -> index.html
         /static/...  -> CSS and JavaScript
         /health      -> {"status": "ok"}

Browser microphone -> AudioWorklet -> 100 ms mono PCM chunks
    -> /ws/transcribe (FastAPI WebSocket)
    -> AssemblyAI streaming WebSocket
    -> partial/final transcript events -> browser

Completed transcript -> browser interview queue (one request at a time)
    -> POST /api/interview/reply (conversation ID + saved turn ID)
    -> read settings and ordered transcript from SQLite
    -> interview instructions -> selected provider adapter
    -> Anthropic Messages API, Gemini Interactions API, or OpenAI Responses API
    -> written reply -> browser conversation
    -> POST /api/speech (reply text + language)
    -> ElevenLabs Flash v2.5 -> complete MP3 -> browser AudioContext playback
```

| File | Purpose |
| --- | --- |
| `app/main.py` | Defines the FastAPI application and routes. |
| `app/transcription.py` | Opens the authenticated STT session and relays audio/transcript events. |
| `app/interview.py` | Validates settings/history and builds language/tone-aware interview instructions. |
| `app/llm.py` | Defines the model catalog, provider interface, and Anthropic/Gemini/OpenAI adapters. |
| `app/speech.py` | Validates speech requests and calls ElevenLabs with server-side voice configuration. |
| `app/static/index.html` | Provides the page structure. |
| `app/static/styles.css` | Styles the page. |
| `app/static/app.js` | Manages Start/Stop, connection state, and transcript updates. |
| `app/static/interview.js` | Deduplicates final turns and queues replies by conversation and turn ID. |
| `app/storage.py` | Saves finalized turns and settings and reads the ordered model context. |
| `app/static/speech.js` | Fetches/decodes audio, controls playback, and gates microphone forwarding. |
| `app/static/microphone.js` | Requests microphone access and manages the Web Audio graph. |
| `app/static/pcm-worklet.js` | Converts samples to little-endian 16-bit mono PCM, with no audible output. |
| `requirements.txt` | Pins the direct Python dependencies. |
| `Dockerfile` | Builds a Python image and starts Uvicorn as a non-root user. |
| `compose.yaml` | Defines the service, local port mapping, and health check. |
| `.dockerignore` | Limits which files are sent to Docker during a build. |
| `.gitignore` | Excludes local secrets and generated files from Git. |
| `.env.example` | Documents runtime settings without real credentials. |
| `DECISIONS.md` | Records design choices and their tradeoffs. |
| `UI_STYLE.md` | Records the HTGF palette and standing rules for UI styling. |

Uvicorn listens on `0.0.0.0` **inside** the container so Docker can reach it.
Compose publishes the port on `127.0.0.1` **on the host**, limiting access to the
local machine. Frontend and API share an origin, so no CORS configuration is needed.

Python 3.13 is the starting runtime. Direct dependencies are pinned; transitive
dependencies and the base-image tag are not fully locked yet.

The AudioWorklet uses the AudioContext's actual sample rate (typically 44.1 or
48 kHz) and communicates that rate to the backend. Supported rates are 8–48 kHz.
It mixes channels to mono and sends binary frames, including silence for turn
detection. On Stop, it pads and sends its final partial audio chunk before the
stop command. FastAPI sends `Terminate`, waits for final transcript events and
provider termination, then acknowledges the stop. A stable turn ID lets the UI
replace partial text instead of duplicating sentences.

The default model is `assemblyai-stt-3-7-realtime-agent` in `balanced` mode,
using the provider's global endpoint. The selection biases recognition toward
German (`de`) or English (`en`); it is not translation. The model can be changed
via `ASSEMBLYAI_SPEECH_MODEL` after checking the provider's supported parameters.

Sessions are limited to 10 minutes. Disconnects and errors terminate the provider
session; missing audio is timed out after 20 seconds. AssemblyAI bills session
duration, including silence. The application stores transcript text locally and discards audio.
This is a localhost prototype with an origin check, not a public service
with user authentication.

Provider references: [streaming protocol](https://www.assemblyai.com/docs/streaming/message-sequence),
[model selection](https://www.assemblyai.com/docs/streaming/select-the-speech-model),
[language configuration](https://www.assemblyai.com/docs/streaming/multilingual-transcription).

## Models and provider modularity

`GET /api/interview/models` supplies the dropdown from `MODELS` in `app/llm.py`.
The choices are `claude-haiku-5-5` (default), `gemini-3.8-flash`, `gpt-5.4-mini`,
and `gpt-5.4`. Claude uses Anthropic's asynchronous Messages API with thinking
disabled, low effort, a 500-token output cap, and no automatic retries.
Its adapter passes history as user/assistant messages and instructions as `system`.
It extracts text blocks and rejects truncated, empty, or refused replies.
The default prioritizes proof-of-concept cost: Haiku 5.5's standard price checked
on 19 November 2026 is $0.10 per million input tokens and $0.50 per million output
tokens for prompts up to 100,000 tokens. Longer prompts use higher rates.
An illustrative 1,000-input/200-output-token call is $0.0002; full history counts
again on subsequent requests. This is an estimate, not measured account billing.
Gemini uses Google's asynchronous Interactions API with `thinking_level=low`
and a 1,024-token output budget. The OpenAI models use the Responses API with
reasoning effort `none` and a 500-token output cap. The shared interview prompt
requests 1-3 short sentences. Model availability still depends on the API project's access
and credits; the catalog is a configured allowlist, not an account access check.

To add another OpenAI model, add a `ModelOption` with its model ID and supported
parameters. To add a different provider, implement the asynchronous `TextProvider`
interface, register its instance in `PROVIDERS`, and add its model entries.
Keep its credentials in environment variables and translate provider errors into
`ReplyError`. The UI displays the provider alongside each model automatically.
Anthropic, Gemini, and OpenAI adapters are implemented. The Gemini adapter translates our
`user`/`assistant` messages into `user_input`/`model_output` steps, preserving
their order. It explicitly reads `GEMINI_API_KEY`; no key enters the browser.
Google's SDK is pinned, including its Interactions-specific exception handling.

The backend owns instructions and accepts only user/assistant history, configured
models, German/English, and professional/conversational tone. German professional
uses Sie; conversational uses du. Unknown models and oversized history are
rejected before a paid call. Full conversation history is sent on each request;
we cap it at 120 messages, 8,000 characters per message, and 60,000 in total.

Partial transcripts never trigger generation. Repeated final events for a turn
are deduplicated. Speech finalized while a request is pending is queued for the
next reply. Failed replies pause generation for that recording; there are no
automatic retries, automatic Gemini continuation requests, or silent model fallbacks.
A successful new recording cancels
the old browser request and ignores late replies. Aborting a browser request
does not guarantee that an already-started provider request stops billing.

OpenAI and Gemini use `store=False`; Anthropic's Messages requests are stateless
and receive the full history each time. These choices are not a promise
of zero provider retention. A page reload ends the live interview. SQLite retains
committed messages. On startup the single app worker marks abandoned sessions interrupted.
Prompted topic coverage and follow-up limits need live evaluation; they are not
deterministic workflow guarantees. Full-pipeline latency still needs measurement and tuning.

References: [OpenAI text generation](https://developers.openai.com/api/docs/guides/text),
[GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini),
[GPT-5.4](https://developers.openai.com/api/docs/models/gpt-5.4).
Gemini references: [Interactions API](https://aistudio.google.com/docs/interactions-overview),
[thinking levels](https://aistudio.google.com/docs/thinking), and
[Python SDK](https://googleapis.github.io/python-genai/).
Anthropic references: [Haiku 5.5](https://platform.claude.com/docs/en/models/haiku-5-5/overview),
[pricing](https://platform.claude.com/docs/en/about-claude/pricing), and
[Python SDK](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python).

## Spoken replies

The backend defaults to Eric (`cjVigY5qzO86Huf0OWal`) with `eleven_flash_v2_5`.
To change the voice, set `ELEVENLABS_VOICE_ID` in `.env` and recreate the container;
no source edit or image rebuild is needed. `ELEVENLABS_TTS_MODEL` is also configurable.
Both German and English pass an explicit language code to ElevenLabs. Eric's
voice is English-labelled; German pronunciation and preferred speaking style need
a listening test before choosing language-specific voices.

We call the small ElevenLabs REST surface directly using `httpx2`, already used by
the model SDKs and now pinned as a direct dependency. The endpoint accepts at most
4,000 characters and returns MP3 at 44.1 kHz / 128 kbps with `Cache-Control: no-store`.
Errors are sanitized, responses are size/time bounded, and no paid request is
automatically retried. If synthesis or playback fails, the text remains visible
and the microphone resumes forwarding. Stop cancels the browser request and
immediately stops local playback; an already-started provider call may still bill.

The browser reuses the AudioContext opened by the Start button. This avoids a
separate autoplaying audio element. While synthesizing/playing, it sends zeroed PCM
frames to STT, keeping the connection alive without feeding speaker audio back
into recognition. It waits another 300 ms after playback to cover buffered capture
and speaker echo. This is simple turn-taking, not voice interruption handling.
STT session time remains billable during silence. The interview queue waits for
playback before issuing another model request. Microphone capture stays open until
Stop even while forwarding is paused.

This checkpoint buffers a complete model reply and a complete MP3 before playback.
It makes cancellation and sequencing easier to inspect, but adds latency compared
with streaming text/audio. We have not established the PDF's <1–2 second target.
No generated audio is saved by the application; provider retention follows their
account policies. Structured summaries are planned for the next checkpoint.

Reference: [ElevenLabs text-to-speech API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert).

## Useful checks

```powershell
docker compose ps
docker compose logs app
Invoke-RestMethod http://localhost:8000/health
```

If port 8000 is occupied, change the mapping in `compose.yaml` to
`127.0.0.1:8001:8000` and open `http://localhost:8001` instead.

## Automated and manual validation

From PowerShell in the project directory, after building the image:

```powershell
docker compose run --rm --no-deps -v "${PWD}/tests:/tests:ro" app python -m unittest discover -s /tests -v
docker run --rm --mount "type=bind,source=$PWD,target=/work,readonly" --workdir /work node:22-slim node --test tests/browser-logic.test.cjs tests/interview-logic.test.cjs tests/speech-logic.test.cjs
```

These tests simulate the provider/browser to check final transcript delivery,
disconnect cleanup, invalid requests, timeouts, PCM conversion at three sample
rates, duplicate partial updates, cancellation, and restart. They do not spend
API credits. Interview tests cover model/provider dispatch, validation, SDK error
handling, final-turn deduplication, sequential history, and ignoring stale replies.
Node is used only for these tests, not by the application.

Earlier transcription validation: 9 Python and 6 JavaScript checks passed. A real provider
session accepted the configured model/key, received one second of synthetic
silence through the relay, and terminated cleanly. This verifies connectivity,
not actual speech accuracy or end-of-turn timing.

Manual browser checks still required:

1. German: say “Wir entwickeln Software für Krankenhäuser.”
2. Try “Wir suchen … [pause] … fünfhunderttausend Euro.” Observe whether the pause
   prematurely finishes the turn. Repeat with a longer answer.
3. Stop, switch to English, restart, and say “We are raising five hundred thousand euros.”
4. Stop immediately after speech and confirm the final words are retained.
5. Deny microphone permission or disconnect the microphone and confirm a clear
   error and a usable Start button. Stop must release the microphone indicator.
6. With the selected provider's API key configured, introduce your startup and confirm a relevant
   written follow-up. Give a team fact and check that later replies remember it.
7. Start fresh recordings with each model and both tones/languages; check German
   Sie/du usage and that the selected model appears on replies.
8. Check that replies play aloud in both languages and that Eric's own speech does
   not appear as a founder turn. The microphone meter should stay at zero while
   speech is generated/played, then resume when the status says Listening.
9. Stop while a model reply is pending, during speech generation, and during playback:
   no late reply/audio should appear, and playback should stop immediately.
   Start another recording and confirm a fresh conversation without stale audio.
10. Test with speakers as well as headphones. Check German names, numbers, and
    English startup terminology. Measure from the end of your speech to audible playback.

Previous backend checkpoint: 31 Python tests passed, including seven Anthropic
and seven Gemini tests using real SDKs with fake HTTP transports. They check
history serialization, reply extraction, missing keys, sanitized errors, timeouts,
cancellation, output limits, and disabled retries/continuations.
The previous frontend checkpoint's 10 JavaScript tests passed.
The rebuilt service is healthy and its catalog defaults to Haiku with all four
models available. One live request through `/api/interview/reply` using synthetic
startup history returned a relevant German follow-up in 1.48 seconds on 19 November.
This verifies Haiku connectivity and a basic reply; it does not establish interview
quality across conversations or end-of-speech-to-audio latency.
On 19 November, after loading the saved Gemini key, authenticated metadata
access for `gemini-3.8-flash` succeeded. Two interview-generation requests timed
out; an isolated short Interactions request returned HTTP 503. Successful live
generation, interview quality, and latency remain unverified. The application
timeout was not increased to hide the failure.
OpenAI still has simulated-response validation only; live account access remains
unverified until an OpenAI key is configured.

TTS checkpoint (19 November): all 38 Python and 18 JavaScript tests passed.
New checks cover the synthesis request contract, language/voice configuration,
errors, input bounds, silence forwarding, sequential playback, and cancellation
during fetch, decoding, playback, and the echo tail. The rebuilt app is healthy.
Two synthetic requests through `/api/speech` returned HTTP 200 and MP3 data using
the saved key: the German sample took 4.00 seconds; the English sample
took 0.60 seconds. These are single full-download timings, not a language comparison
or end-to-end latency benchmark. Local samples are in ignored `recordings/eric-de.mp3`
and `recordings/eric-en.mp3`. Browser audibility, autoplay behavior, pronunciation,
and acoustic echo still need the manual checks above.

Keep individual API timing observations separate from the full
end-of-speech-to-spoken-reply latency measured in the browser.

## GitHub backup

Local commits are backed up only after they are pushed:

```powershell
git status
git add <specific-files>
git commit -m "Describe the change"
git push
```

Keep API keys in local environment files when integrations are added. Never put
keys in frontend JavaScript or commit them. `.env.example` may contain placeholder
values for documentation.
