from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class GFSBacktestRequest(BaseModel):
    symbol: str
    from_date: dt.datetime
    to_date: dt.datetime
