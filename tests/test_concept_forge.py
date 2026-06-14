from __future__ import annotations

from hubble_tension.concept_forge import (
    ConceptForge,
    DuplicateDetector,
    FictionSource,
    PriorArtChecker,
    SciFiMotifMiner,
    motif_closure_status,
)

MOCK_CORPUS = {
    "papers": [
        {"paper_id": "paper-1", "title": "Early dark energy no-go with BAO constraints"}
    ]
}


def test_concept_forge_generates_w0_to_w4_with_replayable_metadata() -> None:
    concepts = ConceptForge(seed=17).generate(MOCK_CORPUS)

    assert {concept.wildness_level for concept in concepts} >= {"W0", "W1", "W2", "W3", "W4"}
    for concept in concepts:
        payload = concept.as_hypothesis_json()
        assert payload["seed"] == 17
        assert payload["operators"]
        assert payload["parameter_budget"] >= 2
        assert payload["assumption_diff"]
        assert payload["falsification_tests"]


def test_prior_art_and_duplicate_detection_are_deterministic() -> None:
    concept = next(
        item for item in ConceptForge(seed=17).generate(MOCK_CORPUS) if item.wildness_level == "W3"
    )

    prior_art = PriorArtChecker(MOCK_CORPUS).check(concept)

    assert prior_art["requires_prior_art"] is True
    assert prior_art["searched_sources"] == ["local_corpus"]
    assert DuplicateDetector().is_duplicate(concept.concept_text, [concept.concept_text])


def test_fiction_motif_is_inspiration_only_and_closes_after_three_failures() -> None:
    source = FictionSource(
        source_id="fiction-1",
        title="Allowed source",
        license_kind="public_domain",
        text="A hidden boundary changes the visible world.",
        consecutive_failed_ab_cycles=3,
    )

    motifs = SciFiMotifMiner().mine(source)
    closure = motif_closure_status(source)

    assert motifs[0].fiction_inspiration_only is True
    assert motifs[0].source_kind == "fiction_motif"
    assert closure["new_status"] == "disabled_permanent"
    assert closure["config_migration_required_to_reenable"] is True
