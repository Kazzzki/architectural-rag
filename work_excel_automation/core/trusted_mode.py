from typing import List, Dict, Any
from core.models_v2 import WorkbookManifest, WriteContract, ProfileV2
from core.profile_matcher_v2 import MatchResultV2

class TrustedModeEvaluation:
    def __init__(self, is_trusted: bool, reasons: List[str]):
        self.is_trusted = is_trusted
        self.reasons = reasons
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_trusted": self.is_trusted,
            "reasons": self.reasons
        }

def evaluate_trusted_mode(
    manifest: WorkbookManifest,
    match_result: MatchResultV2, 
    contract: WriteContract,
    strict_row_append_only: bool = True
) -> TrustedModeEvaluation:
    """
    Phase 3: Trusted Mode Validation
    Evaluates if a given matched sheet can proceed without Human-in-the-Loop confirming operations.
    """
    reasons = []
    is_trusted = True
    
    # 1. Match score must be perfect (1.0 or very high depending on Profile logic)
    if match_result.score < 1.0:
        is_trusted = False
        reasons.append(f"Match score ({match_result.score}) is below 1.0. Human review required.")
        
    if match_result.is_fallback:
        is_trusted = False
        reasons.append("Matched to fallback generic profile instead of specific verified profile.")

    # 2. Risk flags in Manifest must be non-critical
    # E.g., if there's password protection or weird hidden stuff, we might want to alert a human
    for sheet_manifest in manifest.sheets:
        if sheet_manifest.sheet_name == contract.target_sheet:
            dangerous_flags = [f for f in sheet_manifest.risk_flags if f in ("sheet_protected", "has_hidden_rows")]
            if dangerous_flags:
                is_trusted = False
                reasons.append(f"Target sheet contains risk flags: {dangerous_flags}")
            break

    # 3. Contract must be 'safe' (Append only, no overwriting existing read_only_ranges)
    if strict_row_append_only:
        if "overwrite_cell" not in contract.forbidden_operations:
            is_trusted = False
            reasons.append("Contract does not forbid 'overwrite_cell', missing strict safety guarantees.")
            
        if "delete_row" not in contract.forbidden_operations:
            is_trusted = False
            reasons.append("Contract does not forbid 'delete_row', missing strict safety guarantees.")

    if is_trusted:
        reasons.append("All trusted mode criteria met. Execution may proceed without human confirmation.")
        
    return TrustedModeEvaluation(is_trusted=is_trusted, reasons=reasons)
