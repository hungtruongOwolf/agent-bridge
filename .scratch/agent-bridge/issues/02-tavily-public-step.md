# 02 Tavily public step

Status: open
Milestone: M1
Blocked by: none

A `web_search` tool backed by Tavily, usable only in a PUBLIC step: no memory lens, no reads of private values. A later private step may use the results. The broker refuses a query that overlaps the staged records (a pack cannot smuggle your data out in a search query). Parser rule: a step that has `web_search` must have `memory: none` and no `reads` that come from a memory step.

Done when: a pack does a web lookup then a private analysis in one run; a query containing a staged record's text is blocked and journaled; tests use a fake Tavily transport; one live call is proven with the real key (query contains no private data).
