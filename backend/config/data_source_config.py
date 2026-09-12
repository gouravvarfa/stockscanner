from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

DataSourceMode = Literal["auto", "tapetide", "angel_one", "yahoo"]


class DataSourceConfig(BaseModel):
    mode: DataSourceMode = "auto"


DEFAULT_DATA_SOURCE_CONFIG = DataSourceConfig()
