import json
import hashlib
import time
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict

# --------------------------
# 1. Manifest (Detailed Profiling)
# --------------------------
@dataclass
class FileInfo:
    filename: str
    extension: str
    size_bytes: int
    hash: str

@dataclass
class WorkbookMeta:
    sheet_count: int
    protected: bool

@dataclass
class ColumnProfile:
    col_idx: int
    col_label: str
    inferred_type: str
    null_ratio: float
    unique_est: int

@dataclass
class SheetManifest:
    sheet_name: str
    dimensions: str
    used_range: Dict[str, List[int]]  # {"start": [row, col], "end": [row, col]}
    hidden_rows: List[int]
    hidden_cols: List[str]
    merged_cells: List[str]
    header_candidates: List[Dict[str, Any]] # [{"row": int, "values": list}]
    table_candidates: List[Dict[str, int]]  # [{"start_row": int, "end_row": int}]
    formula_regions: List[str]
    column_profiles: List[ColumnProfile]
    risk_flags: List[str]
    profiling_confidence: float

@dataclass
class WorkbookManifest:
    manifest_version: str
    run_id: str
    file_info: FileInfo
    workbook_meta: WorkbookMeta
    sheets: List[SheetManifest]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkbookManifest':
        data['file_info'] = FileInfo(**data['file_info'])
        data['workbook_meta'] = WorkbookMeta(**data['workbook_meta'])
        
        sheets = []
        for sh in data['sheets']:
            sh['column_profiles'] = [ColumnProfile(**cp) for cp in sh.get('column_profiles', [])]
            sheets.append(SheetManifest(**sh))
        data['sheets'] = sheets
        return cls(**data)

# --------------------------
# 2. Mapping Spec
# --------------------------
@dataclass
class FieldMapping:
    source_header: str
    canonical_field: str
    confidence: float
    confirmed_by_user: bool

@dataclass
class MappingSpec:
    mapping_version: str
    profile_id: str
    sheet_name: str
    header_row: int
    field_mappings: List[FieldMapping]
    unmapped_headers: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MappingSpec':
        data['field_mappings'] = [FieldMapping(**fm) for fm in data.get('field_mappings', [])]
        return cls(**data)

# --------------------------
# 3. Write Contract
# --------------------------
@dataclass
class WriteContract:
    contract_version: str
    profile_id: str
    target_sheet: str
    read_only_ranges: List[str]
    write_allowed_ranges: List[str]
    formula_managed_ranges: List[str]
    protected_columns: List[str]
    row_boundary_rule: str
    forbidden_operations: List[str]
    postconditions: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WriteContract':
        return cls(**data)

# --------------------------
# 3.5. Profile (YAML/JSON)
# --------------------------
@dataclass
class ProfileField:
    name: str
    logical_type: str

@dataclass
class ProfileValidations:
    min_data_rows: int

@dataclass
class ProfileMatchRules:
    min_match_ratio: float

@dataclass
class ProfileV2:
    profile_version: str
    profile_id: str
    name: str
    sheet_candidates: List[str]
    header_aliases: Dict[str, List[str]]
    required_fields: List[ProfileField]
    optional_fields: List[ProfileField]
    transforms: List[Any]
    validations: ProfileValidations
    profile_match_rules: ProfileMatchRules
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProfileV2':
        data['required_fields'] = [ProfileField(**f) for f in data.get('required_fields', [])]
        data['optional_fields'] = [ProfileField(**f) for f in data.get('optional_fields', [])]
        if 'validations' in data:
            data['validations'] = ProfileValidations(**data['validations'])
        if 'profile_match_rules' in data:
            data['profile_match_rules'] = ProfileMatchRules(**data['profile_match_rules'])
        return cls(**data)

# --------------------------
# 4. Plan (v2)
# --------------------------
@dataclass
class OperationV2:
    op: str
    sheet: str
    params: Dict[str, Any]
    reason: str

@dataclass
class ValidationV2:
    type: str
    params: Dict[str, Any]

@dataclass
class PreconditionV2:
    type: str
    sheet: str
    row: Optional[int] = None

@dataclass
class PlanV2:
    version: str
    run_id: str
    input_file: str
    output_file: str
    matched_profile: str
    manifest_ref: str
    mapping_ref: str
    write_contract_ref: str
    preconditions: List[PreconditionV2]
    operations: List[OperationV2]
    validations: List[ValidationV2]
    approval_required: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlanV2':
        data['preconditions'] = [PreconditionV2(**p) for p in data.get('preconditions', [])]
        data['operations'] = [OperationV2(**o) for o in data.get('operations', [])]
        data['validations'] = [ValidationV2(**v) for v in data.get('validations', [])]
        return cls(**data)
