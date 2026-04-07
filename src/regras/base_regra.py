"""Interface base para regras de auditoria + R01 implementada."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Achado:
    """Resultado de uma regra de auditoria."""
    regra: str
    titulo: str
    descricao: str
    valor_estimado: float
    tributo: str
    base_legal: str
    confianca: str           # alta, media, baixa
    registros_origem: list[str] = field(default_factory=list)
    recomendacao: str = ""
    risco: str = ""


class RegraAuditoria(ABC):
    """Classe abstrata que toda regra deve implementar."""

    @property
    @abstractmethod
    def codigo(self) -> str: ...

    @property
    @abstractmethod
    def nome(self) -> str: ...

    @property
    @abstractmethod
    def base_legal(self) -> str: ...

    @abstractmethod
    def executar(self, dados_ecd, dados_ecf, mapa_contas: dict) -> list[Achado]: ...
