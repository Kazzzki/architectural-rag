import os
import yaml
import re
from typing import List, Dict, Any
from core.models_v2 import ProfileV2, WorkbookManifest

class MatchResultV2:
    def __init__(self, matched_profile_id: str, score: float, reason: str, is_fallback: bool):
        self.matched_profile_id = matched_profile_id
        self.score = score
        self.reason = reason
        self.is_fallback = is_fallback
        
    def to_dict(self):
        return {
            "matched_profile_id": self.matched_profile_id,
            "score": self.score,
            "reason": self.reason,
            "is_fallback": self.is_fallback
        }

def load_profiles_v2(profiles_dir: str) -> List[ProfileV2]:
    profiles = []
    if not os.path.exists(profiles_dir):
        return profiles
        
    for filename in os.listdir(profiles_dir):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            with open(os.path.join(profiles_dir, filename), "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                try:
                    profiles.append(ProfileV2.from_dict(data))
                except Exception as e:
                    print(f"Warning: Could not parse profile {filename}: {e}")
    return profiles

def match_profile_v2(manifest: WorkbookManifest, profiles_dir: str) -> MatchResultV2:
    """
    Phase 4: Profile Matching (V2)
    Scores a WorkbookManifest against known ProfileV2 YAML definitions.
    """
    profiles = load_profiles_v2(profiles_dir)
    
    best_profile_id = "generic_tabular_v1"
    best_score = 0.0
    reason = "Fallback to generic profile"
    is_fallback = True
    
    for sheet_manifest in manifest.sheets:
        # Extract potential headers
        headers = []
        if sheet_manifest.header_candidates:
            for candidate in sheet_manifest.header_candidates:
                for h in candidate.get("values", []):
                    if h and str(h).strip():
                        headers.append(str(h).strip())
                        
        if not headers:
            continue
            
        for profile in profiles:
            if profile.profile_id == "generic_tabular_v1":
                continue
                
            score = 0.0
            
            # Check sheet name
            sheet_match = False
            for pattern in profile.sheet_candidates:
                if re.match(pattern, sheet_manifest.sheet_name, re.IGNORECASE):
                    sheet_match = True
                    break
            
            if sheet_match:
                score += 0.3
                
            # Check headers
            matched_required = 0
            for req_field in profile.required_fields:
                req_name = req_field.name
                aliases = profile.header_aliases.get(req_name, [])
                candidates = [req_name] + aliases
                
                for h in headers:
                    if h in candidates:
                        matched_required += 1
                        break
                        
            if profile.required_fields:
                header_score = matched_required / len(profile.required_fields)
                score += header_score * 0.7
                
            min_score = profile.profile_match_rules.min_match_ratio if profile.profile_match_rules else 0.8
            
            if score >= min_score and score > best_score:
                best_score = score
                best_profile_id = profile.profile_id
                reason = f"Matched {profile.name} with score {score:.2f} on sheet '{sheet_manifest.sheet_name}'"
                is_fallback = False
                
    return MatchResultV2(
        matched_profile_id=best_profile_id,
        score=best_score,
        reason=reason,
        is_fallback=is_fallback
    )
