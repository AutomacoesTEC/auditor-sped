"""Parser especializado para arquivos ECD (Escrituração Contábil Digital).

Calibrado com arquivo real: BRASNORTE DISTRIBUIDORA DE BEBIDAS LTDA (2024).
Estrutura verificada:
  I050: |I050|DT_ALT|COD_NAT|IND_CTA|NIVEL|COD_CTA|COD_CTA_SUP|CTA|
  I051: |I051|COD_PLAN_REF|COD_CTA_REF|  (aparece logo após I050 analítica)
  I155: |I155|COD_CTA|COD_CCUS|VL_SLD_INI|IND_DC_INI|VL_DEB|VL_CRED|VL_SLD_FIN|IND_DC_FIN|
  I200: |I200|NUM_LCTO|DT_LCTO|VL_LCTO|IND_LCTO|DT_LCTO_EXT|
  I250: |I250|COD_CTA|COD_CCUS|VL_DC|IND_DC|NUM_ARQ|COD_HIST_PAD|HIST|COD_PART|
  C050/C051/C155: mesma estrutura, bloco C (recuperação ECD anterior)
"""

import logging
from dataclasses import dataclass, field
from src.parsers.sped_parser import parse_arquivo, RegistroSPED, valor_monetario
from config import REGISTROS_ECD, I050_CAMPOS, I051_CAMPOS, I155_CAMPOS, I200_CAMPOS, I250_CAMPOS

logger = logging.getLogger(__name__)


@dataclass
class ContaPlano:
    """Registro I050/C050: conta do plano de contas."""
    codigo: str
    natureza: str      # 01=Ativo, 02=Passivo, 03=PL, 04=Resultado, 05=Compensação
    ind_cta: str       # S=Sintética, A=Analítica
    nivel: str
    cod_cta_sup: str
    nome: str
    linha: int


@dataclass
class SaldoPeriodico:
    """Registro I155/C155: saldo periódico de uma conta."""
    codigo_conta: str
    cod_ccus: str
    saldo_inicial: float
    ind_dc_ini: str
    debitos: float
    creditos: float
    saldo_final: float
    ind_dc_fin: str
    linha: int


@dataclass
class Lancamento:
    """Registro I200: cabeçalho do lançamento."""
    num_lcto: str
    dt_lcto: str
    vl_lcto: float
    ind_lcto: str      # N=Normal, E=Encerramento, X=Extemporâneo
    linha: int


@dataclass
class Partida:
    """Registro I250: partida (débito ou crédito) de um lançamento."""
    cod_cta: str
    cod_ccus: str
    valor: float
    ind_dc: str        # D=Débito, C=Crédito
    historico: str     # Campo HIST: texto livre do histórico
    cod_part: str
    num_lcto: str      # Preenchido durante parsing (do I200 pai)
    dt_lcto: str       # Preenchido durante parsing
    linha: int


@dataclass
class DadosECD:
    """Dados estruturados extraídos de um arquivo ECD."""
    # Identificação
    cnpj: str = ""
    razao_social: str = ""
    dt_ini: str = ""
    dt_fin: str = ""

    # Dados parseados
    plano_contas: dict[str, ContaPlano] = field(default_factory=dict)
    mapeamento_referencial: dict[str, str] = field(default_factory=dict)
    saldos: dict[str, list[SaldoPeriodico]] = field(default_factory=dict)
    lancamentos: list[Lancamento] = field(default_factory=list)
    partidas: list[Partida] = field(default_factory=list)

    # Registros brutos para regras que precisem de acesso direto
    registros_brutos: dict[str, list[RegistroSPED]] = field(default_factory=dict)


def parse_ecd(caminho: str) -> DadosECD:
    """Parseia arquivo ECD e retorna dados estruturados."""
    registros = parse_arquivo(caminho, REGISTROS_ECD)
    dados = DadosECD(registros_brutos=registros)

    # Identificação do arquivo (registro 0000)
    # Leiaute ECD: |0000|LEIAUTE|TIPO_ESCRIT|IND_SIT_ESP|NUM_REC_ANT|DT_INI|DT_FIN|NOME|CNPJ|...
    if "0000" in registros:
        r0 = registros["0000"][0]
        dados.dt_ini = r0.campo(5)
        dados.dt_fin = r0.campo(6)
        dados.razao_social = r0.campo(7)
        dados.cnpj = r0.campo(8)

    # Plano de contas: I050 + C050 (bloco C é recuperação da ECD anterior)
    for tipo in ("I050", "C050"):
        _extrair_plano_contas(registros.get(tipo, []), dados.plano_contas)

    # Mapeamento referencial: I051 + C051
    # I051 é filho hierárquico do I050 anterior. Precisamos reconstruir a relação.
    for tipo_pai, tipo_filho in [("I050", "I051"), ("C050", "C051")]:
        _extrair_mapeamento_hierarquico(
            registros.get(tipo_pai, []),
            registros.get(tipo_filho, []),
            dados.mapeamento_referencial,
        )

    # Saldos periódicos: I155 + C155
    for tipo in ("I155", "C155"):
        _extrair_saldos(registros.get(tipo, []), dados.saldos)

    # Lançamentos e partidas: I200 + I250
    dados.lancamentos, dados.partidas = _extrair_lancamentos(
        registros.get("I200", []),
        registros.get("I250", []),
    )

    logger.info(
        "ECD [%s] %s a %s: %d contas, %d mapeamentos, %d saldos, %d lançamentos, %d partidas",
        dados.cnpj, dados.dt_ini, dados.dt_fin,
        len(dados.plano_contas), len(dados.mapeamento_referencial),
        sum(len(v) for v in dados.saldos.values()),
        len(dados.lancamentos), len(dados.partidas),
    )

    if not dados.mapeamento_referencial:
        logger.warning("ATENÇÃO: Nenhum mapeamento referencial (I051/C051) encontrado.")

    return dados


def _extrair_plano_contas(registros: list[RegistroSPED], destino: dict[str, ContaPlano]):
    """Extrai I050/C050 para o dicionário de plano de contas."""
    for reg in registros:
        try:
            codigo = reg.campo(I050_CAMPOS["cod_cta"])
            if not codigo:
                continue
            destino[codigo] = ContaPlano(
                codigo=codigo,
                natureza=reg.campo(I050_CAMPOS["cod_nat"]),
                ind_cta=reg.campo(I050_CAMPOS["ind_cta"]),
                nivel=reg.campo(I050_CAMPOS["nivel"]),
                cod_cta_sup=reg.campo(I050_CAMPOS["cod_cta_sup"]),
                nome=reg.campo(I050_CAMPOS["nome"]),
                linha=reg.linha,
            )
        except Exception as e:
            logger.warning("Erro ao parsear plano de contas na linha %d: %s", reg.linha, e)


def _extrair_mapeamento_hierarquico(
    registros_pai: list[RegistroSPED],
    registros_filho: list[RegistroSPED],
    destino: dict[str, str],
):
    """
    Reconstrói o mapeamento I050->I051 pela proximidade de linha.

    No arquivo SPED, I051 aparece imediatamente após o I050 analítico correspondente.
    Lógica: para cada I051, encontrar o I050(A) mais recente anterior.
    """
    # Criar índice de I050 analíticos por linha
    analiticos_por_linha: dict[int, str] = {}
    linhas_analiticas: list[int] = []

    for reg in registros_pai:
        ind_cta = reg.campo(I050_CAMPOS["ind_cta"])
        codigo = reg.campo(I050_CAMPOS["cod_cta"])
        if ind_cta == "A" and codigo:
            analiticos_por_linha[reg.linha] = codigo
            linhas_analiticas.append(reg.linha)

    linhas_analiticas.sort()

    import bisect
    for reg in registros_filho:
        cod_ref = reg.campo(I051_CAMPOS["cod_cta_ref"])
        if not cod_ref:
            continue

        # Busca binária pelo I050(A) mais próximo anterior
        idx = bisect.bisect_left(linhas_analiticas, reg.linha) - 1
        if idx >= 0:
            conta_pai = analiticos_por_linha[linhas_analiticas[idx]]
            destino[conta_pai] = cod_ref
        else:
            logger.warning("I051 na linha %d sem I050(A) pai: ref=%s", reg.linha, cod_ref)


def _extrair_saldos(registros: list[RegistroSPED], destino: dict[str, list[SaldoPeriodico]]):
    """Extrai I155/C155 para o dicionário de saldos."""
    for reg in registros:
        try:
            codigo = reg.campo(I155_CAMPOS["cod_cta"])
            if not codigo:
                continue
            saldo = SaldoPeriodico(
                codigo_conta=codigo,
                cod_ccus=reg.campo(I155_CAMPOS["cod_ccus"]),
                saldo_inicial=reg.campo_monetario(I155_CAMPOS["vl_sld_ini"]),
                ind_dc_ini=reg.campo(I155_CAMPOS["ind_dc_ini"]),
                debitos=reg.campo_monetario(I155_CAMPOS["vl_deb"]),
                creditos=reg.campo_monetario(I155_CAMPOS["vl_cred"]),
                saldo_final=reg.campo_monetario(I155_CAMPOS["vl_sld_fin"]),
                ind_dc_fin=reg.campo(I155_CAMPOS["ind_dc_fin"]),
                linha=reg.linha,
            )
            if codigo not in destino:
                destino[codigo] = []
            destino[codigo].append(saldo)
        except Exception as e:
            logger.warning("Erro ao parsear I155 na linha %d: %s", reg.linha, e)


def _extrair_lancamentos(
    registros_i200: list[RegistroSPED],
    registros_i250: list[RegistroSPED],
) -> tuple[list[Lancamento], list[Partida]]:
    """
    Extrai I200 + I250 preservando a relação pai-filho.

    I250 herda num_lcto e dt_lcto do I200 imediatamente anterior.
    """
    lancamentos = []
    partidas = []

    # Indexar I200 por linha para associar com I250
    i200_por_linha: dict[int, Lancamento] = {}
    linhas_i200: list[int] = []

    for reg in registros_i200:
        try:
            lcto = Lancamento(
                num_lcto=reg.campo(I200_CAMPOS["num_lcto"]),
                dt_lcto=reg.campo(I200_CAMPOS["dt_lcto"]),
                vl_lcto=reg.campo_monetario(I200_CAMPOS["vl_lcto"]),
                ind_lcto=reg.campo(I200_CAMPOS["ind_lcto"]),
                linha=reg.linha,
            )
            lancamentos.append(lcto)
            i200_por_linha[reg.linha] = lcto
            linhas_i200.append(reg.linha)
        except Exception as e:
            logger.warning("Erro ao parsear I200 na linha %d: %s", reg.linha, e)

    linhas_i200.sort()

    import bisect
    for reg in registros_i250:
        try:
            # Encontrar I200 pai via busca binária O(log n)
            lcto_pai = None
            idx = bisect.bisect_left(linhas_i200, reg.linha) - 1
            if idx >= 0:
                lcto_pai = i200_por_linha[linhas_i200[idx]]

            partida = Partida(
                cod_cta=reg.campo(I250_CAMPOS["cod_cta"]),
                cod_ccus=reg.campo(I250_CAMPOS["cod_ccus"]),
                valor=reg.campo_monetario(I250_CAMPOS["vl_dc"]),
                ind_dc=reg.campo(I250_CAMPOS["ind_dc"]),
                historico=reg.campo(I250_CAMPOS["hist"]),
                cod_part=reg.campo(I250_CAMPOS["cod_part"]),
                num_lcto=lcto_pai.num_lcto if lcto_pai else "",
                dt_lcto=lcto_pai.dt_lcto if lcto_pai else "",
                linha=reg.linha,
            )
            partidas.append(partida)
        except Exception as e:
            logger.warning("Erro ao parsear I250 na linha %d: %s", reg.linha, e)

    return lancamentos, partidas
