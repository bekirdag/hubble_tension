from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetDescriptor:
    dataset_id: str
    name: str
    family: str
    covariance_status: str
    likelihood_status: str


class FixtureLikelihoodLoader:
    dataset_id = "fixture"
    name = "Fixture"
    family = "fixture"
    covariance_status = "summary"
    likelihood_status = "fixture"

    def descriptor(self) -> DatasetDescriptor:
        return DatasetDescriptor(
            dataset_id=self.dataset_id,
            name=self.name,
            family=self.family,
            covariance_status=self.covariance_status,
            likelihood_status=self.likelihood_status,
        )


class PantheonPlusLoader(FixtureLikelihoodLoader):
    dataset_id = "pantheon_plus"
    name = "Pantheon+ summary fixture"
    family = "sn"


class DESIBaoLoader(FixtureLikelihoodLoader):
    dataset_id = "desi_bao"
    name = "DESI BAO summary fixture"
    family = "bao"


class LegacyBaoLoader(FixtureLikelihoodLoader):
    dataset_id = "legacy_bao"
    name = "Legacy BAO summary fixture"
    family = "bao"


class SH0ESPriorLoader(FixtureLikelihoodLoader):
    dataset_id = "sh0es"
    name = "SH0ES local H0 summary fixture"
    family = "local_h0"


class BBNSummaryLoader(FixtureLikelihoodLoader):
    dataset_id = "bbn"
    name = "BBN summary fixture"
    family = "bbn"


class PlanckLiteLoader(FixtureLikelihoodLoader):
    dataset_id = "planck_lite"
    name = "Planck-lite compressed summary fixture"
    family = "cmb"


class ACTDR6Loader(FixtureLikelihoodLoader):
    dataset_id = "act_dr6"
    name = "ACT DR6 compressed summary fixture"
    family = "cmb"


class SPTGuardrailLoader(FixtureLikelihoodLoader):
    dataset_id = "spt_guardrail"
    name = "SPT summary guardrail fixture"
    family = "cmb_guardrail"


class LocalH0GuardrailLoader(FixtureLikelihoodLoader):
    dataset_id = "local_h0_guardrail"
    name = "Local H0 guardrail fixture"
    family = "local_h0"


class S8GuardrailLoader(FixtureLikelihoodLoader):
    dataset_id = "s8_guardrail"
    name = "S8/lensing/cluster guardrail fixture"
    family = "growth"


def default_dataset_registry() -> tuple[DatasetDescriptor, ...]:
    loaders = (
        PantheonPlusLoader(),
        DESIBaoLoader(),
        LegacyBaoLoader(),
        SH0ESPriorLoader(),
        BBNSummaryLoader(),
        PlanckLiteLoader(),
        ACTDR6Loader(),
        SPTGuardrailLoader(),
        LocalH0GuardrailLoader(),
        S8GuardrailLoader(),
    )
    return tuple(loader.descriptor() for loader in loaders)
