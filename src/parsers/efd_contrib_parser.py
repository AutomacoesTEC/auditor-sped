"""Parser especializado para EFD-Contribuições (PIS/COFINS).

Este parser lê os registros relevantes da EFD-Contribuições para:
1. Identificar créditos de PIS/COFINS não aproveitados
2. Cruzar com a ECF (L300/DRE) e ECD (I155/despesas)
3. Validar a correta apuração no Bloco M

Estrutura principal (conforme Guia Prático EFD-Contribuições v1.35+):
  0000: Abertura (período, regime, CNPJ)
  0110: Regime de apuração (1=Não cumulativo, 2=Cumulativo, 3=Ambos)
  0500: Plano de contas contábil
  0600: Centro de custos

  Bloco A: Serviços (notas fiscais de serviço)
  Bloco C: Mercadorias (NF-e, entradas e saídas)
    C100: Documento fiscal
    C170: Itens do documento (detalhamento)
    C175: Registro analítico (operação)
    C180/C181/C185/C188: Créditos nas operações de aquisição
    C190/C191/C195/C198: Receitas nas operações de venda

  Bloco D: Transporte e comunicação
  Bloco F: Demais documentos e operações
    F100: Créditos presumidos (demais receitas, custos, despesas)
    F120: Bens do ativo (depreciação/amortização com crédito)
    F130: Bens do ativo incorporados ao ativo imobilizado
    F150: Crédito sobre estoques de abertura
    F200: Atividade imobiliária
    F500/F510: Apuração consolidada (regime de caixa)
    F550/F560: Apuração consolidada (regime de competência)
    F600: Retenções na fonte (CSRF)

  Bloco M: Apuração de PIS e COFINS (CHAVE)
    M100: Crédito de PIS apurado
    M105: Detalhamento da base de crédito
    M110: Ajustes do crédito de PIS
    M200: Contribuição PIS devida
    M210: Detalhamento PIS por código de receita
    M500: Crédito de COFINS apurado
    M505: Detalhamento da base de crédito
    M510: Ajustes do crédito de COFINS
    M600: Contribuição COFINS devida
    M610: Detalhamento COFINS por código de receita

  Bloco 1: Complemento
    1100: Controle de créditos fiscais PIS
    1500: Controle de créditos fiscais COFINS
"""

import logging
from dataclasses import dataclass, field
from src.parsers.sped_parser import parse_arquivo, RegistroSPED, valor_monetario
from config import REGISTROS_EFD_CONTRIB

logger = logging.getLogger(__name__)


@dataclass
class CreditoPISCOFINS:
    """Registro M100/M500: crédito apurado."""
    tipo_credito: str       # Código do tipo de crédito (Tabela 4.3.6)
    ind_cred_ori: str       # 0=Operações próprias, 1=Evento de incorporação
    vl_bc_credito: float    # Base de cálculo do crédito
    aliquota: float         # Alíquota aplicada
    vl_credito: float       # Valor do crédito apurado
    descricao: str
    linha: int


@dataclass
class ContribuicaoDevida:
    """Registro M200/M600: contribuição devida."""
    vl_total_contrib: float
    vl_total_creditos: float
    vl_contrib_devida: float
    linha: int


@dataclass
class ControleCredito:
    """Registro 1100/1500: controle de créditos fiscais."""
    tipo_credito: str
    periodo_orig: str
    vl_cred_apurado: float
    vl_cred_utilizado: float
    vl_cred_descontado: float
    vl_cred_disp: float      # Saldo disponível
    linha: int


@dataclass
class RetencaoFonte:
    """Registro F600: retenção na fonte (CSRF)."""
    ind_nat_ret: str         # Natureza da retenção
    dt_ret: str
    vl_bc_ret: float
    vl_ret: float            # Valor retido
    cod_rec: str             # Código de receita
    ind_dec: str             # 0=PIS, 1=COFINS, 2=CSLL
    linha: int


@dataclass
class ItemDocumento:
    """Registro C170: item do documento fiscal (para análise de créditos)."""
    num_item: str
    cod_item: str
    descricao: str
    vl_item: float
    cst_pis: str             # CST PIS (50-56 = com crédito, 70-75 = sem crédito)
    vl_bc_pis: float
    aliq_pis: float
    vl_pis: float
    cst_cofins: str
    vl_bc_cofins: float
    aliq_cofins: float
    vl_cofins: float
    cfop: str
    nat_bc_cred: str         # Natureza da base de crédito (Tabela 4.3.7)
    linha: int


@dataclass
class DadosEFDContrib:
    """Dados estruturados de um arquivo EFD-Contribuições."""
    cnpj: str = ""
    razao_social: str = ""
    dt_ini: str = ""
    dt_fin: str = ""
    regime_apuracao: str = ""   # 1=Não cumulativo, 2=Cumulativo, 3=Ambos

    creditos_pis: list[CreditoPISCOFINS] = field(default_factory=list)
    creditos_cofins: list[CreditoPISCOFINS] = field(default_factory=list)
    contrib_pis: list[ContribuicaoDevida] = field(default_factory=list)
    contrib_cofins: list[ContribuicaoDevida] = field(default_factory=list)
    controle_cred_pis: list[ControleCredito] = field(default_factory=list)
    controle_cred_cofins: list[ControleCredito] = field(default_factory=list)
    retencoes: list[RetencaoFonte] = field(default_factory=list)
    itens_documentos: list[ItemDocumento] = field(default_factory=list)

    registros_brutos: dict[str, list[RegistroSPED]] = field(default_factory=dict)


def parse_efd_contrib(caminho: str) -> DadosEFDContrib:
    """Parseia arquivo EFD-Contribuições e retorna dados estruturados."""
    registros = parse_arquivo(caminho, REGISTROS_EFD_CONTRIB)
    dados = DadosEFDContrib(registros_brutos=registros)

    # Identificação
    if "0000" in registros:
        r0 = registros["0000"][0]
        dados.dt_ini = r0.campo(3)
        dados.dt_fin = r0.campo(4)
        dados.razao_social = r0.campo(6)
        dados.cnpj = r0.campo(7)

    if "0110" in registros:
        dados.regime_apuracao = registros["0110"][0].campo(2)

    # Créditos M100 (PIS)
    dados.creditos_pis = _extrair_creditos(registros.get("M100", []))
    # Créditos M500 (COFINS)
    dados.creditos_cofins = _extrair_creditos(registros.get("M500", []))

    # Contribuição devida M200 (PIS), M600 (COFINS)
    dados.contrib_pis = _extrair_contrib(registros.get("M200", []))
    dados.contrib_cofins = _extrair_contrib(registros.get("M600", []))

    # Controle de créditos 1100 (PIS), 1500 (COFINS)
    dados.controle_cred_pis = _extrair_controle(registros.get("1100", []))
    dados.controle_cred_cofins = _extrair_controle(registros.get("1500", []))

    # Retenções F600
    dados.retencoes = _extrair_retencoes(registros.get("F600", []))

    logger.info(
        "EFD-Contrib [%s] %s a %s: regime=%s, "
        "créditos PIS=%d, créditos COFINS=%d, retenções=%d",
        dados.cnpj, dados.dt_ini, dados.dt_fin,
        dados.regime_apuracao,
        len(dados.creditos_pis), len(dados.creditos_cofins),
        len(dados.retencoes),
    )

    return dados


def _extrair_creditos(registros: list[RegistroSPED]) -> list[CreditoPISCOFINS]:
    """Extrai M100/M500: créditos apurados."""
    resultado = []
    for reg in registros:
        try:
            # M100: |M100|COD_CRED|IND_CRED_ORI|VL_BC_CRED|ALIQ|VL_CRED|...|
            resultado.append(CreditoPISCOFINS(
                tipo_credito=reg.campo(1),
                ind_cred_ori=reg.campo(2),
                vl_bc_credito=reg.campo_monetario(3),
                aliquota=reg.campo_monetario(4),
                vl_credito=reg.campo_monetario(5),
                descricao=reg.campo(6) if len(reg.campos) > 6 else "",
                linha=reg.linha,
            ))
        except Exception as e:
            logger.warning("Erro crédito linha %d: %s", reg.linha, e)
    return resultado


def _extrair_contrib(registros: list[RegistroSPED]) -> list[ContribuicaoDevida]:
    """Extrai M200/M600: contribuição devida."""
    resultado = []
    for reg in registros:
        try:
            resultado.append(ContribuicaoDevida(
                vl_total_contrib=reg.campo_monetario(1),
                vl_total_creditos=reg.campo_monetario(5) if len(reg.campos) > 5 else 0.0,
                vl_contrib_devida=reg.campo_monetario(7) if len(reg.campos) > 7 else 0.0,
                linha=reg.linha,
            ))
        except Exception as e:
            logger.warning("Erro contrib linha %d: %s", reg.linha, e)
    return resultado


def _extrair_controle(registros: list[RegistroSPED]) -> list[ControleCredito]:
    """Extrai 1100/1500: controle de créditos fiscais."""
    resultado = []
    for reg in registros:
        try:
            resultado.append(ControleCredito(
                tipo_credito=reg.campo(2),
                periodo_orig=reg.campo(3),
                vl_cred_apurado=reg.campo_monetario(5),
                vl_cred_utilizado=reg.campo_monetario(6),
                vl_cred_descontado=reg.campo_monetario(7),
                vl_cred_disp=reg.campo_monetario(8),
                linha=reg.linha,
            ))
        except Exception as e:
            logger.warning("Erro controle crédito linha %d: %s", reg.linha, e)
    return resultado


def _extrair_retencoes(registros: list[RegistroSPED]) -> list[RetencaoFonte]:
    """Extrai F600: retenções na fonte."""
    resultado = []
    for reg in registros:
        try:
            resultado.append(RetencaoFonte(
                ind_nat_ret=reg.campo(1),
                dt_ret=reg.campo(2),
                vl_bc_ret=reg.campo_monetario(3),
                vl_ret=reg.campo_monetario(4),
                cod_rec=reg.campo(5),
                ind_dec=reg.campo(6),
                linha=reg.linha,
            ))
        except Exception as e:
            logger.warning("Erro F600 linha %d: %s", reg.linha, e)
    return resultado
