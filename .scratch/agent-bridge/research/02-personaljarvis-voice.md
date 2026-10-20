# PersonalJarvis: voice pipeline and reuse assessment

Researched 2026-10-07 from a shallow clone of https://github.com/PersonalJarvis/PersonalJarvis (HEAD d210c1d, 2026-10-06, package version 2.9.0). All facts below come from the repo README, docs, pyproject and source unless marked UNVERIFIED.

## Summary

PersonalJarvis is a very large (about 1,558 Python files in `jarvis/`, 145 MB source, 10.8k files total), Apache-2.0, Python 3.11-3.14 desktop "agent super-app" with a mature voice stack. It is a whole product, not a voice library. It is not practical to lift wholesale, but its voice engine is cleanly layered and uses permissive local models, and it already exposes an MCP server and a local control API. Best use for agent-bridge: treat it as an optional front end that talks to our marketplace through MCP (zero code lifted), and copy only small ideas or modules (turn-taking recipe, wake-word config, approval risk levels, signed peer envelopes). Do not build the demo on top of it.

## Key facts (with sources)

License
- Apache-2.0 from 2.0.0 (switched 2026-08-27); releases up to 1.6.0 stay MIT. Must ship LICENSE and NOTICE and mark modified files. Trademark is carved out (TRADEMARK.md). Sources: https://github.com/PersonalJarvis/PersonalJarvis/blob/main/LICENSE, `NOTICE`, `docs/licensing.md`.
- Bundled third-party pieces have own licenses (Silero VAD, parts adapted from hermes-agent MIT, T3 Code MIT). Parakeet v3 model is CC-BY-4.0 (attribution needed). Source: `docs/local-live-voice-rebuild.md` line 367.

Voice pipeline (two modes)
- Pipeline mode: VAD, STT, Brain (LLM), TTS, each stage independently pluggable and local or hosted. Realtime mode: one live speech-to-speech connection (cloud only; "No local Realtime engine is currently offered"; labelled research preview). Source: `docs/product/everyday-use/voice-conversations.md`.
- Local engine cascade: 16 kHz audio, Silero VAD, Smart Turn v3.2 (semantic end-of-turn model), Parakeet TDT 0.6B v3 int8 via sherpa-onnx (CPU, about 16x real time, 25 European languages), speculative decode on silence, Piper voices via sherpa-onnx (TTS floor on every CPU), optional Qwen3-TTS 1.7B (needs GPU/CUDA for speed). Sources: `docs/local-live-voice-rebuild.md` (sections 4.3, 12.1, table at line 367), `jarvis/voice_engine/stt.py`, `jarvis/voice_engine/tts/piper.py`, `jarvis/voice_engine/tts/{pocket,qwen3}.py`.
- Wake word: openWakeWord (about 3.5 MB ONNX) default, engine options `auto | openwakeword | vosk_kws | stt_match | custom_onnx`; user-chosen phrase; wake only opens the mic. Sources: `jarvis.toml.example` lines 40-44, `docs/local-wakeword/CUSTOM-WAKE-WORD-DESIGN.md`, pyproject lines 138-139, 162.
- Turn-taking: configurable "Thinking pause", continuation buffer (more speech inside the pause is merged into one request), completeness checks, barge-in (sustained user speech stops playback), echo guard and echo reference, audio ducking (Windows and macOS implementations). Sources: voice-conversations.md; `jarvis/speech/{continuation_buffer,completeness,echo_guard,interrupt_intent,turn_buffer}.py`, `jarvis/audio/ducking/windows.py`.
- Cloud STT/TTS providers in config: STT `groq-api | openai-api | openrouter-stt | gemini-api | vertex-stt | faster-whisper`; TTS default `gemini-flash-tts`, alternatives `cartesia`, `grok-voice`, `elevenlabs`, `vertex-tts`. Source: `jarvis.toml.example` lines 46-95.
- Browser voice: when headless, a browser page can "Start Realtime Voice" on localhost or HTTPS (WebRTC transport, `jarvis/realtime/webrtc_transport.py`, `jarvis/browser_voice/`). Source: voice-conversations.md.

Models and providers
- Brain providers include OpenAI, Anthropic, Gemini, OpenRouter, NVIDIA NIM (`https://integrate.api.nvidia.com/v1`, `nvapi-` key, aliases `nvidia|nim|nemotron`), Ollama, local servers. Nemotron 3 Ultra referenced in `jarvis/brain/manager.py` (lines ~382-415). Sources: README "Any model", `jarvis/core/config.py` lines 174-176, `jarvis/brain/manager.py`, `jarvis/brain/model_catalog.py` line 129.
- Nebius is NOT a built-in provider (grep for "nebius" in `jarvis/` and `docs/product/` returned nothing). A user-defined custom OpenAI-compatible endpoint is documented only as "proposal / recommendation. Not implemented" (`docs/custom-provider-endpoints-blueprint.md`). So pointing the brain at Nebius Token Factory needs either a code patch, a localhost OpenAI-compat shim, or a different integration route (see Fit). The NVIDIA NIM provider is built in but is not Nebius, so on its own it would not satisfy the Nebius track.
- Nebius has no ASR/TTS (HACKATHONS.md). So the speech stages must run locally (Parakeet + Piper, both fully offline, no key) or via another vendor (Groq, OpenAI, Gemini, ElevenLabs, Cartesia). Parakeet is an NVIDIA model, which is a nice talking point for the NVIDIA angle (UNVERIFIED whether the hackathon counts it; the "NVIDIA model via Nebius Token Factory" requirement is satisfied by the LLM, not the ASR).

Platform
- Runs on Windows, macOS, Linux and headless (README). Windows installer: `irm .../install/install.ps1 | iex`; needs Python >= 3.11 and Git (installer offers to install). Repo has `.bat` launchers, `voice.bat`, Windows ducking, WinForms error handling, MSIX redirection. Sources: README "Install", `docs/os-parity.md`. UNVERIFIED on our machine: clean install and voice-session latency on the owner's Windows 11 box.
- Install weight: heavy (pyproject 1,000+ lines of dependencies, native wheels such as onnxruntime, sherpa-onnx, openwakeword, webrtcvad). Expect a long first install and model downloads (Parakeet 0.64 GB). Source: pyproject, `docs/local-live-voice-rebuild.md`.

Integration surfaces useful for us
- Local authenticated Control API at `/api/control/*` (bearer `jctl_` key, constant-time compare, loopback does not bypass auth). Source: `docs/jarvis-control-api.md`.
- MCP server surfaces over Streamable HTTP, with a stdio bridge: `/api/control/mcp/` (tools) and `/api/control/mcp/agents` (roster, board, assignments, approvals). Any MCP client with the key can drive it. Source: `docs/agent-mcp.md`.
- Jarvis can also act as an MCP client (`mcp.json` with `mcpServers`, same format as Claude Desktop). Source: `mcp.json.example`, `jarvis/mcp/client.py`. This is the route for voice: add our bridge MCP server (`browse_agents`, `hire`, `task_status`, `approve`) to Jarvis and the Jarvis voice loop can call it.
- Risk levels per action: safe, monitor, ask, block; ask-level actions pause for a spoken yes/no; every run recorded. Source: README "You stay in control", voice-conversations.md step 5.
- `jarvis/friends/peer.py` and `identity.py`: direct server-less peer links between two Jarvis installs using signed envelopes; unknown public keys rejected before any handler runs; explicit statement that NAT means one side must be reachable (LAN, Tailscale, tunnel). Worth reading as prior art for our relay identity and signing (source: docstring in `jarvis/friends/peer.py`). Not a marketplace and has no payment or isolation.
- It already has its own "Marketplace" but that means installable plugins, MCP servers and skills (40+), not agents for hire. Name clash to avoid in our pitch.

## Fit for agent-bridge

What a voice front end would do: "Find me the best data-analysis agent under 5 dollars" (browse/rank), "Hire the top one for this task" (delegate), "What's the status of my task?" (observability), "Approve" (see below). All of these are plain MCP tool calls against our service; the voice loop is just an MCP client with a microphone.

Reuse vs skip

| Piece | Verdict | Why |
|---|---|---|
| Whole app as base platform | Skip | Competes with OpenClaw as base (decisions.md); 1,558 files, own agent runtime, own marketplace, own memory. Adopting it means inheriting its entire product surface and its bugs docs (BUGS.md, many audit reports). |
| Voice as a runnable front end (install Jarvis, add our MCP server in `mcp.json`) | Reuse (optional, demo add-on) | Zero code lifted, Apache-2.0 friendly, gives wake word, barge-in, local STT/TTS. Cost: heavy install, and our demo then depends on a second large app. |
| Voice engine internals (`jarvis/voice_engine/`: Silero VAD + Smart Turn + Parakeet + Piper via sherpa-onnx) | Reuse recipe, not code | The recipe is the valuable part: sherpa-onnx (Apache-2.0) runs Parakeet and Piper on CPU on Windows. We can call sherpa-onnx directly in about a few hundred lines, or lift `stt.py` / `tts/piper.py` (small, self-contained, keep Apache notices). |
| Smart Turn v3.2 end-of-turn detection | Reuse | Best answer to turn-taking without hand-written timers. Model license UNVERIFIED (check model card before bundling). |
| openWakeWord config | Reuse idea | Library is independent of Jarvis; use it directly if we want a wake word. |
| Browser WebRTC voice (`browser_voice`, `realtime/webrtc_transport.py`) | Skip | Cloud realtime only; no Nebius or NVIDIA realtime model, so it cannot serve the Nebius track. |
| Risk levels (safe/monitor/ask/block) | Copy the concept | Maps directly onto our approval policy table for remote agents. |
| Peer signed-envelope identity | Read as prior art | Compare with our public-key plus E2E design; do not copy wholesale. |
| Observability UI, 3D "Jarvis Verse" | Skip | Our observability reference is munder-difflin (separate topic). |
| Telephony, dictation, pets, Appshots, Computer Use | Skip | Off-scope. |

Two options for the voice path:
1. Minimal (recommended): a small voice sidecar of our own that uses sherpa-onnx (Parakeet STT, Piper TTS, Silero VAD, Smart Turn) in front of the marketplace's own MCP tools, with Nemotron on Nebius as the brain. Fully offline speech, Windows-friendly, no cloud ASR/TTS dependency, and every LLM call goes through Nebius so the track rule holds.
2. Show-off: run PersonalJarvis as the voice shell, register our MCP server, and say "Jarvis, hire the best SQL agent". Looks impressive and tests our MCP interface from a real third-party client, but the brain would be Jarvis's own configured provider, so Nebius usage must come from our marketplace-side agents, not from Jarvis (unless we patch in a custom endpoint).

Security rule inherited from decisions.md: voice may browse, hire and read status, but approval of remote-agent permissions stays on desktop/phone, never by voice. Jarvis itself offers spoken yes/no for ask-level actions; for us this is a deliberate non-reuse, since spoken approval can be triggered by replayed or ambient audio (the repo itself warns not to speak secrets).

## Recommendation

- Do not adopt PersonalJarvis as a platform or base. Keep OpenClaw as base per decisions.md.
- Make voice a late, optional layer (Phase 3). Build the marketplace tools first as an MCP server (this is needed anyway, per decisions.md "Interface").
- Preferred voice implementation: option 1 (own thin sidecar on sherpa-onnx with Parakeet + Piper + Silero VAD + Smart Turn). Fallback demo path: option 2, which costs only an `mcp.json` entry once the MCP server exists, so it is cheap insurance and a good "works with any MCP client" proof.
- If we use sherpa-onnx models, record attributions: Parakeet CC-BY-4.0, Apache-2.0 for sherpa-onnx; if we lift any Jarvis file, keep the Apache header, ship NOTICE and mark modifications.
- Timebox: voice budget at most about 1 day; skip if the core delegation + isolation demo is not stable by about 2026-10-20.

## Risks

- Heavy install and fast-moving upstream (version 2.9.0, daily commits, large surface); breakage risk if the demo depends on it.
- License hygiene: Apache NOTICE and file-change marking; CC-BY-4.0 on Parakeet; Silero VAD and Smart Turn model licenses UNVERIFIED for redistribution.
- Nebius track rule: Jarvis has no Nebius provider; the NVIDIA NIM provider is not Nebius Token Factory. Voice brain must be our own call to Nebius.
- Latency: local Parakeet decodes whole utterances (fast on CPU per their benchmark: about 16x real time, p95 under 270 ms on their hardware; UNVERIFIED on the owner's laptop). Piper voice quality is modest; Parakeet v3 covers 25 European languages, so Vietnamese is likely NOT supported (UNVERIFIED; the owner writes Vietnamese, but a demo in English avoids this).
- Voice approval is an attack surface; keep it out of the approval path.
- Possible confusion with its own "Marketplace" (plugins) in the pitch.
- Windows-specific audio issues (device selection, echo) are documented at length in the repo, which suggests they are real; budget time for mic/speaker tuning on the demo machine.

## Open questions

- Do we want voice at all in the judged demo, or only in a short "bonus" clip? Which hackathon scoring (Best Demo Delivery at PayPal) rewards it?
- Does Smart Turn v3.2 have a license that allows bundling in an open-source release (check model card on Hugging Face)?
- Can Nebius Token Factory be configured as a Jarvis custom endpoint with a small patch (OpenAI-compatible `base_url`)? Only matters for option 2.
- Is Vietnamese STT required for the demo? If yes, Parakeet v3 is not the answer (Whisper-class model needed).
- Does NVIDIA offer hosted Parakeet/Riva ASR we could call and cite for the NVIDIA angle? UNVERIFIED, not researched here.
- Clean-install time and idle RAM of PersonalJarvis on the owner's Windows 11 machine (not measured).
