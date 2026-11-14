"""How recommenders are scored: offline on the old carousel log, and live on what our answers sold."""

from dades_huzz.evaluation.live import live_answers, signal_rates, wilson
from dades_huzz.evaluation.offline import (
    HISTORY_CASES,
    PairedDifference,
    Report,
    SlateIps,
    SlotOneIps,
    auc,
    carousel_report,
    evaluate,
    history_cases,
    log_likelihood,
    paired_difference,
    simulate_switch,
    slate_ips,
    slate_ips_by_request,
    slot1_ips,
    weighted_hit,
)

__all__ = [
    "HISTORY_CASES",
    "PairedDifference",
    "Report",
    "SlateIps",
    "SlotOneIps",
    "auc",
    "carousel_report",
    "evaluate",
    "history_cases",
    "live_answers",
    "log_likelihood",
    "paired_difference",
    "signal_rates",
    "simulate_switch",
    "slate_ips",
    "slate_ips_by_request",
    "slot1_ips",
    "weighted_hit",
    "wilson",
]
