# Hubble Tension Research Workbench

This repository is a research workspace for studying the Hubble tension and designing software that can help search for candidate explanations.

The Hubble tension is the disagreement between the early-universe expansion rate inferred from CMB data under Lambda-CDM, around H0 = 67 to 68 km/s/Mpc, and late-universe measurements from local distance-ladder and other direct probes, often around H0 = 70 to 76 km/s/Mpc.

The goal of this project is not to claim that AI can directly solve the problem. The goal is to build a reproducible, local-first research platform that can learn from the existing scientific literature, generate small testable model variations, reject weak ideas quickly, and preserve the few candidates that deserve serious human review.

## What Is In This Repo

- [SCANNED_PAPERS.md](SCANNED_PAPERS.md): tracked bibliography of the 203 scanned papers, with verified arXiv links.
- [papers/README.md](papers/README.md): project-local bibliography for the paper corpus.
- `papers/*.pdf`: local PDF copies of the papers. These are intentionally ignored by Git so the repository can stay lightweight.
- [categories/README.md](categories/README.md): overview of the 8 solution and constraint categories.
- [categories/_coverage.md](categories/_coverage.md): coverage check showing that all 203 papers are assigned to exactly one primary category.
- `categories/*.md`: category-specific notes listing papers and explaining their role in the Hubble tension landscape.

## What The Project Is Trying To Achieve

The intended software should turn the saved scientific corpus into a structured research engine:

1. Import the 203-paper corpus, source links, local PDF paths, and category assignments.
2. Study the papers for methods, equations, priors, datasets, reported results, and failure modes.
3. Extract public dataset and likelihood leads from the literature.
4. Replay or approximate important prior studies before trusting new ideas.
5. Generate small candidate model mutations from known solution families.
6. Reject mathematically invalid or literature-inconsistent candidates before expensive numerical work.
7. Test plausible candidates against CMB, BAO, SN, BBN, local H0, S8, weak-lensing, cluster, and CMB-lensing constraints.
8. Promote only serious survivors to CLASS/CAMB/Cobaya-style validation.
9. Produce reproducible reports that show which papers inspired, constrained, supported, or rejected each candidate.

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

This repo currently contains the research corpus and category map. The planned solver software has not been implemented yet.

The next technical milestone is a local CLI that can:

- Import the corpus and category files.
- Extract paper study records and dataset leads.
- Build benchmark tests from earlier papers.
- Define a Lambda-CDM baseline score.
- Generate early-dark-energy candidate mutations.
- Screen those candidates with transparent rejection reasons and score breakdowns.

## Repository Policy

Scientific PDFs stay local and ignored by Git. The tracked files should preserve the auditable bibliography, categories, and future code without committing large paper files.

This project should remain literature-accountable: every generated model family, candidate, dataset, score, and rejection reason should trace back to the scanned papers or be clearly marked as a new assumption.
