# How the videos get made

You do one thing: turn the scene texts into audio. I do the rest.

## 1. You: the voice (ElevenLabs)

Files to paste, one scene at a time: `docs/video/nebius/voiceover/n01.txt` ... `n10.txt` and `docs/video/paypal/voiceover/p01.txt` ... `p10.txt`.
(`ALL.txt` in each folder is the whole read in one piece, if you prefer one take.)

- Voice: calm, warm, confident, American English, a little slower than you would speak. Same voice for both videos.
- Speed 1.0 in the tool. I speed the finished video up by 1.2 later; do not speed it up twice.
- Pronunciation: "agent-bridge" (agent, bridge), "Nemotron" (NEM-oh-tron), "Nebius" (NEE-bee-us), "Tavily" (TAV-ih-lee), "MIT" (M-I-T).
- Save each scene as `n01.mp3` ... (or `.wav`), keep the same names, and put them in `docs/video/nebius/audio/` and `docs/video/paypal/audio/`.
  If you read one take instead, put it in as `all.mp3` and I will cut it at the pauses.
- If a scene sounds wrong, change the text in `scenes.yaml` and run `python docs/video/build.py`; the txt files update.

## 2. Me: the pictures

| Part | How | Tool |
|---|---|---|
| Animation scenes (hook, pull mode, why it matters, evidence diagram, end cards) | Drawn as small web animations in the console's own look, driven by one clock so each frame can be rendered exactly | Claude Design, then rendered frame by frame with headless Chrome |
| Screen scenes | The real console on the demo data (`bridge demo-data`), driven by a script with a visible cursor, recorded at 1568 x 882 | headless Chrome with screen capture |
| Terminal scenes | The real commands, typed at a readable speed, recorded | the same renderer |

Every recorded clip is cut to the length of its audio, so picture and voice always match.

## 3. Me: the edit (after your audio arrives)

1. Measure each audio file. Set each scene's length to its audio plus a short pause.
2. Stretch or trim each clip to that length (slow parts held, dead time cut).
3. Captions: the short line per scene burned onto the picture, plus the full voice-over as soft subtitles.
4. Join the scenes with quick dissolves, mix the voice, speed everything up 1.2x (picture with `setpts`, voice with `atempo`), check the total is under 3:00.
5. Export 1080p MP4 for YouTube and a poster frame.

## Checks before anything is published

- The total is under 3:00 for both videos.
- Every scene that is not live (recording, practice server, animation) says so in its caption or in the first words of the scene.
- No sentence from "What we do not say" in `BRIEF.md`.
- You watch it once with sound and once muted. Publishing and submitting stay with you.
