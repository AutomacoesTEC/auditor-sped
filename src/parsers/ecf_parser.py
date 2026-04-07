"""Parser especializado para arquivos ECF (Escrituração Contábil Fiscal).

Calibrado com arquivo real: BRASNORTE DISTRIBUIDORA DE BEBIDAS LTDA (2024).
Estrutura verificada:
  N620/N630/N670: formato tabular |REG|LINHA|DESCRIÇÃO|VALOR|
  M300/M350: |REG|CODIGO|DESCRICAO|IND_AD_EX|TP_LANC|VALOR|...
  Y570: |Y570|CNPJ|NOME|IND_PART|COD_REC|VL_REC|VL_IR_RET|VL_IR_UTIL|
  Y580: |Y580|TIPO|PER_APUR|DCOMP_NUM|VL_CRED|
  Y600: |Y600|DT_ALT||COD_PAIS|TIP_PES|CPF_CNPJ|NOME|QUALIF|PERC_CAP|...
"""

import logging
from dataclasses import dataclass, field
from src.parsers.sped_parser import parse_arquivo, RegistroSPED, valor_monetario
from config import (
    REGISTROS_ECF, ECF_TABULAR_CAMPOS,
    Y570_CAMPOS, Y580_CAMPOS, M300_CAMPOS,
    N630_LINHAS, N670_LINHAS, N620_LINHAS,
)

logger = logging.getLogger(__name__)


@dataclass
class LinhaTabular:
    """Uma linha de registro tabular ECF (N620, N630, N670, etc.)."""
    codigo_linha: str
    descricao: str
    valor: float
    linha_arquivo: int


@dataclass
class LancamentoLALUR:
    """Registro M300/M350: lançamento na Parte A do LALUR/LACS."""
    codigo: str
    descricao: str
    ind_ad_ex: str     # A=Adição, E=Exclusão, C=Compensação
    tp_lancamento: str
    valor: float
    linha: int


@dataclass
class RetencaoIRRF:
    """Registro Y570: rendimento com IRRF retido."""
    cnpj: str
    nome: str
    cod_rec: str
    vl_receita: float
    vl_ir_retido: float
    vl_ir_utilizado: float
    linha: int


@dataclass
class PERDcomp:
    """Registro Y580: PER/DCOMP transmitido."""
    tipo: str
    per_apur: str
    numero: str
    valor: float
    linha: int


@dataclass
class Socio:
    """Registro Y600: participação societária."""
    cpf_cnpj: str
    nome: str
    qualificacao: str
    perc_capital: str
    linha: int


@dataclass
class DadosECF:
    """Dados estruturados extraídos de um arquivo ECF."""
    # Identificação
    cnpj: str = ""
    razao_social: str = ""
    dt_ini: str = ""
    dt_fin: str = ""
    forma_tribut: str = ""   # 1=Real, 2=Presumido, etc.

    # Registros tabulares (N620, N630, N670, etc.)
    n620: list[LinhaTabular] = field(default_factory=list)
    n630: list[LinhaTabular] = field(default_factory=list)
    n670: list[LinhaTabular] = field(default_factory=list)
    n500: list[LinhaTabular] = field(default_factory=list)

    # LALUR/LACS
    m300_irpj: list[LancamentoLALUR] = field(default_factory=list)
    m350_csll: list[LancamentoLALUR] = field(default_factory=list)

    # Retenções e complementares
    y570_irrf: list[RetencaoIRRF] = field(default_factory=list)
    y580_perdcomp: list[PERDcomp] = field(default_factory=list)
    y600_socios: list[Socio] = field(default_factory=list)

    # Brutos
    registros_brutos: dict[str, list[RegistroSPED]] = field(default_factory=dict)

    # Helpers
    def n630_valor(self, codigo_linha: str) -> float:
        """Retorna valor de uma linha específica do N630."""
        for lin in self.n630:
            if lin.codigo_linha == codigo_linha:
                return lin.valor
        return 0.0

    def n670_valor(self, codigo_linha: str) -> float:
        """Retorna valor de uma linha específica do N670."""
        for lin in self.n670:
            if lin.codigo_linha == codigo_linha:
                return lin.valor
        return 0.0

    def n620_valores_por_linha(self, codigo_linha: str) -> list[float]:
        """Retorna todos os valores de uma linha N620 (um por mês)."""
        return [lin.valor for lin in self.n620 if lin.codigo_linha == codigo_linha]


def _preencher_identificacao_ecf(r0: "RegistroSPED", dados: "DadosECF") -> None:
    """
    Detecta automaticamente as posicoes dos campos no registro 0000 da ECF.

    O leiaute ECF 0000 varia conforme a versao:
    - v7:  |0000|COD_VER|TIPO|SIT|CNPJ|DT_INI|DT_FIN|NOME|...|
    - v8+: |0000|COD_VER|TIPO|SIT|NUM_REC_ANT|CNPJ|DT_INI|DT_FIN|NOME|...|

    Estrategia: identifica o CNPJ pelo formato numerico de 14 digitos (com ou sem mascara),
    depois deriva as demais posicoes em relacao a ele.
    """
    import re

    _re_cnpj = re.compile(r"^\d{2}[.\-]?\d{3}[.\-]?\d{3}[/.\-]?\d{4}[.\-]?\d{2}$")
    _re_data = re.compile(r"^\d{8}$")

    # Percorre campos a partir do indice 1 buscando CNPJ (formato numerico ou com mascara)
    cnpj_idx = None
    for i in range(1, min(len(r0.campos), 12)):
        valor = r0.campo(i).strip()
        limpo = re.sub(r"[.\-/]", "", valor)
        if len(limpo) == 14 and limpo.isdigit():
            cnpj_idx = i
            break

    if cnpj_idx is not None:
        dados.cnpj = r0.campo(cnpj_idx)
        # DT_INI e DT_FIN devem ser os proximos campos no formato DDMMAAAA (8 digitos)
        if _re_data.match(r0.campo(cnpj_idx + 1)):
            dados.dt_ini = r0.campo(cnpj_idx + 1)
            dados.dt_fin = r0.campo(cnpj_idx + 2)
            dados.razao_social = r0.campo(cnpj_idx + 3)
        else:
            # Fallback: DT_INI pode ter sido omitido; tenta posicoes seguintes
            for offset in range(1, 5):
                cand = r0.campo(cnpj_idx + offset)
                if _re_data.match(cand):
                    dados.dt_ini = cand
                    dados.dt_fin = r0.campo(cnpj_idx + offset + 1)
                    dados.razao_social = r0.campo(cnpj_idx + offset + 2)
                    break
    else:
        # Ultimo recurso: leitura pelas posicoes fixas do leiaute v7
        dados.cnpj = r0.campo(4)
        dados.dt_ini = r0.campo(5)
        dados.dt_fin = r0.campo(6)
        dados.razao_social = r0.campo(7)
        logger.warning(
            "ECF 0000: nao foi possivel detectar CNPJ automaticamente. "
            "Usando posicoes fixas v7. Razao: '%s'", dados.razao_social
        )


def parse_ecf(caminho: str) -> DadosECF:
    """Parseia arquivo ECF e retorna dados estruturados."""
    registros = parse_arquivo(caminho, REGISTROS_ECF)
    dados = DadosECF(registros_brutos=registros)

    # Identificação
    # ECF 0000 leiaute: |0000|COD_VER_LC|TIPO_ESCRIT|IND_SIT_ESP|CNPJ|DT_INI|DT_FIN|NOME|...|
    # Leiaute v8+: pode haver campo NUM_REC_ANTERIOR em posição 4, deslocando demais campos.
    # Detecção automática pelo formato do CNPJ (XX.XXX.XXX/XXXX-XX ou 14 dígitos).
    if "0000" in registros:
        r0 = registros["0000"][0]
        _preencher_identificacao_ecf(r0, dados)
    if "0010" in registros:
        dados.forma_tribut = registros["0010"][0].campo(2)

    # Registros tabulares
    dados.n500 = _extrair_tabular(registros.get("N500", []))
    dados.n620 = _extrair_tabular(registros.get("N620", []))
    dados.n630 = _extrair_tabular(registros.get("N630", []))
    dados.n670 = _extrair_tabular(registros.get("N670", []))

    # LALUR
    dados.m300_irpj = _extrair_lalur(registros.get("M300", []))
    dados.m350_csll = _extrair_lalur(registros.get("M350", []))

    # Complementares
    dados.y570_irrf = _extrair_y570(registros.get("Y570", []))
    dados.y580_perdcomp = _extrair_y580(registros.get("Y580", []))
    dados.y600_socios = _extrair_y600(registros.get("Y600", []))

    # Log resumo
    irrf_total = sum(r.vl_ir_retido for r in dados.y570_irrf)
    irrf_util = sum(r.vl_ir_utilizado for r in dados.y570_irrf)
    logger.info(
        "ECF [%s] %s a %s: N630=%d linhas, N670=%d, M300=%d, M350=%d, "
        "Y570=%d (IRRF ret=R$%.2f util=R$%.2f), Y580=%d PER/DCOMP, Y600=%d sócios",
        dados.cnpj, dados.dt_ini, dados.dt_fin,
        len(dados.n630), len(dados.n670),
        len(dados.m300_irpj), len(dados.m350_csll),
        len(dados.y570_irrf), irrf_total, irrf_util,
        len(dados.y580_perdcomp), len(dados.y600_socios),
    )

    return dados


def _extrair_tabular(registros: list[RegistroSPED]) -> list[LinhaTabular]:
    """Extrai registros tabulares (N620, N630, N670, etc.)."""
    resultado = []
    for reg in registros:
        try:
            resultado.append(LinhaTabular(
                codigo_linha=reg.campo(ECF_TABULAR_CAMPOS["linha"]),
                descricao=reg.campo(ECF_TABULAR_CAMPOS["descricao"]),
                valor=reg.campo_monetario(ECF_TABULAR_CAMPOS["valor"]),
                linha_arquivo=reg.linha,
            ))
        except Exception as e:
            logger.warning("Erro tabular linha %d: %s", reg.linha, e)
    return resultado


def _extrair_lalur(registros: list[RegistroSPED]) -> list[LancamentoLALUR]:
    """Extrai M300/M350: LALUR Parte A."""
    resultado = []
    for reg in registros:
        try:
            resultado.append(LancamentoLALUR(
                codigo=reg.campo(M300_CAMPOS["codigo"]),
                descricao=reg.campo(M300_CAMPOS["descricao"]),
                ind_ad_ex=reg.campo(M300_CAMPOS["ind_ad_ex"]),
                tp_lancamento=reg.campo(M300_CAMPOS["tp_lancamento"]),
                valor=reg.campo_monetario(M300_CAMPOS["vl_lancamento"]),
                linha=reg.linha,
            ))
        except Exception as e:
            logger.warning("Erro M300 linha %d: %s", reg.linha, e)
    return resultado


def _extrair_y570(registros: list[RegistroSPED]) -> list[RetencaoIRRF]:
    """Extrai Y570: rendimentos com IRRF retido."""
    resultado = []
    for reg in registros:
        try:
            resultado.append(RetencaoIRRF(
                cnpj=reg.campo(Y570_CAMPOS["cnpj"]),
                nome=reg.campo(Y570_CAMPOS["nome"]),
                cod_rec=reg.campo(Y570_CAMPOS["cod_rec"]),
                vl_receita=reg.campo_monetario(Y570_CAMPOS["vl_rec"]),
                vl_ir_retido=reg.campo_monetario(Y570_CAMPOS["vl_ir_ret"]),
                vl_ir_utilizado=reg.campo_monetario(Y570_CAMPOS["vl_ir_util"]),
                linha=reg.linha,
            ))
        except Exception as e:
            logger.warning("Erro Y570 linha %d: %s", reg.linha, e)
    return resultado


def _extrair_y580(registros: list[RegistroSPED]) -> list[PERDcomp]:
    """Extrai Y580: PER/DCOMP transmitidos."""
    resultado = []
    for reg in registros:
        try:
            resultado.append(PERDcomp(
                tipo=reg.campo(Y580_CAMPOS["tipo"]),
                per_apur=reg.campo(Y580_CAMPOS["per_apur"]),
                numero=reg.campo(Y580_CAMPOS["dcomp_num"]),
                valor=reg.campo_monetario(Y580_CAMPOS["vl_cred"]),
                linha=reg.linha,
            ))
        except Exception as e:
            logger.warning("Erro Y580 linha %d: %s", reg.linha, e)
    return resultado


def _extrair_y600(registros: list[RegistroSPED]) -> list[Socio]:
    """Extrai Y600: participações societárias."""
    resultado = []
    for reg in registros:
        try:
            resultado.append(Socio(
                cpf_cnpj=reg.campo(5),
                nome=reg.campo(6),
                qualificacao=reg.campo(7),
                perc_capital=reg.campo(8),
                linha=reg.linha,
            ))
        except Exception as e:
            logger.warning("Erro Y600 linha %d: %s", reg.linha, e)
    return resultado
