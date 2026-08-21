"""Composable policies and semantic records for evidence-driven improvement systems.

The deterministic policy kernel remains available as the low-level compatibility
surface while the package grows batteries-included validation, investigation,
improvement, and RSI workflows around the same canonical records.
"""

from .checkpoints import CheckpointPolicy
from .errors import RSITransitionError
from .experiments import ExperimentPolicy
from .hypotheses import HypothesisPolicy, ReflectionPolicy
from .identity import FrozenMap
from .kernel import RSIKernel
from .models import (
    CheckpointDecision,
    CommandExperimentInput,
    CommandObservation,
    ExperimentEvaluation,
    HypothesisProposal,
    HypothesisUpdate,
    PolicyEvaluationUpdate,
    PortfolioTransition,
)
from .portfolios import PortfolioPolicy
from .ports import ExperimentRunner
from .programs import ProgramPolicy
from .records import (
    ArtifactRef,
    Candidate,
    Claim,
    Constraint,
    Evaluation,
    Evidence,
    EvidenceRef,
    ExperimentSpec,
    Goal,
    Hypothesis,
    Intervention,
    Measurement,
    Observation,
    Outcome,
    Question,
    RecordRef,
    SemanticRecord,
    TargetRef,
    TargetSnapshot,
    Trial,
    deserialize_record,
    record_from_dict,
    serialize_record,
)
from .reviews import ReviewPolicy
from .selections import SelectionPolicy
from .selector_policies import SelectorPolicy

__all__ = [
    "ArtifactRef",
    "Candidate",
    "CheckpointDecision",
    "CheckpointPolicy",
    "Claim",
    "CommandExperimentInput",
    "CommandObservation",
    "Constraint",
    "Evaluation",
    "Evidence",
    "EvidenceRef",
    "ExperimentEvaluation",
    "ExperimentPolicy",
    "ExperimentRunner",
    "ExperimentSpec",
    "FrozenMap",
    "Goal",
    "Hypothesis",
    "HypothesisPolicy",
    "HypothesisProposal",
    "HypothesisUpdate",
    "Intervention",
    "Measurement",
    "Observation",
    "Outcome",
    "PolicyEvaluationUpdate",
    "PortfolioPolicy",
    "PortfolioTransition",
    "ProgramPolicy",
    "Question",
    "RSIKernel",
    "RSITransitionError",
    "RecordRef",
    "ReflectionPolicy",
    "ReviewPolicy",
    "SelectionPolicy",
    "SelectorPolicy",
    "SemanticRecord",
    "TargetRef",
    "TargetSnapshot",
    "Trial",
    "deserialize_record",
    "record_from_dict",
    "serialize_record",
]

__version__ = "0.2.0"
