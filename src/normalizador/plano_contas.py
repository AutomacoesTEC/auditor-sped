"""Normalizador do plano de contas via mapeamento referencial RFB (I051).

O registro I051 da ECD mapeia cada conta analítica da empresa para o plano
de contas referencial da RFB (ex: 1.01.05.01.01 = IRRF a compensar).
Este módulo usa esse mapeamento para identificar contas por categoria fiscal
de forma mais robusta do que apenas busca por nome.

Referência: Plano de Contas Referencial — IN RFB 1.420/2013 e atualizações.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ============================================================
# PREFIXOS DO PLANO REFERENCIAL RFB (seleção para auditoria)
# ============================================================

PREFIXOS_IRRF_COMPENSAR = (
    "1.01.05.01",  # IRRF a compensar (imposto de renda retido na fonte)
    "1.01.05.02",  # IRRF sobre aplicações financeiras a compensar
)

PREFIXOS_PIS_COMPENSAR = (
    "1.01.05.03",  # PIS/Pasep a recuperar
    "1.01.05.04",  # PIS/Pasep a compensar
)

PREFIXOS_COFINS_COMPENSAR = (
    "1.01.05.05",  # COFINS a recuperar
    "1.01.05.06",  # COFINS a compensar
)

PREFIXOS_CSRF_COMPENSAR = (
    "1.01.05.07",  # CSRF (CSLL) retida a compensar
    "1.01.05.08",  # CSRF (PIS+COFINS) retida a compensar
)

PREFIXOS_TRIBUTOS_COMPENSAR = (
    PREFIXOS_IRRF_COMPENSAR
    + PREFIXOS_PIS_COMPENSAR
    + PREFIXOS_COFINS_COMPENSAR
    + PREFIXOS_CSRF_COMPENSAR
    + ("1.01.05",)  # categoria geral de tributos a recuperar
)

PREFIXOS_ALIMENTACAO = (
    "4.02.03.05",  # Alimentação (PAT)
    "4.02.03.06",  # Refeição / vale-alimentação
    "4.02.01.05",  # Benefícios — alimentação
)

PREFIXOS_DEPRECIACAO = (
    "4.02.05.01",  # Depreciação de imobilizados
    "4.02.05.02",  # Amortização
    "4.02.05",     # Categoria geral depreciação/amortização
)

PREFIXOS_PDD = (
    "1.01.03.03",  # Provisão para créditos de liquidação duvidosa (PDD)
    "1.01.03.04",  # Perdas com créditos
    "4.02.08.01",  # Despesa com PDD
)

PREFIXOS_SUBVENCAO = (
    "4.05.02",     # Subvenções governamentais
    "7.08.01",     # Outras receitas — subvenção para investimento
)

PREFIXOS_COMBUSTIVEL = (
    "4.02.02.04",  # Combustíveis e lubrificantes
    "4.02.04.03",  # Fretes e carretos
)


# ============================================================
# FUNÇÕES PRINCIPAIS
# ============================================================

@dataclass
class ContaNormalizada:
    """Conta contábil com código referencial RFB associado."""
    codigo: str
    nome: str
    natureza: str
    ind_cta: str
    nivel: str
    cod_cta_sup: str
    linha: int
    cod_referencial: str = ""   # Código referencial I051 (ex: "1.01.05.01.01")


def normalizar_plano(plano_contas: dict, mapeamento_referencial: dict) -> dict[str, ContaNormalizada]:
    """
    Enriquece o plano de contas com códigos referenciais RFB.

    Args:
        plano_contas: dict código → ContaPlano (saída do ecd_parser)
        mapeamento_referencial: dict código_conta → cod_referencial (saída do ecd_parser)

    Returns:
        dict código → ContaNormalizada (ContaPlano + cod_referencial)
    """
    resultado = {}
    mapeadas = 0

    for codigo, conta in plano_contas.items():
        cod_ref = mapeamento_referencial.get(codigo, "")
        resultado[codigo] = ContaNormalizada(
            codigo=codigo,
            nome=conta.nome,
            natureza=conta.natureza,
            ind_cta=conta.ind_cta,
            nivel=conta.nivel,
            cod_cta_sup=conta.cod_cta_sup,
            linha=conta.linha,
            cod_referencial=cod_ref,
        )
        if cod_ref:
            mapeadas += 1

    cobertura = (mapeadas / len(resultado) * 100) if resultado else 0.0
    logger.info(
        "Plano normalizado: %d contas, %d com referencial RFB (%.0f%%)",
        len(resultado), mapeadas, cobertura,
    )
    if cobertura < 30 and resultado:
        logger.warning(
            "Cobertura referencial baixa (%.0f%%). "
            "I051 pode estar incompleto — identificação por nome será usada como fallback.",
            cobertura,
        )

    return resultado


def contas_por_referencial(
    plano_normalizado: dict[str, ContaNormalizada],
    prefixos: tuple[str, ...],
    apenas_analiticas: bool = True,
) -> list[ContaNormalizada]:
    """
    Retorna contas cujo código referencial começa com qualquer um dos prefixos.

    Args:
        plano_normalizado: saída de normalizar_plano()
        prefixos: tuple de prefixos referenciais RFB a buscar
        apenas_analiticas: se True, ignora contas sintéticas (ind_cta='S')
    """
    resultado = []
    for conta in plano_normalizado.values():
        if apenas_analiticas and conta.ind_cta != "A":
            continue
        if conta.cod_referencial and any(
            conta.cod_referencial.startswith(p) for p in prefixos
        ):
            resultado.append(conta)
    return resultado


def contas_por_nome(
    plano_contas: dict,
    palavras: list[str],
    excluir: list[str] | None = None,
    apenas_analiticas: bool = True,
) -> list:
    """
    Busca contas por palavras-chave no nome (case-insensitive).
    Fallback quando não há mapeamento referencial disponível.

    Args:
        plano_contas: dict código → ContaPlano ou ContaNormalizada
        palavras: lista de termos; basta um match (OR)
        excluir: termos que excluem a conta se presentes no nome
        apenas_analiticas: se True, ignora contas sintéticas
    """
    excluir = excluir or []
    resultado = []
    for conta in plano_contas.values():
        if apenas_analiticas and conta.ind_cta != "A":
            continue
        nome_lower = conta.nome.lower()
        if any(e.lower() in nome_lower for e in excluir):
            continue
        if any(p.lower() in nome_lower for p in palavras):
            resultado.append(conta)
    return resultado


def contas_por_nome_ou_ref(
    plano_normalizado: dict[str, ContaNormalizada],
    palavras: list[str],
    prefixos_ref: tuple[str, ...],
    excluir: list[str] | None = None,
    apenas_analiticas: bool = True,
) -> list[ContaNormalizada]:
    """
    Combina busca por nome e por código referencial (union).

    Prioriza o referencial quando disponível e usa o nome como fallback,
    evitando duplicatas no resultado.

    Args:
        plano_normalizado: saída de normalizar_plano()
        palavras: palavras-chave para busca por nome
        prefixos_ref: prefixos referenciais RFB
        excluir: palavras que excluem a conta
        apenas_analiticas: ignora contas sintéticas se True
    """
    excluir = excluir or []
    encontrados: dict[str, ContaNormalizada] = {}

    for conta in plano_normalizado.values():
        if apenas_analiticas and conta.ind_cta != "A":
            continue

        nome_lower = conta.nome.lower()
        if any(e.lower() in nome_lower for e in excluir):
            continue

        match_ref = conta.cod_referencial and any(
            conta.cod_referencial.startswith(p) for p in prefixos_ref
        )
        match_nome = any(p.lower() in nome_lower for p in palavras)

        if match_ref or match_nome:
            encontrados[conta.codigo] = conta

    return list(encontrados.values())


def resumo_cobertura(plano_normalizado: dict[str, ContaNormalizada]) -> dict:
    """Retorna estatísticas de cobertura do mapeamento referencial."""
    total = len(plano_normalizado)
    com_ref = sum(1 for c in plano_normalizado.values() if c.cod_referencial)
    analiticas = sum(1 for c in plano_normalizado.values() if c.ind_cta == "A")
    analiticas_com_ref = sum(
        1 for c in plano_normalizado.values()
        if c.ind_cta == "A" and c.cod_referencial
    )
    return {
        "total_contas": total,
        "com_referencial": com_ref,
        "cobertura_pct": round(com_ref / total * 100, 1) if total else 0.0,
        "analiticas": analiticas,
        "analiticas_com_referencial": analiticas_com_ref,
        "cobertura_analiticas_pct": round(
            analiticas_com_ref / analiticas * 100, 1
        ) if analiticas else 0.0,
    }
