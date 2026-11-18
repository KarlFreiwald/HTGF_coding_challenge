# HTGF startup interview agent

An incremental implementation of the AI voice-agent coding challenge.

**Current checkpoint:** live microphone transcription in German or English.
The browser sends PCM audio through FastAPI to AssemblyAI and displays partial
and completed turns. The UI follows HTGF's palette (see `UI_STYLE.md`).

LLM replies, TTS, tone selection, interview logic, and persistent conversation
history are not implemented yet. Transcripts stay in the current browser tab;
starting a successful new recording replaces the previous transcript.

## Run locally with Docker

Start Docker Desktop, then open PowerShell in the project directory:

```powershell
cd C:\Users\kfrei\Code\HTGF_coding_challenge
```

If `.env` does not exist yet, copy the placeholder template:

```powershell
Copy-Item .env.example .env
```

Edit `.env` locally and set `ASSEMBLYAI_API_KEY` to your AssemblyAI key. Keep the
key private. Compose loads it into the backend at runtime; `.gitignore` excludes
it from Git and `.dockerignore` excludes it from the image. The page can load
without a key, but starting transcription reports a configuration error.

```powershell
docker compose up --build
```

The first build downloads Python and installs dependencies. Once Uvicorn reports
that it is running, open:

- Application: <http://localhost:8000>
- Health response: <http://localhost:8000/health>
- Interactive HTTP API documentation: <http://localhost:8000/docs>

Select **Deutsch** or **English**, click **Start recording**, allow microphone
access, and wait for **Listening** before speaking. The same button switches to
**Stop recording**; click it to release the
microphone and finish the final transcript. The browser microphone indicator
should turn off. Use a current Chrome or Edge browser for the first manual test.
Microphone capture requires localhost or HTTPS.

The button briefly shows **Stopping…** while the last transcript is received,
then returns to **Start recording**. New turns appear at the top; updates to an
existing turn replace its text in place without changing its position.

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
```

| File | Purpose |
| --- | --- |
| `app/main.py` | Defines the FastAPI application and routes. |
| `app/transcription.py` | Opens the authenticated STT session and relays audio/transcript events. |
| `app/static/index.html` | Provides the page structure. |
| `app/static/styles.css` | Styles the page. |
| `app/static/app.js` | Manages Start/Stop, connection state, and transcript updates. |
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
duration, including silence. Our application does not write audio or transcripts
to disk. This is a localhost prototype with an origin check, not a public service
with user authentication.

Provider references: [streaming protocol](https://www.assemblyai.com/docs/streaming/message-sequence),
[model selection](https://www.assemblyai.com/docs/streaming/select-the-speech-model),
[language configuration](https://www.assemblyai.com/docs/streaming/multilingual-transcription).

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
docker run --rm --mount "type=bind,source=$PWD,target=/work,readonly" --workdir /work node:22-slim node --test tests/browser-logic.test.cjs
```

These tests simulate the provider/browser to check final transcript delivery,
disconnect cleanup, invalid requests, timeouts, PCM conversion at three sample
rates, duplicate partial updates, cancellation, and restart. They do not spend
API credits. Node is used only for these tests, not by the application.

Validation completed: 9 Python and 6 JavaScript checks passed. A real provider
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

Keep timing observations separate from the full end-of-speech-to-spoken-reply
latency target, which cannot be measured until LLM and TTS are connected.

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
