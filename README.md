# Hubble Tension Autonomous Lab

This repository is a local-first research workspace for the Hubble tension and the software plan for an autonomous AI laboratory that studies the saved scientific corpus, invents and mutates hypotheses, implements testable model code, runs reality checks, learns from failures, and records durable lab notes.

The Hubble tension is the disagreement between:

- Early-universe inference: CMB plus Lambda-CDM predicts H0 around 67 to 68 km/s/Mpc.
- Late-universe measurements: Cepheid-calibrated distance ladders such as SH0ES/H0DN cluster around H0 roughly 73 km/s/Mpc, while TRGB/CCHP-style calibrations sit lower, around 70 km/s/Mpc.

This project does not claim to have solved the Hubble tension. Its goal is to build an auditable software laboratory that can test ideas against real datasets and reject weak concepts automatically before any internally promising candidate is treated seriously.

## Product Direction

The planned product is a fully automated AI-led lab. The AI lab head is the only required reviewer in the default workflow. A human operator can inspect logs, pause the process, change configuration, or read reports, but the software must not require human scientific or code-review approval to continue.

The intended user-facing launcher is:

```text
./hubble_tension.sh
```

The launcher starts or resumes the lab with no prompts and no required arguments. It prefers the repo-local `.venv/bin/python` when `PYTHON` is not set, then falls back to supported system Python versions. This keeps a direct shell run from accidentally selecting a Python environment that is missing runtime dependencies such as Pydantic.

It streams concise live logs, persists state continuously, checkpoints after interruptions, and keeps running until stopped, budget-paused, or until an internally stable candidate survives all configured validation and adversarial checks.

Even then, the strongest internal status is `stable_internal_candidate`. Reports and terminal banners must say that a candidate passed configured gates and is not a scientific claim.

## Current Repo Contents

- [SCANNED_PAPERS.md](SCANNED_PAPERS.md): tracked bibliography of the 203 scanned papers with verified arXiv links.
- [papers/README.md](papers/README.md): project-local bibliography for the paper corpus.
- `papers/*.pdf`: local PDF copies of the papers. These remain ignored by Git.
- [categories/README.md](categories/README.md): overview of the 8 solution and constraint categories.
- [categories/_coverage.md](categories/_coverage.md): proof that all 203 papers are assigned to exactly one primary category.
- `categories/*.md`: category-specific notes listing papers and explaining their role in the Hubble tension landscape.
- `docs/planning/hubble_tension_solver_sds.md`: local SDS for the autonomous lab.
- `docs/planning/hubble_tension_build_plan.md`: local phased build plan for implementing the product.

Note: `docs/planning/` is intentionally ignored in this repo, so those planning documents are local working docs unless that policy changes.

## Planned Lab Loop

The core loop defined in the SDS is:

```text
literature + allowed fiction motifs + random speculation
-> hypothesis
-> formal model
-> generated implementation
-> automated tests on real datasets
-> tuning / mutation / branching / refutation
-> adversarial validation for promising candidates
-> lab memory
-> next hypothesis
```

The software should:

1. Import the paper corpus, source links, local PDF paths, and category assignments.
2. Extract model families, equations, parameters, priors, datasets, reported results, and failure modes.
3. Build durable lab memory from hypotheses, implementations, runs, failures, mutations, branches, and reports.
4. Generate paper-derived mutations, failure inversions, assumption-removal ideas, seeded random concepts, and allowed fiction-motif abstractions.
5. Convert concepts into equations, priors, parameterizations, and falsification tests.
6. Generate sandboxed code for model modules.
7. Run schema, math, unit, baseline, calibration, dataset, replication, and adversarial checks.
8. Tune or branch ideas that partially improve metrics.
9. Abandon wrong turns with recorded evidence.
10. Produce reports with provenance, negative evidence, external-status tracking, and no hidden failures.

## Build Plan Summary

The current build plan breaks implementation into 15 phases:

| Phase | Name | Main Outcome |
| ---: | --- | --- |
| 0 | Repo and Policy Foundation | Package skeleton, schemas, CI, config, concrete budgets, and immutable science rules. |
| 1 | Launcher and Runtime Supervisor | `./hubble_tension.sh`, locks, resume, checkpointing, live logs, STOP handling, and budget states. |
| 2 | State Store and Provenance | Durable state, migrations, agent and prompt provenance, lab notes, candidates, and reports. |
| 3 | Corpus and Category Import | The 203-paper corpus, 8 categories, source links, and local PDF paths imported. |
| 4 | Paper Study and Failure Memory | Methods, datasets, priors, results, failure modes, and no-go lessons extracted. |
| 5 | Stub Autonomous Lab Loop | Deterministic `StubLabHead`, mock corpus mode, and end-to-end dry-run workflow. |
| 6 | Concept Forge | Paper mutations, failure inversion, assumption removal, random forge, and controlled motif mining. |
| 7 | Formula, Critic, and Sandbox Code Loop | Hypotheses become equations and isolated generated modules. |
| 8 | Reality Checks and Calibration | L0-L5 rejection pipeline, typed metric packets, likelihood loaders, and known-bad tests. |
| 9 | Tuning, Branching, and Backtracking | Multi-iteration search with abandonment rules and `generator_quarantine`. |
| 10 | Supported Solver and Posterior Path | CLASS-family solver path, solver build automation, and `inconclusive_posterior` handling. |
| 11 | Independent Replication | L8 independent implementation path and compressed-observable checks. |
| 12 | Adversarial Validation and Candidate Registry | Registered refutation checks and truthful stable-candidate banner rendering. |
| 13 | Continuous Lab Operations | External-status transitions, digests, maintenance, and optional scale-out profile. |
| 14 | Release Readiness and Closure | Automated readiness manifest, validation ledger, and no-claim release gate. |

## Scientific Categories

The current corpus is organized into these categories:

| Category | Papers | Role |
| --- | ---: | --- |
| Early-Universe and Pre-Recombination Solutions | 24 | Models that change physics before or near recombination, often by reducing the sound horizon. |
| Late-Universe Dark Energy and Modified Gravity | 8 | Models that modify low-redshift expansion or gravity. |
| Distance-Ladder Calibration and Local Systematics | 27 | Tests of Cepheids, TRGB, JAGB, SBF, supernova calibration, and related local-H0 systematics. |
| Independent Late-Universe H0 Probes | 13 | Time-delay lenses, megamasers, standard sirens, FRBs, and other non-ladder H0 probes. |
| Local Inhomogeneity and Light-Propagation Effects | 4 | Local-void, local-environment, and propagation-effect explanations. |
| Inverse Distance Ladder, BAO, and Expansion History | 57 | BAO, supernovae, chronometers, DESI/BOSS/eBOSS, and expansion-history constraints. |
| Growth, S8, Weak Lensing, Clusters, and CMB Lensing | 55 | Structure-growth and lensing constraints that viable H0 solutions should not worsen. |
| Reviews, Model Comparisons, and No-Go Results | 15 | Reviews, rankings, and arguments that map why many proposed solutions fail. |

## Current Status

The implementation is complete through Phase 14 of the build plan as an executable local scaffold:

- Phase 0 created the Python package skeleton, config, CI, policy contracts, schemas, and immutable science rules.
- Phase 1 added `./hubble_tension.sh`, no-prompt startup, runtime supervisor, live logs, locks, STOP handling, checkpointing, resume behavior, and budget states.
- Phase 2 added the SQLite state store, migrations, lab notes, event log, checkpoints, candidate/report records, and required agent/prompt provenance.
- Phase 3 added `hubble_tension.corpus.importer`, which imports all 203 scanned papers, preserves arXiv URLs and local ignored PDF paths, resolves stable paper IDs, validates the 8 category assignments, seeds dataset leads, and writes the corpus into the state store.
- Phase 4 added `hubble_tension.corpus.study`, which builds strict JSON paper-study records for all 203 papers, records method/dataset/prior/result/failure fields, creates reusable failure memories, answers which papers constrain a concept category, and encodes the SDS MVP 3 benchmark replay suite by paper ID.
- Phase 5 added a deterministic `StubLabHead` path and mock corpus mode so one launcher run can observe, imagine, hypothesize, formalize, implement, test, tune, branch/refute, remember, decide, and checkpoint without `mcoda` or solvers.
- Phase 6 added the concept forge: paper mutations, failure inversions, assumption-removal tracks, seeded random concepts, prior-art/similarity checks, and allowlisted fiction-motif inspiration with permanent disable policy after failed A/B cycles.
- Phase 7 added formula building, static math criticism, generated model rendering under active run paths, and static sandbox isolation checks.
- Phase 8 added fixture likelihood loaders, richer typed metric packets, L0-L5 summary-screen reality checks, covariance gate blockers, and disguised Lambda-CDM non-promotion.
- Phase 9 added bounded tuning, assumption-aware branching, abandonment lessons, branch-priority scoring with novelty as tie-breaker only, W0-W5 abandonment thresholds, and generator quarantine.
- Phase 10 added the supported-solver scaffold: commit-pinned solver config, dry-run and container build automation for CLASS-family and HyRec paths, candidate-to-solver adapters, Lambda-CDM and EDE replay fixtures, posterior timeout/failure statuses, and lazy runtime solver probes that surface `bootstrap_solver_unavailable`.
- Phase 11 added independent replication scaffolding: L8 queue records, separate replication implementation metadata, deterministic automated reviewer routing, CMB compressed-observable checks, recombination fixture checks, replication reports, and policy blocking for background-only or failed replication scopes.
- Phase 12 added adversarial validation scaffolding: immutable code-defined L9 checks, 12-attempt registered-gate accounting, budget-exhaustion handling as `inconclusive_adversarial_budget`, adversarial queue/report storage, a stable-candidate registry, and row-state-driven restart banners that cannot make unreplicated timeout rows look passed.
- Phase 13 added continuous lab operations scaffolding: external-status monitor batching, cited transition proposals, automated lab-head accept/reject rules, explicit external rerun queueing, report search indexing, dataset-integration backlog records, periodic no-ack operator digests, storage compaction/stale-scratch/report-regeneration records, and an optional scale-out profile that cannot bypass sandbox, provenance, metric, replication, or adversarial gates.
- Phase 14 added release-readiness closure: phase completion records for phases 0-14, validation evidence records, a persisted readiness report with provenance, and schema gates proving the scaffold remains automated-only, no-claim, and runnable through `./hubble_tension.sh`.
- Startup readiness hardening fixed two practical launch paths: the autonomous scaffold starts by default unless `HT_LAB_DISABLE_AUTONOMOUS_LOOP=1` is set, and the root launcher now selects `.venv/bin/python` by default so `./hubble_tension.sh` works from a normal shell without manually exporting `PYTHON`.

The configured autonomous loop starts by default when `./hubble_tension.sh` runs. A one-cycle dry-run of the stub path can be exercised locally with:

```text
HT_LAB_DRY_RUN=1 HT_LAB_HEAD_AGENT=stub HT_LAB_CORPUS_SOURCE=mock ./hubble_tension.sh
```

Set `HT_LAB_DISABLE_AUTONOMOUS_LOOP=1` only when you want a monitor-only startup smoke test.

Latest startup validation covered the direct no-`PYTHON` launcher path, the stub autonomous loop, configured `codex55` agent discovery, clean STOP-file shutdown, Ruff, mypy, Docdex impact diagnostics, Docdex pre-commit, and 150 passing pytest tests.

The first scientific target is not a novel solution. It is to replay Lambda-CDM, reproduce a published early-dark-energy failure mode, reject known bad model classes for literature-traceable reasons, and produce an automated report linking the rejection evidence to saved paper IDs and metric-packet fields.

## Repository Policy

Scientific PDFs stay local and ignored by Git. The tracked files preserve the auditable bibliography, categories, and future code without committing large paper files.

Generated model code must run in OS-level isolation with read-only source and corpus mounts, no network by default, and writable scratch space only under the active run directory. Podman is the documented default sandbox runtime on macOS; Docker Desktop and OrbStack are opt-in fallbacks.

This project must remain literature-accountable: every generated model family, candidate, dataset, metric, and rejection reason should trace back to the scanned papers or be clearly marked as a new assumption.
