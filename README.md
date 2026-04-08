# localtunnel-publish-skill

Cursor Marketplace plugin repository built from the official [cursor/plugin-template](https://github.com/cursor/plugin-template).

## Plugin: `localtunnel-publish`

Share a **local static site** on the public internet:

- **HTTP Basic Auth** on `127.0.0.1` (Python `ThreadingHTTPServer`)
- **PEP 723** / **`uv run`** for `psutil` and reliable cleanup on Linux, macOS, and Windows
- Pair with **`npx -y localtunnel`** for an `https://*.loca.lt` URL
- **`--show-guide`** prints the full runbook (curl checks, **Bypass-Tunnel-Reminder**, share blurb)

### Layout

| Path | Purpose |
|------|---------|
| `.cursor-plugin/marketplace.json` | Marketplace manifest |
| `plugins/localtunnel-publish/.cursor-plugin/plugin.json` | Plugin manifest |
| `plugins/localtunnel-publish/skills/publish-preview/SKILL.md` | Agent skill |
| `plugins/localtunnel-publish/scripts/serve_basic_auth.py` | Auth server + cleanup |
| `plugins/localtunnel-publish/assets/logo.svg` | Marketplace logo |
| `scripts/validate-template.mjs` | Validator from upstream template |

### Quick start (contributors)

```bash
git clone https://github.com/smartex-ai-sw/localtunnel-publish-skill.git
cd localtunnel-publish-skill
node scripts/validate-template.mjs
uv run plugins/localtunnel-publish/scripts/serve_basic_auth.py --show-guide
```

### Requirements

- **Node.js** (for `node scripts/validate-template.mjs` and `npx localtunnel`)
- **Python 3.10+**
- Optional: **[uv](https://docs.astral.sh/uv/getting-started/installation/)** (recommended)

### Validation

Before opening a PR or submitting to Cursor:

```bash
node scripts/validate-template.mjs
```

### Defaults (script)

- Basic Auth user: `preview` (override `--user`)
- Password file: `.local/preview-auth.pass` (gitignored; override `--pass-file`)

### License

MIT (see plugin manifest).

### Submission

Per [plugin-template](https://github.com/cursor/plugin-template): repository link and checklist; contact Cursor per their current publish flow.
