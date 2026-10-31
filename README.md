# Retail Data Quality Check

MiraFlores AI Engineer case study: a small pre-ingestion quality checker for retail order-line CSV batches.

## Current status

Planning and repository setup. The validator and runnable prototype are not implemented yet.
All demonstration data will be synthetic; no JD internal code or data is included.

## Proposed core workflow

CSV batch → deterministic validation → row-level findings and an import-readiness summary.

Initial scope: required columns and values, numeric parsing, duplicate/conflicting order-line IDs, and invalid/ambiguous dates. Business rules will be documented before implementation. One order may contain multiple lines, so order ID alone is not a unique key.

## Repository

- `src/`: application and validation logic (planned)
- `samples/`: synthetic representative and difficult inputs (planned)
- `tests/`: focused validation checks (planned)
- `docs/CASE_STUDY.md`: submission outline and decisions
- `docs/WORK_LOG.md`: actual work sessions
- `scripts/work_timer.py`: start/stop timer, Python 3 standard library only

## Track time

```sh
python3 scripts/work_timer.py start "Repository setup and scope"
python3 scripts/work_timer.py status
python3 scripts/work_timer.py stop "Describe completed work"
```

Stop the timer during breaks. The timer records only explicitly started sessions; it does not reconstruct earlier discussion or prove total effort. Include relevant earlier planning time honestly in the final time declaration. The case study asks for 2–4 hours and a stop at four hours.

## Development history

Commit meaningful milestones and push them to the remote:

```sh
git add README.md docs scripts src samples tests
git commit -m "Describe the completed milestone"
git push
```

Git records commit times; remote pushes preserve the history but are not a precise time clock. Do not backdate commits.

## AI and reuse disclosure

Codex assisted with brainstorming, repository scaffolding, and the time-tracking script. The applicant must review generated work and be able to explain it. No prior project code has been reused at this stage. Update this section with implementation and verification details before submission.

## Before submission

Add installation and run instructions, dependencies, sample inputs and expected outputs, normal and difficult-case demonstrations, actual time spent, and implemented/mocked/deferred features.
