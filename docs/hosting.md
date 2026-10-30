# Hosting judge mode on Render

Judge mode lets anyone run the real application with no keys: the real server, ledger and PayPal client code, a recorded model for the
answers, and a practice server that copies PayPal's API (test money only). Each visitor gets a private copy that ends after two idle hours.
See "Judge mode and hosting" in the README for what is real and what is not.
The console starts with a sample history (chats, payments in every state, and a helper the visitor "built" that other buyers paid for), spread over the last days and made by the same code paths as a live visit: the recorded model and the practice PayPal. It is built once when the server starts (and again when it is about 12 hours old) and copied for each visitor; it is test money, not real activity.

## Deploy (about 10 minutes, no keys needed)

1. Push this repository to GitHub and make it public (the free plan builds from a public repo without extra access).
2. On render.com: **New > Blueprint**, connect the GitHub account, pick this repository. Render reads `render.yaml` and proposes one web
   service named `agora` (Docker, free plan, health check `/healthz`).
3. When Render asks for the environment variables, leave all three empty to use the recorded model:
   - `JUDGE_ALLOWED_HOSTS`: only if you add a custom domain (comma separated names).
   - `JUDGE_REAL_MODEL`: `1` switches on the live model (see below).
   - `NEBIUS_API_KEY`: secret, used only when `JUDGE_REAL_MODEL=1`.
4. **Apply**. The first build takes a few minutes. Open the `https://<name>.onrender.com` address; the first visit after a sleep takes about a
   minute. `RENDER_EXTERNAL_HOSTNAME` is set by Render and the app allows exactly that name (plus any you list), nothing else.
5. Check `https://<name>.onrender.com/healthz` answers `{"ok": true}`, then run through "Which accounts are at risk?" once yourself.

## Optional: the live model

Set `NEBIUS_API_KEY` (as a secret) and `JUDGE_REAL_MODEL=1`. The app then answers with the live model, but never more than 60 calls an hour for
everyone and 12 an hour for each visitor (`--judge-model-per-hour`, `--judge-model-per-visitor-hour`); past a cap the recorded model answers, and
the line at the bottom of every page says so. Use a key with a small spending limit anyway.

## Run it yourself

```
bridge serve --judge-mode --port 9100                                   # local only, recorded model
bridge serve --judge-mode --host 0.0.0.0 --allowed-host demo.example.org   # reachable from other machines
docker build -t agora . && docker run -p 8787:8787 -e RENDER_EXTERNAL_HOSTNAME=localhost agora
node tools/judge-e2e.mjs http://127.0.0.1:9100                          # headless Chrome walk-through with two visitors
```

## Limits to know

- Free plan: the service sleeps after 15 minutes and loses all visitor data when it restarts. Sessions are capped at 50 and idle ones end after 2 hours.
- Helpers that run code or search the web are refused (no containers inside the container). The recorded model answers Sales and meeting-notes helpers only.
- The Docker build was not run on the machine this was written on (no Docker engine was running); Render's first build is the first real test.
