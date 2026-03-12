import json
import os
from typing import Optional
from core.models_v2 import MappingSpec, WriteContract

def save_mapping(mapping: MappingSpec, filepath: str):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(mapping.to_dict(), f, indent=2, ensure_ascii=False)

def load_mapping(filepath: str) -> MappingSpec:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Mapping file not found: {filepath}")
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return MappingSpec.from_dict(data)

def save_contract(contract: WriteContract, filepath: str):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(contract.to_dict(), f, indent=2, ensure_ascii=False)

def load_contract(filepath: str) -> WriteContract:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Contract file not found: {filepath}")
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return WriteContract.from_dict(data)
