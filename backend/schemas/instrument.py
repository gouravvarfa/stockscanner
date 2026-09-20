"""Schema mixin that stamps every symbol-carrying API model with the ONE
centralized FUTURE/EQUITY classification (services/instrument_classifier.py).
Pure display metadata — never a strategy filter."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

from backend.services.instrument_classifier import get_instrument_type


class InstrumentTyped(BaseModel):
    instrument_type: Literal["FUTURE", "EQUITY"] = "EQUITY"

    @model_validator(mode="after")
    def _classify(self):
        # Index underlyings (NIFTY, BANKNIFTY...) only ever trade as futures.
        if getattr(self, "instrument_class", None) == "INDEX":
            self.instrument_type = "FUTURE"
        else:
            self.instrument_type = get_instrument_type(getattr(self, "symbol", None))
        return self


class FnoTyped(BaseModel):
    """Same classification under the name `fno_type` — for the Expiry Level
    signal models, whose existing `instrument_type` field already means
    STOCK/INDEX and must not change."""
    fno_type: Literal["FUTURE", "EQUITY"] = "EQUITY"

    @model_validator(mode="after")
    def _classify(self):
        self.fno_type = get_instrument_type(getattr(self, "symbol", None))
        return self
