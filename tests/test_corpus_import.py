from __future__ import annotations

import subprocess
from pathlib import Path

from hubble_tension.corpus import (
    EXPECTED_CATEGORY_COUNT,
    EXPECTED_PAPER_COUNT,
    BibliographyResolver,
    load_corpus,
    write_corpus_to_store,
)
from hubble_tension.state import StateStore

EXPECTED_CATEGORY_COUNTS = {
    "Distance-Ladder Calibration and Local Systematics": 27,
    "Early-Universe and Pre-Recombination Solutions": 24,
    "Growth, S8, Weak Lensing, Clusters, and CMB Lensing": 55,
    "Independent Late-Universe H0 Probes": 13,
    "Inverse Distance Ladder, BAO, and Expansion History": 57,
    "Late-Universe Dark Energy and Modified Gravity": 8,
    "Local Inhomogeneity and Light-Propagation Effects": 4,
    "Reviews, Model Comparisons, and No-Go Results": 15,
}


def test_load_corpus_imports_all_scanned_papers_without_errors() -> None:
    result = load_corpus(".")

    assert result.errors == ()
    assert result.ok is True
    assert len(result.papers) == EXPECTED_PAPER_COUNT
    assert len(result.category_counts) == EXPECTED_CATEGORY_COUNT
    assert result.category_counts == EXPECTED_CATEGORY_COUNTS
    assert result.papers[0].paper_id == "paper-001"
    assert result.papers[-1].paper_id == "paper-203"
    assert {paper.paper_id for paper in result.papers} == {
        f"paper-{number:03d}" for number in range(1, EXPECTED_PAPER_COUNT + 1)
    }


def test_bibliography_resolver_preserves_links_paths_categories_and_sources() -> None:
    result = load_corpus(".")
    resolver = result.resolver

    paper = resolver.require("paper-001")

    assert isinstance(resolver, BibliographyResolver)
    assert paper.title == 'Planck Collaboration, "Planck 2018 results. VI. Cosmological parameters"'
    assert paper.source_url == "https://arxiv.org/abs/1807.06209"
    assert paper.local_path == "papers/1807.06209_planck_2018_cosmological_parameters.pdf"
    assert paper.category == "Early-Universe and Pre-Recombination Solutions"
    assert paper.source_file == "SCANNED_PAPERS.md"
    assert paper.metadata["readme_source_file"] == "papers/README.md"
    assert paper.metadata["coverage_source_file"] == "categories/_coverage.md"
    assert paper.metadata["category_source_file"] == (
        "categories/01_early_universe_pre_recombination.md"
    )
    assert resolver.by_source_url("https://arxiv.org/abs/1807.06209") == paper
    assert (
        resolver.by_local_path("papers/1807.06209_planck_2018_cosmological_parameters.pdf")
        == paper
    )


def test_every_paper_has_one_category_url_and_local_ignored_pdf_path() -> None:
    result = load_corpus(".")

    assert len({paper.source_url for paper in result.papers}) == EXPECTED_PAPER_COUNT
    assert len({paper.local_path for paper in result.papers}) == EXPECTED_PAPER_COUNT
    for paper in result.papers:
        assert paper.source_url.startswith("https://arxiv.org/abs/")
        assert paper.local_path.startswith("papers/")
        assert paper.local_path.endswith(".pdf")
        assert (Path(".") / paper.local_path).exists()

    check_ignore = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        input="\n".join(paper.local_path for paper in result.papers),
        text=True,
        capture_output=True,
        check=False,
    )
    assert check_ignore.returncode == 0
    assert len(check_ignore.stdout.splitlines()) == EXPECTED_PAPER_COUNT

    tracked = subprocess.run(
        ["git", "ls-files", "--", "papers/*.pdf", "papers/**/*.pdf"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert tracked.stdout == ""


def test_dataset_leads_are_seeded_from_categories_and_paper_metadata() -> None:
    result = load_corpus(".")

    assert len(result.dataset_leads) == EXPECTED_CATEGORY_COUNT
    lead_by_category = {lead.metadata["category"]: lead for lead in result.dataset_leads}
    assert set(lead_by_category) == set(EXPECTED_CATEGORY_COUNTS)
    for category, expected_count in EXPECTED_CATEGORY_COUNTS.items():
        lead = lead_by_category[category]
        assert lead.dataset_id.startswith("dataset-lead-")
        assert lead.local_path is not None
        assert lead.local_path.startswith("categories/")
        assert lead.metadata["lead_type"] == "category_seed"
        assert lead.metadata["paper_count"] == expected_count
        assert len(lead.metadata["paper_ids"]) == expected_count
        assert len(lead.metadata["source_urls"]) == expected_count
        assert lead.metadata["dataset_hints"]


def test_write_corpus_to_store_populates_paper_and_dataset_tables(tmp_path: Path) -> None:
    result = load_corpus(".")
    store = StateStore(tmp_path / "lab.sqlite3")
    store.initialize()

    write_corpus_to_store(store, result)
    write_corpus_to_store(store, result)

    with store.connect() as connection:
        paper_count = connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        dataset_count = connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]

    assert paper_count == EXPECTED_PAPER_COUNT
    assert dataset_count == EXPECTED_CATEGORY_COUNT
    stored_paper = store.paper_by_id("paper-001")
    assert stored_paper is not None
    assert stored_paper["source_url"] == "https://arxiv.org/abs/1807.06209"
    assert stored_paper["metadata_json"]["filename"] == (
        "1807.06209_planck_2018_cosmological_parameters.pdf"
    )

    dataset_id = "dataset-lead-early-universe-and-pre-recombination-solutions"
    stored_dataset = store.dataset_by_id(dataset_id)
    assert stored_dataset is not None
    assert stored_dataset["metadata_json"]["paper_count"] == 24
    assert "paper-001" in stored_dataset["metadata_json"]["paper_ids"]


def test_duplicate_or_unresolved_rows_become_import_error_records(tmp_path: Path) -> None:
    _write_bad_corpus(tmp_path)

    result = load_corpus(tmp_path)

    messages = [error.message for error in result.errors]
    assert any("duplicate source_url" in message for message in messages)
    assert any("expected 203 imported papers" in message for message in messages)
    assert all(error.source_file for error in result.errors)
    assert all(isinstance(error.row_ref, str) for error in result.errors)


def test_missing_category_file_assignment_is_an_import_error(tmp_path: Path) -> None:
    _write_bad_corpus(tmp_path)
    category_file = tmp_path / "categories" / "01_bad_category.md"
    category_file.write_text(
        "\n".join(
            [
                "# Bad Category",
                "",
                "| Local PDF | Study | Why it is in this category | Source |",
                "| --- | --- | --- | --- |",
                "| [`a.pdf`](../papers/a.pdf) | A | First row. | https://arxiv.org/abs/1 |",
            ]
        ),
        encoding="utf-8",
    )

    result = load_corpus(tmp_path)

    assert any(
        error.source_file == "SCANNED_PAPERS.md"
        and "no category-file assignment in categories/*.md" in error.message
        and "b.pdf" in error.message
        for error in result.errors
    )


def _write_bad_corpus(root: Path) -> None:
    papers_dir = root / "papers"
    categories_dir = root / "categories"
    papers_dir.mkdir()
    categories_dir.mkdir()
    (papers_dir / "a.pdf").write_bytes(b"%PDF-1.4 a")
    (papers_dir / "b.pdf").write_bytes(b"%PDF-1.4 b")

    (root / "SCANNED_PAPERS.md").write_text(
        "\n".join(
            [
                "# Scanned Hubble Tension Papers",
                "",
                "| # | Local ignored PDF | Study | Why included | Source |",
                "| ---: | --- | --- | --- | --- |",
                '| 1 | `papers/a.pdf` | A, "Study A" | First row. | https://arxiv.org/abs/1 |',
                '| 2 | `papers/b.pdf` | B, "Study B" | Duplicate URL. | https://arxiv.org/abs/1 |',
            ]
        ),
        encoding="utf-8",
    )
    (papers_dir / "README.md").write_text(
        "\n".join(
            [
                "# Hubble Tension Papers",
                "",
                "| File | Study | Why it is included | Source |",
                "| --- | --- | --- | --- |",
                '| `a.pdf` | A, "Study A" | First row. | https://arxiv.org/abs/1 |',
                '| `b.pdf` | B, "Study B" | Duplicate URL. | https://arxiv.org/abs/1 |',
            ]
        ),
        encoding="utf-8",
    )
    (categories_dir / "_coverage.md").write_text(
        "\n".join(
            [
                "# Classification Coverage",
                "",
                "| File | Category |",
                "| --- | --- |",
                "| `a.pdf` | Bad Category |",
                "| `b.pdf` | Bad Category |",
            ]
        ),
        encoding="utf-8",
    )
    (categories_dir / "01_bad_category.md").write_text(
        "\n".join(
            [
                "# Bad Category",
                "",
                "| Local PDF | Study | Why it is in this category | Source |",
                "| --- | --- | --- | --- |",
                "| [`a.pdf`](../papers/a.pdf) | A | First row. | https://arxiv.org/abs/1 |",
                "| [`b.pdf`](../papers/b.pdf) | B | Duplicate URL. | https://arxiv.org/abs/1 |",
            ]
        ),
        encoding="utf-8",
    )
