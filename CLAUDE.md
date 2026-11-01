# TwitterMcp — project guide for Claude

Local-first analysis of single X.com posts: text, images and video. Videos are
transcribed with Whisper and summarized by a local Gemma model via Ollama;
nothing goes to a cloud LLM from this project. The results are exposed as MCP
tools, so Claude, ChatGPT, Open WebUI or a LangGraph workflow can use them.

It is the first of several MCP servers the user plans to combine into
agentic workflows on their own hardware, so keep the core reusable.

## Privacy and account safety (read first)

- **Never read `cookies*.txt`, `.env`, or `data/`.** The cookies are the user's
  X.com session; `data/` holds downloaded media and the cache database.
  Cookies are only passed to yt-dlp (`config.cookie_options()`), never read,
  logged or returned by a tool.
- **Single posts on request, no crawling.** The project fetches one post per
  user request. Do not add timeline, search or follower scraping: it breaks
  X's terms and can get the user's account suspended.
- Tests and fixtures use invented posts only.
- Before any commit, confirm `git status` shows code files only.

## Stack

- Python 3.12, FastMCP (stdio + Streamable HTTP), SQLite
- yt-dlp (video download), PyAV + Pillow (frames, images), faster-whisper
  (`large-v3-turbo`, CUDA with CPU fallback)
- Local LLM: Gemma 4 via Ollama at `http://localhost:11434`
  (`gemma4:e4b` default, `gemma4:26b-a4b-it-qat` for better accuracy;
  `GEMMA_MODEL`, `GEMMA_NUM_CTX`)
- HTTP server at `http://127.0.0.1:8600/mcp`

## Layout

Same standard as `Financie`, `PlanningRopeBridge` and the other sibling
projects: `src/` package, `pyproject.toml`, Makefile, pytest, shared IntelliJ
run configs, copyright header in every source file.

The package is split into an interface-free **core** and thin **adapters**.
The core never imports MCP, argparse or a web framework; adapters contain no
logic of their own. A new interface (web UI, LangGraph node) is a new adapter.

| File | Purpose |
|---|---|
| `src/twittermcp/core/xpost.py` | post URL → id, syndication fetch, `Post`/`Media`, yt-dlp fallback with cookies |
| `src/twittermcp/core/media.py` | photo/video download, keyframes, image scaling |
| `src/twittermcp/core/transcribe.py` | faster-whisper, `Transcript` with `[mm:ss]` lines |
| `src/twittermcp/core/gemma.py` | Ollama client (same as Financie's) |
| `src/twittermcp/core/analyze.py` | LLM prompts: image/frame descriptions, chunked transcript notes, summary schema |
| `src/twittermcp/core/pipeline.py` | the use cases `get_post`, `transcripts`, `image_notes`, `analyze_post`, each step cached |
| `src/twittermcp/core/db.py` | SQLite cache, schema version and migrations |
| `src/twittermcp/core/config.py` | `DATA_DIR`, cookie settings (env variables) |
| `src/twittermcp/mcp_server.py` | MCP adapter: the tools, `init_db()` in the lifespan |
| `src/twittermcp/cli.py` | `python -m twittermcp serve / post / transcribe / analyze` |
| `tests/` | pytest; `conftest.py` isolates `data/`, blocks the network and disables Ollama |

## Conventions

- **Facts come from code, text from the LLM.** Author, date, media, durations
  and timestamps are taken from the post and Whisper; Gemma only describes,
  condenses and summarizes. Never ask the model for something the data has.
- **Everything slow is cached** in SQLite, keyed by the model name (Whisper or
  Gemma), so a changed model gives fresh results. A repeated call does only
  the work that is missing; `refresh=True` re-fetches the post and re-analyzes.
- **Tool errors carry a code** (`invalid_url`, `not_found`, `unavailable`,
  `ollama_unavailable`): `PostError.code` in the core, `ToolError("<code>: …")`
  in the MCP adapter.
- **stdio is sacred.** In `serve` without `--http`, stdout is the MCP channel:
  no `print` in the core; progress goes through the `progress` callback.
- **HTTP binds 127.0.0.1 and has no auth.** Before it is exposed through a
  tunnel (Cloudflare Tunnel / Tailscale Funnel, for Claude Android or ChatGPT),
  OAuth must be added (FastMCP `auth=`). Never bind 0.0.0.0 without it.
- **Language:** talk to the user in Slovak. All code, comments, docstrings,
  log messages, LLM prompts, the README and other docs are in English. The
  output language of an analysis is a parameter (`language`, default `en`).
- **Schema changes go through migrations** (`SCHEMA_VERSION`, `MIGRATIONS` in
  `db.py`); `init_db()` backs the database up before upgrading. The database
  is only a cache, but transcripts are expensive to redo.
- **Shared code across MCP servers** (Ollama client, auth, config) is extracted
  into its own package only once a second server needs it.

## Running and testing

```bash
make venv      # .venv with Python 3.12 via the py launcher, editable install with [dev]
make test
make run       # MCP server over HTTP; stdio: .venv\Scripts\python -m twittermcp serve
```

GPU transcription on Windows needs the CUDA DLLs:
`.venv\Scripts\python -m pip install -e ".[dev,cuda]"`. Without them Whisper
runs on the CPU (slower, same result).

The user is on Windows 11 and uses the local `.venv`; do not use or suggest
conda. Dependencies live in `pyproject.toml` only; after changing them run
`make venv`.
