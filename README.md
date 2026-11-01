# TwitterMcp

Local-first analysis of posts on X.com: the text, the images and what is said
in the videos. Paste a post URL and get a summary, key points, who said what
(with timestamps), topics and claims worth checking — in the language you ask
for.

Everything runs on your machine: videos are transcribed with
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) and analyzed by
Gemma 4 through [Ollama](https://ollama.com). The results are offered as
[MCP](https://modelcontextprotocol.io) tools, so any MCP client can use them:
Claude Desktop, Claude Code, Open WebUI, a LangGraph agent.

```
post URL ─► syndication JSON (text, author, media)
          ├► photos ─────────────► Gemma vision ─► image notes ─┐
          └► videos (yt-dlp) ─┬─► keyframes ─► Gemma vision ────┤
                              └─► Whisper ─► [mm:ss] transcript ┴─► Gemma ─► analysis
                                         (every step cached in SQLite)
```

## Requirements

- Windows 11 (Linux/macOS work too), Python 3.12, GNU make
- [Ollama](https://ollama.com) with a Gemma 4 model: `ollama pull gemma4:e4b`
- An NVIDIA GPU is optional; Whisper falls back to the CPU

## Development environment

```bash
make venv
make test
```

For GPU transcription on Windows, add the CUDA runtime DLLs once:

```bash
.venv\Scripts\python -m pip install -e ".[dev,cuda]"
```

The Whisper model (`large-v3-turbo`, about 1.6 GB) is downloaded from Hugging
Face on first use. IntelliJ IDEA setup: [docs/intellij.md](docs/intellij.md).

## Command line

```bash
.venv\Scripts\python -m twittermcp post https://x.com/user/status/123
.venv\Scripts\python -m twittermcp transcribe https://x.com/user/status/123
.venv\Scripts\python -m twittermcp analyze https://x.com/user/status/123 --lang sk -q "What is the main claim?"
```

## MCP server

Tools: `get_post`, `transcribe_post`, `analyze_post`, `recent_analyses`.

**stdio** — the client starts the server itself. Claude Code:

```bash
claude mcp add twitter -- C:\path\to\TwitterMcp\.venv\Scripts\python.exe -m twittermcp serve
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "twitter": {
      "command": "C:\\path\\to\\TwitterMcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "twittermcp", "serve"]
    }
  }
}
```

**HTTP** — one long-running server for several clients:

```bash
make run    # http://127.0.0.1:8600/mcp
```

The HTTP endpoint has no authentication and listens on 127.0.0.1 only. To
use it from the Claude mobile app or ChatGPT it has to be reachable over
HTTPS (e.g. Cloudflare Tunnel) **and** protected with OAuth first — not done
yet. Note that the analysis is local, but whatever a tool returns is then
seen by the cloud model of that client.

## Posts that need a login

Public posts work without any account. For posts that are only visible when
logged in, give yt-dlp your X.com session through cookies — your password is
never needed:

| Variable | Value |
|---|---|
| `TWITTERMCP_COOKIES_BROWSER` | `firefox` (Chrome on Windows encrypts cookies so yt-dlp cannot read them) |
| `TWITTERMCP_COOKIES` | path to a Netscape `cookies.txt` exported from the browser |

Keep `cookies.txt` out of git (it is in `.gitignore`): it gives full access
to your account. The tool fetches single posts on request only; it does not
crawl timelines, which would break X's terms and risk the account.

## Configuration

| Variable | Default |
|---|---|
| `OLLAMA_URL` | `http://localhost:11434` |
| `GEMMA_MODEL` | `gemma4:e4b` (`gemma4:26b-a4b-it-qat` is more accurate) |
| `GEMMA_NUM_CTX` | `32768` |
| `WHISPER_MODEL` | `large-v3-turbo` |
| `WHISPER_DEVICE` | `cuda` (falls back to `cpu`) |
| `TWITTERMCP_DATA` | `data/` in the project: media and the cache database |

---

© 2026 Taras Bulubas. All rights reserved. See [LICENSE](LICENSE).
