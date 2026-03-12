from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime

@dataclass
class ProfileField:
    name: str
    type: str
    required: bool = True

@dataclass
class Profile:
    id: str
    name: str
    description: str
    version: str
    min_score_required: float
    sheet_name_patterns: List[str]
    required_headers: List[str]
    header_aliases: Dict[str, List[str]]
    fields: List[ProfileField]
    allow_unlisted_columns: bool = True
    allow_row_deletion: bool = False

@dataclass
class Precondition:
    type: str
    value: Any
    sheet: Optional[str] = None

@dataclass
class Operation:
    op: str
    sheet: str
    params: Dict[str, Any]
    reason: str

@dataclass
class Validation:
    type: str
    params: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Plan:
    run_id: str
    input_file: str
    output_file: str
    matched_profile: str
    operations: List[Operation]
    preconditions: List[Precondition] = field(default_factory=list)
    validations: List[Validation] = field(default_factory=list)
    schema_version: str = "1.0"
    mode: str = "safe"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "input_file": self.input_file,
            "output_file": self.output_file,
            "matched_profile": self.matched_profile,
            "mode": self.mode,
            "preconditions": [{"type": p.type, "value": p.value, "sheet": p.sheet} for p in self.preconditions],
            "operations": [{"op": o.op, "sheet": o.sheet, "params": o.params, "reason": o.reason} for o in self.operations],
            "validations": [{"type": v.type, "params": v.params} for v in self.validations],
            "created_at": self.created_at
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Plan":
        return cls(
            run_id=data["run_id"],
            input_file=data["input_file"],
            output_file=data["output_file"],
            matched_profile=data["matched_profile"],
            operations=[Operation(**o) for o in data["operations"]],
            preconditions=[Precondition(**p) for p in data.get("preconditions", [])],
            validations=[Validation(**v) for v in data.get("validations", [])],
            schema_version=data.get("schema_version", "1.0"),
            mode=data.get("mode", "safe"),
            created_at=data.get("created_at", datetime.now().isoformat())
        )

@dataclass
class IntakeResult:
    run_id: str
    original_path: str
    working_path: str
    file_hash: str
    file_size: int

@dataclass
class DiscoverySummary:
    sheets: List[str]
    dimensions: Dict[str, str] # sheet_name -> "A1:D10"
    raw_data: Dict[str, List[List[Any]]] # top 20 rows including None
    merged_cells: Dict[str, List[str]] # e.g. ["A1:C1", "D1:D2"]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sheets": self.sheets,
            "dimensions": self.dimensions,
            "raw_data": self.raw_data,
            "merged_cells": self.merged_cells
        }

@dataclass
class MatchResult:
    matched_profile_id: str
    score: float
    reason: str
    is_fallback: bool

@dataclass
class DryRunReport:
    run_id: str
    changed_sheets: List[str]
    estimated_cells_changed: int
    columns_added: int
    columns_removed: int
    formula_changes: int
    preconditions_met: bool
    stop_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "changed_sheets": self.changed_sheets,
            "estimated_cells_changed": self.estimated_cells_changed,
            "columns_added": self.columns_added,
            "columns_removed": self.columns_removed,
            "formula_changes": self.formula_changes,
            "preconditions_met": self.preconditions_met,
            "stop_reason": self.stop_reason
        }

@dataclass
class ExecuteResult:
    run_id: str
    success: bool
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    executed_operations: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "success": self.success,
            "output_path": self.output_path,
            "error_message": self.error_message,
            "executed_operations": self.executed_operations
        }

@dataclass
class VerifyReport:
    run_id: str
    success: bool
    diff_summary: Dict[str, Any]
    failed_validations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "success": self.success,
            "diff_summary": self.diff_summary,
            "failed_validations": self.failed_validations
        }
