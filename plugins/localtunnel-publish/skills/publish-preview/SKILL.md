---
name: publish-preview
description: >-
  Publishes a temporary public HTTPS preview of a local static site using HTTP
  Basic Auth on 127.0.0.1 plus localtunnel. Run scripts/serve_basic_auth.py
  with --show-guide for the full workflow. Triggers: publish preview, share
  preview, public URL, localtunnel with password, expose localhost,
  localtunnel-share.
---

# Publish preview

## When to use

- User wants a **short-lived public link** to something on **localhost**.
- Stack: **`serve_basic_auth.py`** (this plugin) + **`npx -y localtunnel`**.

## What the script owns (read this first)

Run **`--show-guide`** on **`scripts/serve_basic_auth.py`** for the full workflow: uv install, **`--root`** choice for relative assets, localtunnel, **Bypass-Tunnel-Reminder** curl checks, share blurb template, gitignore, cleanup behavior, threading note, automation **`uv run`** caveat.

From a **clone of this repository** (repository root):

```bash
uv run plugins/localtunnel-publish/scripts/serve_basic_auth.py --show-guide
```

From **this plugin directory** (`plugins/localtunnel-publish/`):

```bash
uv run scripts/serve_basic_auth.py --show-guide
```

Defaults are **generic** (user **`preview`**, password file **`.local/preview-auth.pass`**). Override with **`--user`** and **`--pass-file`** if needed.

## Agent-only (not in the script)

1. **Pick `--root`:** if HTML loads sibling paths (e.g. `../csv/`), serve the **parent** of the page directory, not only `output/`.
2. **Minimal reply to the user:** paste the share blurb from **`--show-guide`** (fill URL and password). One line on how to stop if they asked.
3. **Background servers from automation:** some runners SIGTERM **`uv run`** children; use **`python3`** on the script for long-lived background here, or ask the user to run **`uv run`** in their own terminal (see **`--show-guide`**).

## Trigger phrases

- "publish preview", "preview link", "share preview", "temporary public URL"
- "localtunnel", "localtunnel with password", "localtunnel-share", "expose localhost"
