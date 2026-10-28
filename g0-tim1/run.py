#!/usr/bin/env python3
"""Run mock + TIM1 training pipeline, then the metrics test report."""

from g0_tim1.pipeline import run
from g0_tim1.report import generate_report


if __name__ == "__main__":
    meta = run()
    metrics = generate_report()
    print("Done:", meta)
    print("Test report:", metrics["checklist"])
