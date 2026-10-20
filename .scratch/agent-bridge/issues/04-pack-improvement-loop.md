# 04 Pack improvement loop

Status: open
Milestone: M1

Shows how a harness is developed and improved, not only run. `bridge improve <pack>`: take the pack, generate prompt variants of its llm steps with Nemotron, certify each variant on a dev suite, keep the best, write it as a new version (v0.2.0) with a typed diff (only prompt text changed, permissions identical). The owner approves before publish. The registry refuses a version that widens permissions without a major bump.

Done when: v0.1 to v0.2 shows a measured score change on a held-out suite, the diff proves no permission change, a variant that widens tools is rejected, and the console shows both versions.
