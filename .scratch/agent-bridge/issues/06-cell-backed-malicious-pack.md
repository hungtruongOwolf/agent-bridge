# 06 Cell-backed malicious pack in the console

Status: resolved (2026-10-20)
Milestone: M1

Today the console's "thief" uses a simulated compromised model. Add a second malicious pack whose harm is real code: a `code` step that tries the network, tries to read the host environment, and tries to write outside its sandbox, all inside the Docker Cell. The console shows what each attempt returned (blocked) and the Certifier flags it by behaviour, not by a hard-coded name.

Done when: the console runs it live with no simulation toggle, the report lists each blocked attempt, and the pack is certified as a violation by the Certifier.
