"""Opt-in offline experimental scorer. No import-time I/O or policy selection."""
from .score import SCORER_NAME, SCORER_VERSION, score_case, bind_v1_signature
from .annotations import load_annotations, validate_annotations
from .tables import TABLES_VERSION
__all__ = ['SCORER_NAME','SCORER_VERSION','TABLES_VERSION','score_case','bind_v1_signature','load_annotations','validate_annotations']
