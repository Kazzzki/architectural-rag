import os
import yaml
import re
from typing import List, Dict, Any, Tuple
from core.models import DiscoverySummary, MatchResult, Profile, ProfileField

def load_profiles(profiles_dir: str) -> List[Profile]:
    profiles = []
    if not os.path.exists(profiles_dir):
        return profiles
        
    for filename in os.listdir(profiles_dir):
        if filename.endswith(".yaml"):
            with open(os.path.join(profiles_dir, filename), "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                
                fields = [ProfileField(**fld) for fld in data.get("data_model", {}).get("fields", [])]
                
                profile = Profile(
                    id=data["id"],
                    name=data["name"],
                    description=data["description"],
                    version=str(data.get("version", "1.0")),
                    min_score_required=float(data.get("matching_rules", {}).get("min_score_required", 0.0)),
                    sheet_name_patterns=data.get("matching_rules", {}).get("sheet_name_patterns", []),
                    required_headers=data.get("matching_rules", {}).get("required_headers", []),
                    header_aliases=data.get("header_aliases", {}),
                    fields=fields,
                    allow_unlisted_columns=data.get("operations", {}).get("allow_unlisted_columns", True),
                    allow_row_deletion=data.get("operations", {}).get("allow_row_deletion", False)
                )
                profiles.append(profile)
    return profiles

def match_profile(summary: DiscoverySummary, profiles_dir: str) -> MatchResult:
    """
    Phase 3: Profile Matching
    Matches the discovered structure against known profiles.
    """
    profiles = load_profiles(profiles_dir)
    
    best_profile_id = "generic_tabular_v1"
    best_score = 0.0
    reason = "Fallback to generic profile"
    is_fallback = True
    
    # Simple scoring logic (backward compatibility for CLI tests)
    for sheet, raw_rows in summary.raw_data.items():
        # Flatten first 5 rows to use as header candidates
        headers = []
        for row in raw_rows[:5]:
            for cell in row:
                if cell and str(cell).strip():
                    headers.append(str(cell).strip())
                    
        if not headers:
            continue
            
        for profile in profiles:
            if profile.id == "generic_tabular_v1":
                continue
                
            score = 0.0
            
            # Check sheet name
            sheet_match = False
            for pattern in profile.sheet_name_patterns:
                if re.match(pattern, sheet, re.IGNORECASE):
                    sheet_match = True
                    break
            
            if sheet_match:
                score += 0.3
                
            # Check headers
            matched_required = 0
            for req_h in profile.required_headers:
                # check direct or alias
                aliases = profile.header_aliases.get(req_h, [])
                candidates = [req_h] + aliases
                
                for h in headers:
                    if h in candidates:
                        matched_required += 1
                        break
                        
            if profile.required_headers:
                header_score = matched_required / len(profile.required_headers)
                score += header_score * 0.7
                
            if score >= profile.min_score_required and score > best_score:
                best_score = score
                best_profile_id = profile.id
                reason = f"Matched {profile.name} with score {score:.2f} on sheet '{sheet}'"
                is_fallback = False
                
    return MatchResult(
        matched_profile_id=best_profile_id,
        score=best_score,
        reason=reason,
        is_fallback=is_fallback
    )
