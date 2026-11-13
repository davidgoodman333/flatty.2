# Flatty

Flatty helps students find a rental in Bern. It has a React front-end (Vite, Tailwind CSS) and a local Python back-end (FastAPI, scikit-learn, and an optional local LLM through Ollama). For how the back-end works, see [backend/README.md](backend/README.md). For every use of AI in the prototype and how far each one is, see [AI_USE_CASES.md](AI_USE_CASES.md).

## Set up on a new Mac

### One command

Open Terminal, go to the folder where you want the project, and paste:

```bash
(command -v brew >/dev/null || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)") && \
eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)" && \
brew install git node@22 pnpm python@3.13 ollama && \
brew link --force --overwrite node@22 && \
git clone https://github.com/davidgoodman333/flatty.2.git flatty && cd flatty && \
pnpm install && \
python3.13 -m venv backend/.venv && \
backend/.venv/bin/pip install --upgrade pip && \
backend/.venv/bin/pip install -r backend/requirements.txt && \
brew services start ollama && sleep 5 && \
ollama pull qwen3:8b
```

The command asks for your Mac password once, while Homebrew installs. Expect it to take 10–20 minutes. Most of that time is the 5 GB AI model.

### What it does, step by step

1. **Homebrew**: installs the Mac package manager, unless it's already installed.
2. **Tools**: installs Git, Node.js 22, pnpm, Python 3.13 and Ollama.
3. **Code**: downloads this repository into a folder called `flatty`.
4. **Front-end packages**: `pnpm install` installs React, Vite, Tailwind CSS, Leaflet and TypeScript.
5. **Back-end packages**: creates a Python environment in `backend/.venv` and installs FastAPI, uvicorn, httpx, scikit-learn, scipy, numpy, joblib and pydantic.
6. **Local AI model**: starts Ollama and downloads `qwen3:8b`, which drafts application e-mails. This step is optional. Without it, the app writes e-mails from templates.

### Dependencies

| Part | Dependency | Defined in |
|---|---|---|
| System | Node.js 22, pnpm 10, Python 3.10+ (3.13 recommended), Ollama (optional) | [.mise.toml](.mise.toml) |
| Front-end | react, react-dom, leaflet, vite, tailwindcss, @tailwindcss/vite, @vitejs/plugin-react, typescript, oxfmt | [package.json](package.json) |
| Back-end | fastapi, uvicorn, httpx, scikit-learn, scipy, numpy, joblib, pydantic | [backend/requirements.txt](backend/requirements.txt) |
| AI model | qwen3:8b through Ollama (optional) | [backend/README.md](backend/README.md) |

## Run

**Terminal 1, back-end.** Run this from the `flatty` folder. The first two commands are only needed the first time. They collect listings (about 2.5 minutes) and train the risk model.

```bash
cd backend
.venv/bin/python -m app.scraper.run
.venv/bin/python -m app.ml.train
.venv/bin/uvicorn app.main:app --port 8000 --reload
```

**Terminal 2, front-end.** Run this from the `flatty` folder:

```bash
pnpm dev
```

Open http://localhost:8443. If the back-end isn't running, the app shows demo data.
