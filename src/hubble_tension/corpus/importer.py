from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from hubble_tension.state import StateStore

EXPECTED_PAPER_COUNT = 203
EXPECTED_CATEGORY_COUNT = 8

_BACKTICK_RE = re.compile(r"`([^`]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_URL_RE = re.compile(r"https?://[^\s|)]+")
_WHITESPACE_RE = re.compile(r"\s+")
_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class ImportErrorRecord:
    source_file: str
    row_ref: str
    message: str
    raw_row: str


@dataclass(frozen=True)
class CorpusPaper:
    paper_id: str
    title: str
    source_url: str
    local_path: str
    category: str
    source_file: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class DatasetLead:
    dataset_id: str
    name: str
    source_url: str | None
    local_path: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class CorpusImportResult:
    papers: tuple[CorpusPaper, ...]
    dataset_leads: tuple[DatasetLead, ...]
    errors: tuple[ImportErrorRecord, ...]
    category_counts: Mapping[str, int]

    @property
    def resolver(self) -> BibliographyResolver:
        return BibliographyResolver(self.papers)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class _TableRow:
    line_number: int
    cells: tuple[str, ...]
    raw: str


@dataclass(frozen=True)
class _BibliographyRow:
    row_number: int
    title: str
    why_included: str
    source_url: str
    local_path: str
    source_file: str
    line_number: int
    raw: str

    @property
    def filename(self) -> str:
        return PurePosixPath(self.local_path).name


@dataclass(frozen=True)
class _CategoryAssignment:
    category: str
    source_file: str
    line_number: int
    raw: str


class BibliographyResolver:
    def __init__(self, papers: Sequence[CorpusPaper]) -> None:
        self._by_id = {paper.paper_id: paper for paper in papers}
        self._by_source_url = {paper.source_url: paper for paper in papers}
        self._by_local_path = {paper.local_path: paper for paper in papers}

    def get(self, paper_id: str) -> CorpusPaper | None:
        return self._by_id.get(paper_id)

    def require(self, paper_id: str) -> CorpusPaper:
        paper = self.get(paper_id)
        if paper is None:
            raise KeyError(f"unknown paper id: {paper_id}")
        return paper

    def by_source_url(self, source_url: str) -> CorpusPaper | None:
        return self._by_source_url.get(source_url)

    def by_local_path(self, local_path: str) -> CorpusPaper | None:
        return self._by_local_path.get(local_path)


def load_corpus(root: str | Path = ".") -> CorpusImportResult:
    repo_root = Path(root)
    errors: list[ImportErrorRecord] = []

    scanned_rows = _load_scanned_papers(repo_root / "SCANNED_PAPERS.md", errors)
    readme_rows = _load_papers_readme(repo_root / "papers" / "README.md", errors)
    coverage_assignments = _load_coverage_assignments(
        repo_root / "categories" / "_coverage.md", errors
    )
    category_file_assignments = _load_category_file_assignments(repo_root / "categories", errors)

    _record_duplicate_field_errors(scanned_rows, "source_url", "SCANNED_PAPERS.md", errors)
    _record_duplicate_field_errors(scanned_rows, "local_path", "SCANNED_PAPERS.md", errors)
    _record_duplicate_field_errors(readme_rows, "source_url", "papers/README.md", errors)
    _record_duplicate_field_errors(readme_rows, "local_path", "papers/README.md", errors)

    readme_by_filename = _rows_by_filename(readme_rows, "papers/README.md", errors)
    scanned_filenames = {row.filename for row in scanned_rows}
    readme_filenames = {row.filename for row in readme_rows}

    for filename in sorted(readme_filenames - scanned_filenames):
        row = readme_by_filename.get(filename)
        errors.append(
            _error_from_row(
                row,
                "papers/README.md",
                f"README row has no matching scanned-paper row for {filename}",
            )
        )

    for filename, assignment in sorted(coverage_assignments.items()):
        if filename not in scanned_filenames:
            errors.append(
                ImportErrorRecord(
                    source_file=assignment.source_file,
                    row_ref=str(assignment.line_number),
                    message=f"coverage assignment has no matching paper row for {filename}",
                    raw_row=assignment.raw,
                )
            )

    for filename, assignment in sorted(category_file_assignments.items()):
        coverage_assignment = coverage_assignments.get(filename)
        if coverage_assignment is None:
            errors.append(
                ImportErrorRecord(
                    source_file=assignment.source_file,
                    row_ref=str(assignment.line_number),
                    message=f"category file assignment has no coverage row for {filename}",
                    raw_row=assignment.raw,
                )
            )
        elif assignment.category != coverage_assignment.category:
            errors.append(
                ImportErrorRecord(
                    source_file=assignment.source_file,
                    row_ref=str(assignment.line_number),
                    message=(
                        f"category file assigns {filename} to {assignment.category!r}, "
                        f"but coverage assigns {coverage_assignment.category!r}"
                    ),
                    raw_row=assignment.raw,
                )
            )

    papers: list[CorpusPaper] = []
    seen_paper_ids: set[str] = set()
    for scanned in scanned_rows:
        paper_id = f"paper-{scanned.row_number:03d}"
        if paper_id in seen_paper_ids:
            errors.append(
                _error_from_row(scanned, "SCANNED_PAPERS.md", f"duplicate paper id {paper_id}")
            )
            continue
        seen_paper_ids.add(paper_id)

        readme = readme_by_filename.get(scanned.filename)
        if readme is None:
            errors.append(
                _error_from_row(
                    scanned,
                    "SCANNED_PAPERS.md",
                    f"scanned row has no matching papers/README.md row for {scanned.filename}",
                )
            )
            continue
        if readme.source_url != scanned.source_url:
            errors.append(
                _error_from_row(
                    readme,
                    "papers/README.md",
                    (
                        f"README URL {readme.source_url!r} does not match scanned URL "
                        f"{scanned.source_url!r} for {scanned.filename}"
                    ),
                )
            )
        if _normal_text(readme.title) != _normal_text(scanned.title):
            errors.append(
                _error_from_row(
                    readme,
                    "papers/README.md",
                    f"README title does not match scanned title for {scanned.filename}",
                )
            )

        coverage_assignment = coverage_assignments.get(scanned.filename)
        category_assignment = category_file_assignments.get(scanned.filename)
        if coverage_assignment is None:
            errors.append(
                _error_from_row(
                    scanned,
                    "SCANNED_PAPERS.md",
                    f"paper has no category assignment for {scanned.filename}",
                )
            )
            continue
        if category_assignment is None:
            errors.append(
                _error_from_row(
                    scanned,
                    "SCANNED_PAPERS.md",
                    (
                        "paper has no category-file assignment in categories/*.md "
                        f"for {scanned.filename}"
                    ),
                )
            )
        category = coverage_assignment.category

        if not (repo_root / scanned.local_path).exists():
            errors.append(
                _error_from_row(
                    scanned,
                    "SCANNED_PAPERS.md",
                    f"local PDF path is referenced but missing: {scanned.local_path}",
                )
            )

        papers.append(
            CorpusPaper(
                paper_id=paper_id,
                title=scanned.title,
                source_url=scanned.source_url,
                local_path=scanned.local_path,
                category=category,
                source_file="SCANNED_PAPERS.md",
                metadata={
                    "filename": scanned.filename,
                    "scanned_row_number": scanned.row_number,
                    "scanned_line_number": scanned.line_number,
                    "readme_source_file": "papers/README.md",
                    "readme_line_number": readme.line_number,
                    "why_included": scanned.why_included,
                    "readme_why_included": readme.why_included,
                    "coverage_source_file": "categories/_coverage.md",
                    "coverage_line_number": coverage_assignment.line_number,
                    "category_source_file": (
                        category_assignment.source_file
                        if category_assignment is not None
                        else None
                    ),
                    "category_line_number": (
                        category_assignment.line_number
                        if category_assignment is not None
                        else None
                    ),
                    "dataset_hints": _dataset_hints(scanned),
                },
            )
        )

    category_counts = Counter(paper.category for paper in papers)
    if len(papers) != EXPECTED_PAPER_COUNT:
        errors.append(
            ImportErrorRecord(
                source_file="SCANNED_PAPERS.md",
                row_ref="all",
                message=f"expected {EXPECTED_PAPER_COUNT} imported papers, got {len(papers)}",
                raw_row="",
            )
        )
    if len(category_counts) != EXPECTED_CATEGORY_COUNT:
        errors.append(
            ImportErrorRecord(
                source_file="categories/_coverage.md",
                row_ref="all",
                message=(
                    f"expected {EXPECTED_CATEGORY_COUNT} represented categories, "
                    f"got {len(category_counts)}"
                ),
                raw_row="",
            )
        )

    return CorpusImportResult(
        papers=tuple(papers),
        dataset_leads=tuple(_dataset_leads_from_papers(papers, category_file_assignments)),
        errors=tuple(errors),
        category_counts=dict(sorted(category_counts.items())),
    )


def write_corpus_to_store(store: StateStore, result: CorpusImportResult) -> None:
    for paper in result.papers:
        store.upsert_paper(
            paper_id=paper.paper_id,
            title=paper.title,
            source_url=paper.source_url,
            local_path=paper.local_path,
            category=paper.category,
            source_file=paper.source_file,
            metadata=paper.metadata,
        )
    for lead in result.dataset_leads:
        store.upsert_dataset(
            dataset_id=lead.dataset_id,
            name=lead.name,
            source_url=lead.source_url,
            local_path=lead.local_path,
            metadata=lead.metadata,
        )


def _load_scanned_papers(path: Path, errors: list[ImportErrorRecord]) -> list[_BibliographyRow]:
    rows = _parse_markdown_table(
        path,
        expected_headers=("#", "Local ignored PDF", "Study", "Why included", "Source"),
        errors=errors,
    )
    parsed: list[_BibliographyRow] = []
    for row in rows:
        row_number = _parse_int(row.cells[0])
        local_path = _extract_pdf_path(row.cells[1])
        source_url = _extract_url(row.cells[4])
        if row_number is None or local_path is None or source_url is None:
            errors.append(
                ImportErrorRecord(
                    source_file=_rel_source(path),
                    row_ref=str(row.line_number),
                    message=(
                        "scanned-paper row is missing a row number, "
                        "local PDF path, or source URL"
                    ),
                    raw_row=row.raw,
                )
            )
            continue
        parsed.append(
            _BibliographyRow(
                row_number=row_number,
                title=_plain_text(row.cells[2]),
                why_included=_plain_text(row.cells[3]),
                source_url=source_url,
                local_path=local_path,
                source_file=_rel_source(path),
                line_number=row.line_number,
                raw=row.raw,
            )
        )
    return parsed


def _load_papers_readme(path: Path, errors: list[ImportErrorRecord]) -> list[_BibliographyRow]:
    rows = _parse_markdown_table(
        path,
        expected_headers=("File", "Study", "Why it is included", "Source"),
        errors=errors,
    )
    parsed: list[_BibliographyRow] = []
    for index, row in enumerate(rows, start=1):
        local_path = _extract_pdf_path(row.cells[0])
        source_url = _extract_url(row.cells[3])
        if local_path is None or source_url is None:
            errors.append(
                ImportErrorRecord(
                    source_file=_rel_source(path),
                    row_ref=str(row.line_number),
                    message="papers/README.md row is missing a local PDF path or source URL",
                    raw_row=row.raw,
                )
            )
            continue
        parsed.append(
            _BibliographyRow(
                row_number=index,
                title=_plain_text(row.cells[1]),
                why_included=_plain_text(row.cells[2]),
                source_url=source_url,
                local_path=local_path,
                source_file=_rel_source(path),
                line_number=row.line_number,
                raw=row.raw,
            )
        )
    return parsed


def _load_coverage_assignments(
    path: Path, errors: list[ImportErrorRecord]
) -> dict[str, _CategoryAssignment]:
    rows = _parse_markdown_table(
        path,
        expected_headers=("File", "Category"),
        errors=errors,
    )
    assignments: dict[str, _CategoryAssignment] = {}
    for row in rows:
        local_path = _extract_pdf_path(row.cells[0])
        category = _plain_text(row.cells[1])
        if local_path is None or not category:
            errors.append(
                ImportErrorRecord(
                    source_file=_rel_source(path),
                    row_ref=str(row.line_number),
                    message="coverage row is missing a local PDF path or category",
                    raw_row=row.raw,
                )
            )
            continue
        filename = PurePosixPath(local_path).name
        if filename in assignments:
            errors.append(
                ImportErrorRecord(
                    source_file=_rel_source(path),
                    row_ref=str(row.line_number),
                    message=f"duplicate coverage assignment for {filename}",
                    raw_row=row.raw,
                )
            )
            continue
        assignments[filename] = _CategoryAssignment(
            category=category,
            source_file=_rel_source(path),
            line_number=row.line_number,
            raw=row.raw,
        )
    return assignments


def _load_category_file_assignments(
    categories_dir: Path, errors: list[ImportErrorRecord]
) -> dict[str, _CategoryAssignment]:
    assignments: dict[str, _CategoryAssignment] = {}
    for path in sorted(categories_dir.glob("[0-9][0-9]_*.md")):
        category = _first_heading(path)
        rows = _parse_markdown_table(
            path,
            expected_headers=("Local PDF", "Study", "Why it is in this category", "Source"),
            errors=errors,
        )
        if not category:
            errors.append(
                ImportErrorRecord(
                    source_file=_rel_source(path),
                    row_ref="1",
                    message="category file is missing an H1 category heading",
                    raw_row="",
                )
            )
            continue
        for row in rows:
            local_path = _extract_pdf_path(row.cells[0])
            if local_path is None:
                errors.append(
                    ImportErrorRecord(
                        source_file=_rel_source(path),
                        row_ref=str(row.line_number),
                        message="category row is missing a local PDF path",
                        raw_row=row.raw,
                    )
                )
                continue
            filename = PurePosixPath(local_path).name
            if filename in assignments:
                errors.append(
                    ImportErrorRecord(
                        source_file=_rel_source(path),
                        row_ref=str(row.line_number),
                        message=f"duplicate category-file assignment for {filename}",
                        raw_row=row.raw,
                    )
                )
                continue
            assignments[filename] = _CategoryAssignment(
                category=category,
                source_file=_rel_source(path),
                line_number=row.line_number,
                raw=row.raw,
            )
    return assignments


def _parse_markdown_table(
    path: Path,
    *,
    expected_headers: Sequence[str],
    errors: list[ImportErrorRecord],
) -> list[_TableRow]:
    if not path.exists():
        errors.append(
            ImportErrorRecord(
                source_file=_rel_source(path),
                row_ref="file",
                message="required corpus file is missing",
                raw_row="",
            )
        )
        return []

    expected = tuple(_normal_text(header) for header in expected_headers)
    rows: list[_TableRow] = []
    inside_target_table = False
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw.strip()
        if not stripped.startswith("|"):
            if inside_target_table:
                break
            continue
        cells = _split_table_row(stripped)
        if not cells:
            continue
        normalized = tuple(_normal_text(cell) for cell in cells)
        if normalized == expected:
            inside_target_table = True
            continue
        if not inside_target_table:
            continue
        if _is_separator_row(cells):
            continue
        if len(cells) != len(expected_headers):
            errors.append(
                ImportErrorRecord(
                    source_file=_rel_source(path),
                    row_ref=str(line_number),
                    message=(
                        f"expected {len(expected_headers)} cells in markdown row, "
                        f"got {len(cells)}"
                    ),
                    raw_row=raw,
                )
            )
            continue
        rows.append(_TableRow(line_number=line_number, cells=tuple(cells), raw=raw))
    if not inside_target_table:
        errors.append(
            ImportErrorRecord(
                source_file=_rel_source(path),
                row_ref="header",
                message=f"markdown table header was not found: {' | '.join(expected_headers)}",
                raw_row="",
            )
        )
    return rows


def _split_table_row(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _is_separator_row(cells: Sequence[str]) -> bool:
    return all(cell and set(cell.replace(" ", "")) <= {"-", ":"} for cell in cells)


def _parse_int(value: str) -> int | None:
    normalized = _plain_text(value).strip()
    if not normalized.isdigit():
        return None
    return int(normalized)


def _extract_pdf_path(cell: str) -> str | None:
    link_match = _LINK_RE.search(cell)
    if link_match is not None:
        candidate = link_match.group(2)
    else:
        backtick_match = _BACKTICK_RE.search(cell)
        candidate = backtick_match.group(1) if backtick_match is not None else cell
    candidate = candidate.strip()
    if not candidate.endswith(".pdf"):
        return None
    while candidate.startswith("../"):
        candidate = candidate[3:]
    if candidate.startswith("./"):
        candidate = candidate[2:]
    if "/" not in candidate:
        candidate = f"papers/{candidate}"
    return candidate


def _extract_url(cell: str) -> str | None:
    match = _URL_RE.search(cell)
    if match is None:
        return None
    return match.group(0).rstrip(".,;")


def _plain_text(cell: str) -> str:
    def replace_link(match: re.Match[str]) -> str:
        return match.group(1)

    value = _LINK_RE.sub(replace_link, cell)
    value = _BACKTICK_RE.sub(lambda match: match.group(1), value)
    return _WHITESPACE_RE.sub(" ", value.replace("\\", "")).strip()


def _normal_text(value: str) -> str:
    return _plain_text(value).casefold()


def _first_heading(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _record_duplicate_field_errors(
    rows: Sequence[_BibliographyRow],
    field_name: str,
    source_file: str,
    errors: list[ImportErrorRecord],
) -> None:
    seen: dict[str, _BibliographyRow] = {}
    for row in rows:
        value = str(getattr(row, field_name))
        previous = seen.get(value)
        if previous is not None:
            errors.append(
                ImportErrorRecord(
                    source_file=source_file,
                    row_ref=str(row.line_number),
                    message=(
                        f"duplicate {field_name} {value!r}; first seen at line "
                        f"{previous.line_number}"
                    ),
                    raw_row=row.raw,
                )
            )
            continue
        seen[value] = row


def _rows_by_filename(
    rows: Sequence[_BibliographyRow],
    source_file: str,
    errors: list[ImportErrorRecord],
) -> dict[str, _BibliographyRow]:
    by_filename: dict[str, _BibliographyRow] = {}
    for row in rows:
        if row.filename in by_filename:
            errors.append(
                ImportErrorRecord(
                    source_file=source_file,
                    row_ref=str(row.line_number),
                    message=f"duplicate filename {row.filename!r}",
                    raw_row=row.raw,
                )
            )
            continue
        by_filename[row.filename] = row
    return by_filename


def _error_from_row(
    row: _BibliographyRow | None,
    source_file: str,
    message: str,
) -> ImportErrorRecord:
    return ImportErrorRecord(
        source_file=source_file if row is None else row.source_file,
        row_ref="unknown" if row is None else str(row.line_number),
        message=message,
        raw_row="" if row is None else row.raw,
    )


def _dataset_leads_from_papers(
    papers: Sequence[CorpusPaper],
    category_file_assignments: Mapping[str, _CategoryAssignment],
) -> list[DatasetLead]:
    by_category: dict[str, list[CorpusPaper]] = {}
    for paper in papers:
        by_category.setdefault(paper.category, []).append(paper)

    leads: list[DatasetLead] = []
    for category, category_papers in sorted(by_category.items()):
        filenames = [PurePosixPath(paper.local_path).name for paper in category_papers]
        local_path = _category_source_file(filenames, category_file_assignments)
        hints = sorted(
            {hint for paper in category_papers for hint in paper.metadata.get("dataset_hints", [])}
        )
        leads.append(
            DatasetLead(
                dataset_id=f"dataset-lead-{_slug(category)}",
                name=f"{category} corpus lead",
                source_url=None,
                local_path=local_path,
                metadata={
                    "lead_type": "category_seed",
                    "category": category,
                    "paper_count": len(category_papers),
                    "paper_ids": [paper.paper_id for paper in category_papers],
                    "source_urls": [paper.source_url for paper in category_papers],
                    "dataset_hints": hints,
                },
            )
        )
    return leads


def _category_source_file(
    filenames: Sequence[str],
    category_file_assignments: Mapping[str, _CategoryAssignment],
) -> str | None:
    for filename in filenames:
        assignment = category_file_assignments.get(filename)
        if assignment is not None:
            return assignment.source_file
    return None


def _dataset_hints(row: _BibliographyRow) -> list[str]:
    haystack = f"{row.title} {row.why_included} {row.local_path}".casefold()
    hints: list[str] = []
    keyword_groups = {
        "bao": ("bao", "baryon acoustic", "desi", "boss", "eboss", "wigglez", "6df"),
        "cmb": ("cmb", "planck", "act", "spt", "wmap", "recombination", "bbn"),
        "clusters": ("cluster", "clusters", "abundance"),
        "cosmic_chronometers": ("chronometer", "chronometers"),
        "distance_ladder": ("cepheid", "shoes", "distance ladder", "trgb", "jagb"),
        "frb": ("fast radio burst", "frb"),
        "growth": ("growth", "s8", "sigma8", "structure"),
        "standard_sirens": ("standard siren", "gravitational-wave", "gw", "gwtc"),
        "supernovae": ("supernova", "supernovae", "sn ia", "pantheon", "jla"),
        "time_delay_lensing": ("time-delay", "time delay", "lensed", "tdcosmo", "h0licow"),
        "weak_lensing": ("weak lensing", "cosmic shear", "lensing"),
    }
    for hint, keywords in sorted(keyword_groups.items()):
        if any(keyword in haystack for keyword in keywords):
            hints.append(hint)
    return hints or ["literature_constraint"]


def _slug(value: str) -> str:
    slug = _NON_SLUG_RE.sub("-", value.casefold()).strip("-")
    return slug or "uncategorized"


def _rel_source(path: Path) -> str:
    parts = path.parts
    for anchor in ("categories", "papers"):
        if anchor in parts:
            return str(PurePosixPath(*parts[parts.index(anchor) :]))
    return path.name
