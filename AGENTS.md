# figma-make-app

React + Vite + Tailwind CSS project running inside Figma Make.

## Development Server

A Vite development server is **already running** on `$PORT` (default 8443). You don't need to start it manually.

- Preview URL: The user can access the running app through the preview panel
- Hot reload: Changes to source files are reflected immediately

## Project Structure

This is the canonical project structure. Start with task-relevant files below. Only follow imports or inspect other files when required, when a documented path is missing, or when the repository contradicts this guide.

- `src/main.tsx` - React entrypoint; imports `src/index.css` and mounts `src/App.tsx` into the `#root` element
- `src/App.tsx` - Primary application component and the usual starting point for UI work
- `src/index.css` - Global CSS entrypoint and Tailwind CSS v4 import
- `index.html` - Vite HTML shell containing the `#root` element and loading `src/main.tsx`
- `package.json` - Project dependencies and the Vite build, development, preview, and formatting scripts
- `vite.config.ts` - Vite configuration with React, Tailwind CSS v4, and Figma Make plugins plus the `@` alias for `src`
- `.mise.toml` - Toolchain versions for Node.js and pnpm

## Back-end

`backend/` is a local FastAPI + scikit-learn back-end (scraper, risk and quality models, local LLM through Ollama). `src/api.ts` calls it via `/api`, which Vite proxies to `http://127.0.0.1:8000`; without it the app falls back to demo data. See `backend/README.md`. Accounts (log-in, remembered profile, saved homes) are in `backend/app/accounts.py`; setting `FLATTY_ALLOWED_EMAILS` or `FLATTY_INVITE_CODE` makes the API log-in only. A developer password in front of every route (`backend/app/site_gate.py`) is read from `backend/site_password.txt` (git-ignored; never commit it, the repo is public), for an online test. The online test runs through Vercel (`vercel/vercel.json` forwards everything) to a team Mac via Tailscale Funnel; `./start-online.sh` starts it (see `backend/README.md`). When `dist/` exists the back-end serves it, so one port is the whole site. All weights, thresholds, scanned phrases and AI prompts behind the risk and reply scores are in `backend/rules.toml`, loaded by `backend/app/rules.py`; change rules there, not in code. Scraping rules per site are in `backend/LEGAL.md` and enforced in `backend/app/scraper/sources.py`. Don't enable a source there without reviewing its terms.

## Dependencies

- Runtime: React 19 and React DOM 19
- Styling: Tailwind CSS v4 with the `@tailwindcss/vite` plugin
- Build tooling: Vite 8, TypeScript 5.7, and `@vitejs/plugin-react`
- Formatting: oxfmt

## Styling

This project uses **Tailwind CSS v4** through the `@tailwindcss/vite` plugin configured in `vite.config.ts`. `src/index.css` imports Tailwind with `@import 'tailwindcss';`. Use Tailwind utility classes directly in JSX and put global CSS or Tailwind v4 theme customization in `src/index.css`. This scaffold does not need a Tailwind config file or PostCSS config.

`src/main.tsx` imports `src/index.css`, so global font wiring belongs in `src/index.css`. Keep CSS `@import` statements first, then add any `@font-face` rules and font-family defaults there.

## Code quality

- Use double quotes for strings containing apostrophes (`"We're here to help"`), or escape them in single-quoted strings. An unescaped apostrophe in a single-quoted string breaks the build.
- Ensure JSX tags are closed and braces are balanced.
- Export components as default exports.
