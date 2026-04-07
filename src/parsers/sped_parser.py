"""Parser genérico de arquivos SPED (.txt separado por |)."""

import logging
from dataclasses import dataclass, field
from config import ENCODING_PRIMARIO, ENCODING_FALLBACK, SEPARADOR

logger = logging.getLogger(__name__)


@dataclass
class RegistroSPED:
    """Um registro SPED com metadados de origem."""
    tipo: str
    campos: list[str]
    linha: int

    def campo(self, indice: int, default: str = "") -> str:
        """Retorna campo pelo índice com segurança."""
        if indice < len(self.campos):
            return self.campos[indice].strip()
        return default

    def campo_monetario(self, indice: int) -> float:
        """Retorna campo monetário convertido para float."""
        return valor_monetario(self.campo(indice))


def parse_arquivo(caminho: str, registros_interesse: list[str] | None = None) -> dict[str, list[RegistroSPED]]:
    """
    Lê arquivo SPED e retorna dicionário indexado pelo código do registro.

    Args:
        caminho: caminho do arquivo .txt SPED
        registros_interesse: se informado, filtra apenas esses tipos de registro

    Returns:
        Dicionário { "I155": [RegistroSPED, ...], "M300": [...], ... }
    """
    resultado: dict[str, list[RegistroSPED]] = {}
    encoding = _detectar_encoding(caminho)
    registros_set = set(registros_interesse) if registros_interesse else None

    with open(caminho, "r", encoding=encoding, errors="replace") as f:
        for num_linha, linha in enumerate(f, start=1):
            linha = linha.strip().rstrip("\r\n")
            if not linha or not linha.startswith(SEPARADOR):
                continue

            # Remove pipes inicial e final
            if linha.startswith(SEPARADOR):
                linha = linha[1:]
            if linha.endswith(SEPARADOR):
                linha = linha[:-1]

            campos = linha.split(SEPARADOR)
            if not campos:
                continue

            tipo = campos[0].strip()

            # Ignorar linhas binárias/corrompidas
            if not tipo.isalnum() and tipo not in ("", " "):
                continue

            if registros_set and tipo not in registros_set:
                continue

            registro = RegistroSPED(tipo=tipo, campos=campos, linha=num_linha)

            if tipo not in resultado:
                resultado[tipo] = []
            resultado[tipo].append(registro)

    total = sum(len(v) for v in resultado.values())
    logger.info("Arquivo %s: %d registros parseados (%d tipos)", caminho, total, len(resultado))

    return resultado


def _detectar_encoding(caminho: str) -> str:
    """Tenta abrir com encoding primário; se falhar, usa fallback."""
    try:
        with open(caminho, "r", encoding=ENCODING_PRIMARIO) as f:
            f.read(4096)
        return ENCODING_PRIMARIO
    except (UnicodeDecodeError, UnicodeError):
        logger.warning("Encoding %s falhou, usando %s", ENCODING_PRIMARIO, ENCODING_FALLBACK)
        return ENCODING_FALLBACK


def valor_monetario(campo: str) -> float:
    """Converte campo monetário SPED (vírgula como decimal) para float."""
    if not campo or not campo.strip():
        return 0.0
    campo = campo.strip()
    try:
        # SPED usa vírgula como separador decimal e ponto como milhar
        return float(campo.replace(".", "").replace(",", "."))
    except ValueError:
        logger.warning("Valor monetário inválido: '%s'", campo)
        return 0.0
