"""Age-buffer live own-dent S from I0 and G0 table."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .i0 import i0_bps


@dataclass
class OwnTake:
    age: int  # in trade-count steps; 1 = just taken
    impact: float  # same units as G0 / I0 (bps)


@dataclass
class AgeBuffer:
    G0: np.ndarray  # G0[0]=G0(1), ...
    i0_fit: dict
    takes: list[OwnTake] = field(default_factory=list)

    @property
    def L_keep(self) -> int:
        return len(self.G0)

    def on_own_take(self, q: float) -> None:
        impact = float(i0_bps(q, self.i0_fit))
        self.takes.append(OwnTake(age=1, impact=impact))

    def on_public_trade(self, n_steps: int = 1) -> None:
        for t in self.takes:
            t.age += n_steps
        L = self.L_keep
        self.takes = [t for t in self.takes if t.age <= L]

    def S(self, extra_lag: int = 0) -> float:
        """Residual dent; extra_lag for candidate wait τ → ℓ̂."""
        if not self.takes:
            return 0.0
        g0_1 = self.G0[0]
        if g0_1 == 0:
            return 0.0
        s = 0.0
        for t in self.takes:
            ell = t.age + extra_lag
            if ell < 1 or ell > self.L_keep:
                continue
            s += t.impact * (self.G0[ell - 1] / g0_1)
        return float(s)

    def g(self, ell: int) -> float:
        if ell < 1 or ell > self.L_keep:
            return 0.0
        return float(self.G0[ell - 1] / self.G0[0])
