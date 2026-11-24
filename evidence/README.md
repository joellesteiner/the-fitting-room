# Evidence

Screenshots and records that support the 002 report. Every item here should be referenced from the report body or an appendix.

## Folders

| Folder | What goes in it | Report section |
| --- | --- | --- |
| `process/` | Project board snapshots, CI runs, pull requests, commit history, releases | Proof of Concept (process, S6) |
| `design/` | Requirements, user stories, diagram versions, before and after comparisons | Proposed Solution (S3) |
| `poc/` | Prototype screens, test runs, model and backtest results | Proof of Concept (S4) |
| `security/` | Attack attempts and their failure, security scan output, risk assessments | Privacy and Security (B3) |
| `ai_use/` | Record of each AI tool used, what it was used for, and how the output was checked | Proof of Concept (GenAI) and AI disclosure |

## Naming

`YYYYMMDD_short_description.png`, for example `20261118_ci_first_green_run.png`.

Dating every file shows the work happening over time, which is the point of the process evidence.

## Before adding a file

* Redact names, emails, student IDs and any other personal information.
* Crop to the part that proves the point.
* Add a row to the log below.

## Log

| Date | File | Shows | Used in |
| --- | --- | --- | --- |
| 18 Nov 2026 | process/20261118_project_board_created.png | Project board set up with all 10 issues in Todo | Proof of Concept, process |
| 18 Nov 2026 | process/20261118_board_after_pr11.png | Issues #1 and #2 moved to Done after PR #11 merged | Proof of Concept, process |
| 19 Nov 2026 | security/20261119_sql_injection_wardrobe.md | Injection payloads against wardrobe storage refused; data intact; tests detect an unsafe rewrite | Privacy and Security, R1 |
| 23 Nov 2026 | security/20261123_tampered_belief_rejected.md | Forged belief accepted before and refused after; made up, tampered and other shoppers' IDs refused; replayed reports stored once | Privacy and Security, R2 |
| 24 Nov 2026 | process/20261124_board_midway.png | #3 and #4 in progress with PRs #13 and #14 linked; #1 and #2 done; six issues to do | Proof of Concept, process |
| 24 Nov 2026 | process/20261124_board_after_pr15.png | #1 to #4 done after PRs #13 and #15 merged; nothing in progress; six issues to do | Proof of Concept, process |
| 24 Nov 2026 | security/20261124_database_download_blocked.md | Whole database and source downloadable before; a stolen shopper ID reused; 404 for every private path after | Privacy and Security, R3 |
