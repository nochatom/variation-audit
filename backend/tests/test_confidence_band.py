"""Confidence band mapping (decision .21.3): low<0.5<=medium<0.8<=high."""
from decimal import Decimal

import pytest

from app.models import ConfidenceBand
from app.worker.job_worker import band_for_score


@pytest.mark.parametrize(
    "score, band",
    [
        (0.0, ConfidenceBand.low),
        (0.49, ConfidenceBand.low),
        (0.499, ConfidenceBand.low),
        (0.5, ConfidenceBand.medium),
        (0.79, ConfidenceBand.medium),
        (0.8, ConfidenceBand.high),
        (1.0, ConfidenceBand.high),
        (Decimal("0.95"), ConfidenceBand.high),
    ],
)
def test_band_boundaries(score, band):
    assert band_for_score(score) == band


def test_band_none():
    assert band_for_score(None) is None
