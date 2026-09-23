"""Per-mutation safety profiles for the gated mutation sweep.

This is the default-deny registry: a mutation from src/spec/operations.py
can only run if it has an entry here. A newly re-imported mutation with
no entry stays skipped, with a reason naming the missing profile - it
never silently starts running. See tests/unit/test_mutation_profiles.py
and the plan at ~/.claude/plans/i-want-to-be-steady-whistle.md.

Cleanup reality check: the captured spec (src/spec/operations.py) has NO
delete/revert mutations at all - it's a straight Postman import of
whatever traffic was captured, and nobody happened to capture a delete
call. So every profile below is `cleanup=None` with an explicit
`cleanup_reason`. This is a real limitation, not an oversight: every
mutation run leaves a permanent record on `pre`. tests/mutations/conftest.py
logs every run to mutations-uncleaned.json so what's left behind is at
least traceable, and the tier system below at least keeps the sweep from
ever reaching a real external party by accident.

Tiers:
  isolated - writes only Ambak-internal data. Gated by ALLOW_MUTATIONS.
  external - reaches a real lender, credit bureau, or paid provider, and
             is categorically irreversible. Gated by ALLOW_MUTATIONS AND
             ALLOW_EXTERNAL_MUTATIONS (see src/config/settings.py).
"""
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from src.spec.types import OperationDef
from src.testdata.mutation_data import (
    SYNTHETIC_CITY,
    SYNTHETIC_LOAN_AMOUNT,
    SYNTHETIC_PINCODE,
    fake_email,
    fake_last_name,
    fake_mobile,
    fake_name,
    fake_pan,
    fake_remark,
    fake_role_name,
)


@dataclass(frozen=True)
class MutationProfile:
    tier: str  # "isolated" | "external"
    overrides: Callable[[OperationDef], dict]
    cleanup: Optional[Callable[[OperationDef, dict], None]] = None
    cleanup_reason: str = ""

    def __post_init__(self):
        if self.tier not in ("isolated", "external"):
            raise ValueError(f"invalid tier {self.tier!r}")
        if self.cleanup is None and not self.cleanup_reason:
            raise ValueError("a profile with no cleanup must state cleanup_reason")


def _no_override(op: OperationDef) -> dict:
    """For mutations whose captured variables carry no PII worth
    replacing (e.g. reference an existing internal id only)."""
    return {}


def _lead_person_fields() -> dict:
    return {"FirstName": fake_name(), "LastName": fake_last_name()}


PROFILES: Dict[str, MutationProfile] = {
    "finex.UploadDocument": MutationProfile(
        tier="isolated",
        overrides=_no_override,
        cleanup_reason="no delete-document mutation exists in the captured spec",
    ),
    "finex.CalculateEodAverageForIndependent": MutationProfile(
        tier="isolated",
        overrides=_no_override,
        cleanup_reason="a calculation trigger, not a create - nothing to revert",
    ),
    "finex.create_loan": MutationProfile(
        tier="isolated",
        overrides=lambda op: {
            "newLeadInput": {
                **op.variables["newLeadInput"],
                "first_name": fake_name(),
                "last_name": fake_last_name(),
                "mobile": fake_mobile(),
            }
        },
        cleanup_reason="no delete-lead mutation exists in the captured spec",
    ),
    "finex.LinkIndependentAbbToLead": MutationProfile(
        tier="isolated",
        overrides=_no_override,
        cleanup_reason="links two existing internal ids - no unlink mutation captured",
    ),
    "finex.CalculateEodAverageBalanceForLead": MutationProfile(
        tier="isolated",
        overrides=_no_override,
        cleanup_reason="a calculation trigger, not a create - nothing to revert",
    ),
    "finex.save_additional_info": MutationProfile(
        tier="isolated",
        overrides=lambda op: {
            "LeadAdditionalInput": {
                **op.variables["LeadAdditionalInput"],
                "customer": {
                    **op.variables["LeadAdditionalInput"]["customer"],
                    "first_name": fake_name(),
                    "last_name": fake_last_name(),
                    "mobile": fake_mobile(),
                },
            }
        },
        cleanup_reason="no revert mutation captured for lead additional info",
    ),
    "finex.saveRole": MutationProfile(
        tier="isolated",
        overrides=lambda op: {
            "SaveRoleInput": {**op.variables["SaveRoleInput"], "name": fake_role_name()}
        },
        cleanup_reason="no delete-role mutation exists in the captured spec",
    ),
    "finex.saveFollowup": MutationProfile(
        tier="isolated",
        overrides=lambda op: {
            "CreateFollowupInput": {
                **op.variables["CreateFollowupInput"],
                "comment": fake_remark(),
            }
        },
        cleanup_reason="no delete-followup mutation exists in the captured spec",
    ),
    "finex.SaveDocument": MutationProfile(
        tier="isolated",
        overrides=_no_override,
        cleanup_reason="no delete-document mutation exists in the captured spec",
    ),
    "finex.save_bank_branch": MutationProfile(
        tier="isolated",
        overrides=lambda op: {
            "saveBankBranchInput": {
                **op.variables["saveBankBranchInput"],
                "branch_name": f"AUTOTEST_BRANCH_{fake_role_name()[-8:]}",
            }
        },
        cleanup_reason="no delete-branch mutation exists in the captured spec (master data)",
    ),
    "finex.save_banker_records": MutationProfile(
        tier="isolated",
        overrides=lambda op: {
            "createBankerRecordInput": {
                **op.variables["createBankerRecordInput"],
                "name": fake_name(),
                "email": fake_email(),
                "phone": fake_mobile(),
            }
        },
        cleanup_reason="no delete-banker mutation exists in the captured spec (master data)",
    ),
    "finex.update_lead_status": MutationProfile(
        tier="isolated",
        overrides=_no_override,
        cleanup_reason=(
            "mutates the shared fixture lead (2125209) used by other operations - "
            "no read-status query is wired up here to capture/restore the prior "
            "status, so this cannot be safely cleaned up yet (see plan's open "
            "questions); left in isolated tier rather than external only because "
            "the write itself stays inside Ambak"
        ),
    ),
    "finex.save_bank_poc_mapping": MutationProfile(
        tier="isolated",
        overrides=_no_override,
        cleanup_reason="no delete-mapping mutation exists in the captured spec",
    ),
    "finex.FetchHomeData": MutationProfile(
        tier="isolated",
        overrides=_no_override,
        cleanup_reason="captured as a mutation but looks read-only (search-style call) - nothing to revert",
    ),
    "insurance.CreateInsuranceLead": MutationProfile(
        tier="isolated",
        overrides=lambda op: {"input": {**op.variables["input"], "full_name": fake_name()}},
        cleanup_reason="no delete-insurance-lead mutation exists in the captured spec",
    ),
    "insurance.CaptureAdditionalDetails": MutationProfile(
        tier="isolated",
        overrides=_no_override,
        cleanup_reason="no revert mutation captured for insurance lead details",
    ),
    "bank-integration.SelectPropertyType": MutationProfile(
        tier="isolated",
        overrides=_no_override,
        cleanup_reason="writes with leadId: 0 in the capture - no revert mutation captured",
    ),
    "finex.saveRemark": MutationProfile(
        tier="isolated",
        overrides=lambda op: {
            "LeadData": {**op.variables["LeadData"], "remark": fake_remark()}
        },
        cleanup_reason="no delete-remark mutation exists in the captured spec",
    ),
    # -- external tier: reaches a real lender / credit bureau. Gated by
    # ALLOW_EXTERNAL_MUTATIONS on top of ALLOW_MUTATIONS. Do not soften
    # these overrides to "look more real" - the goal is to run these as
    # rarely and as syntheticly as possible.
    "bank-integration.indiashelter_createLead": MutationProfile(
        tier="external",
        overrides=lambda op: {"opts": {**op.variables["opts"], **_lead_person_fields()}},
        cleanup_reason="files a real application with India Shelter - categorically irreversible",
    ),
    "bank-integration.indiashelter_saveData": MutationProfile(
        tier="external",
        overrides=lambda op: {
            "payload": {
                **op.variables["payload"],
                "opts": {
                    **op.variables["payload"]["opts"],
                    **_lead_person_fields(),
                    "City": SYNTHETIC_CITY,
                    "Pincode": SYNTHETIC_PINCODE,
                    "Loan_amount_Required_Cust": SYNTHETIC_LOAN_AMOUNT,
                },
            }
        },
        cleanup_reason="writes real applicant data into India Shelter's system - categorically irreversible",
    ),
    "finex.get_stored_transunion_cibil_report": MutationProfile(
        tier="external",
        overrides=lambda op: {"pan_card": fake_pan()},
        cleanup_reason="pulls a live bureau report - a real, billable, irreversible bureau hit",
    ),
    "finex.save_tu_link_status": MutationProfile(
        tier="external",
        overrides=lambda op: {"input": {**op.variables["input"], "pancard_no": fake_pan()}},
        cleanup_reason="records a TransUnion bureau link/consent state - no revert mutation captured",
    ),
}


def get_profile(key: str) -> Optional[MutationProfile]:
    """key is '<service>.<name>', matching OperationDef service/name.
    Returns None for anything not explicitly classified - the default-deny
    behavior the whole registry exists to enforce."""
    return PROFILES.get(key)
