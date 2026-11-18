# HTGF startup interview agent

An incremental implementation of the AI voice-agent coding challenge.

**Current checkpoint:** a FastAPI backend serves a plain HTML/CSS/JavaScript
page. The page calls `/health` and displays whether the backend responds.
Microphone input, AssemblyAI, LLM/TTS calls, settings, and persistence are not
implemented yet. No API keys are needed for this checkpoint.

## Run locally with Docker

Start Docker Desktop, then open PowerShell in the project directory:

```powershell
cd C:\Users\kfrei\Code\HTGF_coding_challenge
docker compose up --build
```

The first build downloads Python and installs dependencies. Once Uvicorn reports
that it is running, open:

- Application: <http://localhost:8000>
- Health response: <http://localhost:8000/health>
- Interactive HTTP API documentation: <http://localhost:8000/docs>

The page should show **Connected. The application is responding.** The health
endpoint returns `{"status":"ok"}`. This only checks our application, not external
AI services. The **Check connection** button repeats the browser-to-backend call.

Stop with `Ctrl+C`, then remove the stopped service container and its network:

```powershell
docker compose down
```

After editing source files, rerun `docker compose up --build`. This initial setup
copies source into the image; it has no live-reload bind mount.

## How the pieces fit together

```text
Browser on localhost:8000
    -> Docker's published port 8000
    -> Uvicorn (the HTTP/ASGI server)
    -> FastAPI (routing and application logic)
         /            -> index.html
         /static/...  -> CSS and JavaScript
         /health      -> {"status": "ok"}
```

| File | Purpose |
| --- | --- |
| `app/main.py` | Defines the FastAPI application and routes. |
| `app/static/index.html` | Provides the page structure. |
| `app/static/styles.css` | Styles the page. |
| `app/static/app.js` | Calls `/health` and updates the connection message. |
| `requirements.txt` | Pins the direct Python dependencies. |
| `Dockerfile` | Builds a Python image and starts Uvicorn as a non-root user. |
| `compose.yaml` | Defines the service, local port mapping, and health check. |
| `.dockerignore` | Limits which files are sent to Docker during a build. |
| `.gitignore` | Excludes local secrets and generated files from Git. |
| `DECISIONS.md` | Records design choices and their tradeoffs. |
| `UI_STYLE.md` | Records the HTGF palette and standing rules for UI styling. |

Uvicorn listens on `0.0.0.0` **inside** the container so Docker can reach it.
Compose publishes the port on `127.0.0.1` **on the host**, limiting access to the
local machine. Frontend and API share an origin, so no CORS configuration is needed.

Python 3.13 is the starting runtime. Direct dependencies are pinned; transitive
dependencies and the base-image tag are not fully locked yet.

## Useful checks

```powershell
docker compose ps
docker compose logs app
Invoke-RestMethod http://localhost:8000/health
```

If port 8000 is occupied, change the mapping in `compose.yaml` to
`127.0.0.1:8001:8000` and open `http://localhost:8001` instead.

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
