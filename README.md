# localtunnel-publish-skill

Share a **local static site** over the internet with **HTTP Basic Auth** on `127.0.0.1`, then expose it with **[localtunnel](https://github.com/localtunnel/localtunnel)** (`npx -y localtunnel`).

## Quick start

```bash
cd .cursor/skills/publish-preview/scripts
uv run serve_basic_auth.py --show-guide
```

Then run the server and tunnel as printed (or read `.cursor/skills/publish-preview/SKILL.md`).

## Layout

| Path | Purpose |
|------|---------|
| `.cursor/skills/publish-preview/SKILL.md` | Cursor agent skill (triggers + thin notes) |
| `.cursor/skills/publish-preview/scripts/serve_basic_auth.py` | PEP 723 script: auth server, port cleanup, `--show-guide` |

Copy this repository’s `.cursor` tree into a project, or vendor the paths you need.

## Requirements

- Python 3.10+
- Optional: [uv](https://docs.astral.sh/uv/getting-started/installation/) (recommended; installs `psutil` via PEP 723)
- Node / npm for `npx -y localtunnel`

## Defaults

- Basic Auth user: `preview` (override `--user`)
- Password file: `.local/preview-auth.pass` (created on first run; **gitignore it**)

## License

Use and modify as needed for your team; no warranty.
