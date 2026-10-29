"""
Clinical Decision Support (CDS) Engine
Standardized pharmacological verification, RxNorm normalization, OpenFDA labeling, and clinical rules.
"""

from .rxnorm_normalizer import normalize as rxnorm_normalize
from .openfda_label import get_label as get_openfda_label
from .clinical_rules import run_all as evaluate_clinical_rules
from .clinical_llm import explain_with_meta as explain_clinical_findings

__all__ = [
    "rxnorm_normalize",
    "get_openfda_label",
    "evaluate_clinical_rules",
    "explain_clinical_findings",
]
