from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator


class SorteoCreate(BaseModel):
    fecha: str = Field(..., description="Fecha del sorteo, ej: 2026-10-22 o 2026-10-22 21:30:00")
    n1: int = Field(..., ge=1, le=49)
    n2: int = Field(..., ge=1, le=49)
    n3: int = Field(..., ge=1, le=49)
    n4: int = Field(..., ge=1, le=49)
    n5: int = Field(..., ge=1, le=49)
    n6: int = Field(..., ge=1, le=49)
    complementario: Optional[int] = Field(None, ge=1, le=49)
    reintegro: Optional[int] = Field(None, ge=0, le=9)
    joker: Optional[str] = Field(None)
    bote: Optional[float] = Field(0.0, ge=0.0)

    @field_validator("n6")
    @classmethod
    def validate_unique_numbers(cls, v, values):
        data = values.data
        nums = [data.get("n1"), data.get("n2"), data.get("n3"),
                data.get("n4"), data.get("n5"), v]
        if any(n is None for n in nums):
            return v
        if len(set(nums)) < 6:
            raise ValueError("Los 6 números de la combinación deben ser diferentes entre sí.")
        return v


class SorteoResponse(BaseModel):
    id: int
    id_sorteo: str
    fecha: str
    combinacion: str
    n1: int
    n2: int
    n3: int
    n4: int
    n5: int
    n6: int
    complementario: Optional[int]
    joker: Optional[str]
    reintegro: Optional[int]
    bote: float


class PremioResponse(BaseModel):
    id: int
    id_sorteo: str
    tipo_juego: Optional[str]
    categoria_nombre: Optional[str]
    ganadores: int
    importe_premio: float


class PronosticoQuery(BaseModel):
    strategy: str = "all"
    window: int = 0
    count: int = 5


class BacktestQuery(BaseModel):
    strategy: str = "reversion"
    window_size: int = 100
    max_evals: int = 200
