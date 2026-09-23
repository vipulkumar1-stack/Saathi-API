"""Hand-written, IDE-discoverable methods for a few finex operations that
get deeper, schema-validated tests. Everything else in finex is still
covered through GenericClient - this file is the pattern to extend when a
test needs named clarity instead of a string lookup.
"""
from src.clients.generic_client import GenericClient
from src.core.response import ApiResponse


class FinexClient:
    def __init__(self, generic: GenericClient):
        self._generic = generic

    def bank_list(self, api_called_by: str = "partner") -> ApiResponse:
        return self._generic.call_operation(
            "finex", "BankList", variables_override={"api_called_by": api_called_by}
        )

    def get_role_access_features(self, role_id: float) -> ApiResponse:
        return self._generic.call_operation(
            "finex", "GetRoleAccessFeatures", variables_override={"role_id": role_id}
        )

    def save_remark(self, lead_id: int, remark: str, user_id: str, remark_type: int = 1) -> ApiResponse:
        return self._generic.call_operation(
            "finex",
            "saveRemark",
            variables_override={
                "LeadData": {
                    "lead_id": lead_id,
                    "remark_type": remark_type,
                    "remark": remark,
                    "user_id": user_id,
                    "section": "",
                    "sub_section": "",
                }
            },
        )
