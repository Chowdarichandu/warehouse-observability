import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Kind = Literal["null_rate", "duplicate_keys", "accepted_values", "schema_contract"]


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", value):
        raise ValueError("Use a simple warehouse identifier of at most 63 characters")
    return value


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NullRate(Params):
    column: str
    max_null_rate: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    _column = field_validator("column")(identifier)


class DuplicateKeys(Params):
    columns: list[str] = Field(min_length=1, max_length=8)
    max_duplicate_rate: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)

    @field_validator("columns")
    @classmethod
    def columns_valid(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Key columns must be distinct")
        return [identifier(item) for item in value]


class AcceptedValues(Params):
    column: str
    values: list[str] = Field(min_length=1, max_length=100)
    max_invalid_rate: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    _column = field_validator("column")(identifier)

    @field_validator("values")
    @classmethod
    def values_valid(cls, value: list[str]) -> list[str]:
        if any(len(item) > 200 for item in value):
            raise ValueError("Accepted values must be at most 200 characters")
        return list(dict.fromkeys(value))


class SchemaContract(Params):
    columns: dict[str, str] = Field(min_length=1, max_length=100)
    allow_extra: bool = True

    @field_validator("columns")
    @classmethod
    def columns_valid(cls, value: dict[str, str]) -> dict[str, str]:
        for name, data_type in value.items():
            identifier(name)
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_ ]{0,79}", data_type):
                raise ValueError("Use an information_schema data_type name")
        return {name: data_type.lower().strip() for name, data_type in value.items()}


PARAM_TYPES = {
    "null_rate": NullRate,
    "duplicate_keys": DuplicateKeys,
    "accepted_values": AcceptedValues,
    "schema_contract": SchemaContract,
}


class QualityCheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    table_name: str
    kind: Kind
    params: dict[str, Any]
    sample_limit: int = Field(default=1000, ge=1, le=10000)
    interval_sec: int = Field(default=900, ge=60, le=86400)
    enabled: bool = True
    _table = field_validator("table_name")(identifier)

    @model_validator(mode="after")
    def valid_params(self) -> "QualityCheckInput":
        self.params = PARAM_TYPES[self.kind].model_validate(self.params).model_dump()
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Name cannot be blank")
        return self


class QualityResult(BaseModel):
    id: int
    check_id: int
    tenant_id: str
    status: Literal["pass", "fail", "error"]
    sampled_rows: int
    details: dict[str, Any]
    simulated: bool
    checked_at: datetime


class QualityCheck(QualityCheckInput):
    id: int
    created_at: datetime
    updated_at: datetime
    last_checked_at: datetime | None
    latest_result: QualityResult | None = None


class QualityCheckPage(BaseModel):
    items: list[QualityCheck]
    total: int


class QualityResultPage(BaseModel):
    items: list[QualityResult]
    total: int


class QualityCheckPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
