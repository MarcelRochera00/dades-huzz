"""Lane A: the serving loop that answers live requests, the handover between laptops, and the serving report."""

from dades_huzz.serving.handover import decide_role
from dades_huzz.serving.loop import (
    ANSWER_SIZE,
    Recommend,
    answer,
    repair,
    serve,
    validate,
)
from dades_huzz.serving.report import FEEDBACK_LAG_S, serving_report

__all__ = [
    "ANSWER_SIZE",
    "FEEDBACK_LAG_S",
    "Recommend",
    "answer",
    "decide_role",
    "repair",
    "serve",
    "serving_report",
    "validate",
]
