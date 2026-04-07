"""Motor de Lançamentos Gatilho.

Analisa históricos de lançamentos (I250) e nomes de contas (I050) para
identificar padrões que indicam possíveis créditos não aproveitados,
classificações incorretas ou lançamentos que merecem atenção especial.

Funciona em duas camadas:
  1. Gatilhos por CONTA: analisa o nome/natureza da conta contábil
  2. Gatilhos por HISTÓRICO: analisa o texto do histórico do lançamento (I250)

Cada gatilho tem:
  - padrões de palavras-chave (case insensitive)
  - categoria de risco tributário
  - justificativa
  - ação recomendada
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class Gatilho:
    """Definição de um padrão gatilho."""
    codigo: str
    categoria: str          # IRPJ, CSLL, PIS_COFINS, CLASSIFICACAO, PROCEDIMENTO
    descricao: str
    palavras: list[str]     # Qualquer uma dispara o gatilho (OR)
    palavras_excluir: list[str] = field(default_factory=list)  # Exclui falsos positivos
    justificativa: str = ""
    acao: str = ""
    severidade: str = "media"  # alta, media, baixa


@dataclass
class AchadoGatilho:
    """Resultado de um gatilho disparado."""
    gatilho: str             # Código do gatilho
    categoria: str
    descricao: str
    justificativa: str
    acao: str
    severidade: str
    # Contexto do disparo
    cod_conta: str
    nome_conta: str
    historico: str
    valor: float
    data: str
    num_lancamento: str
    linha_arquivo: int
    tipo: str                # "conta" ou "historico"


# ============================================================
# DEFINIÇÃO DOS GATILHOS
# ============================================================

GATILHOS_CONTA = [
    # --- TRIBUTOS A COMPENSAR/RECUPERAR (créditos potenciais) ---
    Gatilho(
        codigo="GC01",
        categoria="CREDITO_TRIBUTARIO",
        descricao="Tributos a compensar com saldo remanescente",
        palavras=["a compensar", "a recuperar", "a restituir", "crédito tributário"],
        justificativa="Contas de tributos a compensar com saldo positivo podem indicar créditos não utilizados via PER/DCOMP.",
        acao="Verificar saldo final, origem do crédito e se houve pedido de compensação/restituição.",
        severidade="alta",
    ),
    Gatilho(
        codigo="GC02",
        categoria="IRPJ",
        descricao="IRRF a compensar/recuperar",
        palavras=["irrf", "ir retido", "imposto de renda retido", "ir a compensar", "ir a recuperar"],
        palavras_excluir=["a pagar", "a recolher"],
        justificativa="IRRF retido na fonte pode não ter sido deduzido na apuração do IRPJ (N630 linha 20).",
        acao="Cruzar saldo com N630/N620 e Y570. Se retido e não deduzido, gerar PER/DCOMP.",
        severidade="alta",
    ),
    Gatilho(
        codigo="GC03",
        categoria="PIS_COFINS",
        descricao="PIS/COFINS a compensar",
        palavras=["pis a compensar", "cofins a compensar", "pis a recuperar", "cofins a recuperar"],
        justificativa="Saldo de PIS/COFINS a compensar pode indicar créditos excedentes não utilizados.",
        acao="Verificar registros 1100/1500 da EFD-Contribuições e cruzar com DCTF/PER/DCOMP.",
        severidade="alta",
    ),
    Gatilho(
        codigo="GC04",
        categoria="CSLL",
        descricao="CSLL retida/a compensar",
        palavras=["csll a compensar", "csll retida", "csrf a compensar", "contribuição social a compensar"],
        justificativa="CSLL retida na fonte (CSRF) pode não ter sido deduzida em N670.",
        acao="Cruzar com N670 linhas 15-18 e F600 da EFD-Contribuições.",
        severidade="alta",
    ),

    # --- PAT E ALIMENTAÇÃO ---
    Gatilho(
        codigo="GC05",
        categoria="IRPJ",
        descricao="Despesas com alimentação (potencial PAT)",
        palavras=["alimentação", "alimentacao", "refeição", "refeicao", "vale refeição",
                  "cesta básica", "cesta basica", "vale alimentação", "vale alimentacao",
                  "ticket refeição", "ticket alimentação"],
        justificativa="Empresa com despesas de alimentação pode ter direito ao incentivo PAT (4% do IRPJ).",
        acao="Verificar se empresa possui inscrição no PAT e se dedução foi aplicada em N630 linha 8 / N620 linha 9.",
        severidade="media",
    ),

    # --- DEPRECIAÇÃO ---
    Gatilho(
        codigo="GC06",
        categoria="IRPJ",
        descricao="Depreciação (verificar taxas e aceleração)",
        palavras=["depreciação", "depreciacao", "amortização", "amortizacao"],
        palavras_excluir=["depreciação acumulada"],
        justificativa="Taxas de depreciação podem estar abaixo do permitido, ou depreciação acelerada pode não ter sido aplicada no LALUR.",
        acao="Comparar taxa efetiva com tabelas da RFB. Verificar exclusão no M300 para depreciação acelerada.",
        severidade="media",
    ),

    # --- PROVISÕES E PERDAS ---
    Gatilho(
        codigo="GC07",
        categoria="IRPJ",
        descricao="Provisão para devedores duvidosos / PDD",
        palavras=["provisão para crédito", "pdd", "devedores duvidosos", "perdas estimadas",
                  "perdas com recebimento", "perda em crédito"],
        justificativa="PDD é adicionada ao LALUR; quando a perda se torna dedutível (art. 9, Lei 9.430/96), deve ser excluída.",
        acao="Verificar adições em M300 e se há exclusões correspondentes quando requisitos do art. 9 são atingidos.",
        severidade="media",
    ),

    # --- SUBVENÇÕES ---
    Gatilho(
        codigo="GC08",
        categoria="IRPJ",
        descricao="Subvenções governamentais",
        palavras=["subvenção", "subvencao", "incentivo fiscal", "benefício fiscal",
                  "isenção icms", "redução icms", "crédito presumido icms"],
        justificativa="Subvenções para investimento podem ser excluídas do LALUR (art. 30, Lei 12.973/2014) ou gerar crédito fiscal (Lei 14.789/2023).",
        acao="Verificar natureza da subvenção e tratamento no M300. Se não excluída, pode estar sendo tributada indevidamente.",
        severidade="alta",
    ),

    # --- JCP ---
    Gatilho(
        codigo="GC09",
        categoria="IRPJ",
        descricao="Juros sobre capital próprio",
        palavras=["juros sobre capital próprio", "juros sobre capital proprio", "jcp", "juros s/ capital"],
        justificativa="JCP declarado mas não pago pode indicar dedutibilidade não aproveitada ou cálculo a menor.",
        acao="Verificar se JCP foi deduzido no LALUR, se há IRRF recolhido (15%), e se o valor está dentro do limite (TJLP).",
        severidade="media",
    ),

    # --- MULTAS E PENALIDADES ---
    Gatilho(
        codigo="GC10",
        categoria="CLASSIFICACAO",
        descricao="Multas fiscais (dedutibilidade)",
        palavras=["multa fiscal", "multa compensatória", "multa punitiva", "multa contratual",
                  "multa de mora", "multa por infração"],
        justificativa="Multas compensatórias são dedutíveis; punitivas são indedutíveis. Classificação incorreta afeta IRPJ/CSLL.",
        acao="Verificar se multas compensatórias foram adicionadas indevidamente no LALUR ou se punitivas não foram adicionadas.",
        severidade="media",
    ),

    # --- BRINDES ---
    Gatilho(
        codigo="GC11",
        categoria="CLASSIFICACAO",
        descricao="Brindes e bonificações",
        palavras=["brindes", "bonificação", "bonificacao", "doação", "doacao"],
        justificativa="Brindes são indedutíveis para IRPJ (art. 13, Lei 9.249/95). Bonificações em mercadorias podem gerar crédito de PIS/COFINS.",
        acao="Verificar adição no LALUR para brindes e tratamento PIS/COFINS para bonificações.",
        severidade="baixa",
    ),

    # --- INSUMOS PIS/COFINS ---
    Gatilho(
        codigo="GC12",
        categoria="PIS_COFINS",
        descricao="Despesas potencialmente creditáveis (PIS/COFINS)",
        palavras=["aluguel", "energia elétrica", "energia eletrica", "frete", "carreto",
                  "combustível", "combustivel", "telecomunicação", "telecomunicacao",
                  "manutenção", "manutencao", "reparo", "seguro", "embalagem",
                  "material de limpeza", "uniforme", "epi"],
        justificativa="No regime não cumulativo, diversas despesas operacionais geram crédito de PIS (1,65%) e COFINS (7,6%), conforme conceito amplo de insumo (REsp 1.221.170/PR).",
        acao="Cruzar com EFD-Contribuições: verificar se CST utilizado permite crédito (50-56) e se base de cálculo está correta.",
        severidade="alta",
    ),
]


GATILHOS_HISTORICO = [
    # --- PADRÕES DE RISCO EM HISTÓRICOS ---
    Gatilho(
        codigo="GH01",
        categoria="PROCEDIMENTO",
        descricao="Lançamento de ajuste/estorno (verificar regularidade)",
        palavras=["ajuste referente", "estorno", "reclassificação", "reclassificacao",
                  "transferência entre contas", "correção de lançamento", "correcao de lancamento"],
        justificativa="Ajustes e estornos podem indicar correções que afetam a base de cálculo de tributos.",
        acao="Verificar se o ajuste afeta contas de resultado e se houve reflexo no LALUR.",
        severidade="baixa",
    ),
    Gatilho(
        codigo="GH02",
        categoria="IRPJ",
        descricao="Baixa de PDD / Perda em crédito (dedutibilidade)",
        palavras=["baixa/prejuízo pdd", "baixa pdd", "perda com recebimento",
                  "perda definitiva", "crédito irrecuperável", "credito irrecuperavel"],
        justificativa="Baixa de PDD contra perda efetiva pode gerar exclusão no LALUR se atender art. 9, Lei 9.430/96.",
        acao="Verificar se há exclusão correspondente no M300 e se os requisitos legais estão atendidos (valor > R$15k com garantia, ou concordata/falência, ou sem garantia > 1 ano).",
        severidade="alta",
    ),
    Gatilho(
        codigo="GH03",
        categoria="CLASSIFICACAO",
        descricao="Baixa de ativo / alienação (ganho ou perda de capital)",
        palavras=["baixa de ativo", "alienação", "alienacao", "venda de imobilizado",
                  "venda de bem", "baixa por obsolescência"],
        justificativa="Alienação de ativo pode gerar ganho ou perda de capital com tratamento fiscal específico.",
        acao="Verificar se ganho/perda foi corretamente incluído na base de IRPJ/CSLL.",
        severidade="media",
    ),
    Gatilho(
        codigo="GH04",
        categoria="IRPJ",
        descricao="Lançamento com referência a exercício anterior",
        palavras=["exercício anterior", "exercicio anterior", "período anterior", "periodo anterior",
                  "competência anterior", "competencia anterior"],
        justificativa="Despesas de exercícios anteriores podem ser indedutíveis se não atenderem ao regime de competência.",
        acao="Verificar se houve adição no LALUR e se a despesa é passível de retificação para dedutibilidade.",
        severidade="media",
    ),
    Gatilho(
        codigo="GH05",
        categoria="PIS_COFINS",
        descricao="Devolução de vendas/compras",
        palavras=["devolução", "devoluçao", "devolucao", "nf devolução", "nf devoluçao"],
        justificativa="Devoluções de vendas reduzem a receita bruta (e o débito de PIS/COFINS). Devoluções de compras anulam créditos.",
        acao="Verificar se devoluções estão corretamente refletidas na EFD-Contribuições.",
        severidade="baixa",
    ),
    Gatilho(
        codigo="GH06",
        categoria="CREDITO_TRIBUTARIO",
        descricao="Retenção na fonte mencionada no histórico",
        palavras=["retenção", "retencao", "retido na fonte", "irrf", "csrf",
                  "ret. pis", "ret. cofins", "ret. csll"],
        justificativa="Menções a retenção no histórico podem indicar valores retidos não compensados.",
        acao="Cruzar com contas de tributos a compensar e com deduções na ECF.",
        severidade="alta",
    ),
    Gatilho(
        codigo="GH07",
        categoria="CLASSIFICACAO",
        descricao="Despesa pessoal ou de sócio (indedutibilidade)",
        palavras=["despesa pessoal", "uso pessoal", "sócio", "socio", "pró-labore",
                  "retirada de sócio", "distribuição de lucro", "distribuicao de lucro"],
        palavras_excluir=["provisão para", "contribuição social"],
        justificativa="Despesas pessoais de sócios são indedutíveis. Distribuição de lucros tem tratamento fiscal específico.",
        acao="Verificar se há adição no LALUR e se a classificação contábil está correta.",
        severidade="media",
    ),
    Gatilho(
        codigo="GH08",
        categoria="CREDITO_TRIBUTARIO",
        descricao="Crédito de fornecedor / bonificação recebida",
        palavras=["crédito cia", "credito cia", "bonificação recebida", "bonificacao recebida",
                  "metas atingidas", "desconto obtido", "abatimento"],
        justificativa="Créditos de fornecedores (rebates, bonificações) podem ter tratamento fiscal diferenciado para PIS/COFINS.",
        acao="Verificar classificação como receita ou redução de custo e reflexo na apuração de PIS/COFINS.",
        severidade="media",
    ),
    Gatilho(
        codigo="GH09",
        categoria="IRPJ",
        descricao="Contabilização incorreta declarada no histórico",
        palavras=["contabilizada incorretamente", "lançamento incorreto", "classificação incorreta",
                  "conta errada", "estorno por erro"],
        justificativa="Históricos que declaram erro de contabilização podem indicar que a correção não foi refletida na ECF.",
        acao="Verificar se o ajuste afeta contas de resultado e se a ECF reflete a posição corrigida.",
        severidade="alta",
    ),
    Gatilho(
        codigo="GH10",
        categoria="PROCEDIMENTO",
        descricao="Pagamento sem nota fiscal / fornecedor sem NF",
        palavras=["sem nota fiscal", "sem nf", "não emitiu nf", "nao emitiu nf",
                  "fornecedor não emitiu", "sem documento fiscal"],
        justificativa="Pagamentos sem NF podem ser indedutíveis e não geram crédito de PIS/COFINS.",
        acao="Verificar se a despesa foi adicionada ao LALUR e se não gerou crédito indevido de PIS/COFINS.",
        severidade="alta",
    ),
]


def executar_gatilhos_conta(
    plano_contas: dict,
    saldos: dict,
) -> list[AchadoGatilho]:
    """
    Analisa nomes de contas contábeis contra padrões gatilho.

    Retorna apenas contas que tiveram movimentação (débitos ou créditos > 0)
    ou saldo final > 0 para contas de ativo (tributos a compensar).
    """
    achados = []

    for codigo, conta in plano_contas.items():
        if conta.ind_cta != "A":  # Apenas analíticas
            continue

        nome_lower = conta.nome.lower()

        for gatilho in GATILHOS_CONTA:
            # Verificar exclusões primeiro
            if any(exc.lower() in nome_lower for exc in gatilho.palavras_excluir):
                continue

            # Verificar se alguma palavra-chave match
            if not any(p.lower() in nome_lower for p in gatilho.palavras):
                continue

            # Verificar se a conta tem movimentação relevante
            saldos_conta = saldos.get(codigo, [])
            if not saldos_conta:
                continue

            # Pegar o último saldo (período mais recente)
            ultimo_saldo = saldos_conta[-1]
            tem_movimento = (ultimo_saldo.debitos > 0 or ultimo_saldo.creditos > 0)
            tem_saldo = ultimo_saldo.saldo_final > 0

            if not tem_movimento and not tem_saldo:
                continue

            achados.append(AchadoGatilho(
                gatilho=gatilho.codigo,
                categoria=gatilho.categoria,
                descricao=gatilho.descricao,
                justificativa=gatilho.justificativa,
                acao=gatilho.acao,
                severidade=gatilho.severidade,
                cod_conta=codigo,
                nome_conta=conta.nome,
                historico="",
                valor=ultimo_saldo.saldo_final,
                data="",
                num_lancamento="",
                linha_arquivo=conta.linha,
                tipo="conta",
            ))

    logger.info("Gatilhos de conta: %d achados", len(achados))
    return achados


def executar_gatilhos_historico(
    partidas: list,
    plano_contas: dict,
    limite_valor: float = 0.0,
    amostra_max: int = 0,
) -> list[AchadoGatilho]:
    """
    Analisa históricos de lançamentos (I250) contra padrões gatilho.

    Args:
        partidas: lista de Partida (do ecd_parser)
        plano_contas: dicionário código -> ContaPlano
        limite_valor: se > 0, filtra apenas lançamentos acima desse valor
        amostra_max: se > 0, limita o número de achados por gatilho
    """
    achados = []
    contadores: dict[str, int] = {}

    for partida in partidas:
        if not partida.historico:
            continue

        if limite_valor > 0 and partida.valor < limite_valor:
            continue

        hist_lower = partida.historico.lower()
        nome_conta = plano_contas.get(partida.cod_cta, None)
        nome_display = nome_conta.nome if nome_conta else partida.cod_cta

        for gatilho in GATILHOS_HISTORICO:
            # Limite de amostra por gatilho
            if amostra_max > 0:
                count = contadores.get(gatilho.codigo, 0)
                if count >= amostra_max:
                    continue

            # Verificar exclusões
            if any(exc.lower() in hist_lower for exc in gatilho.palavras_excluir):
                continue

            # Verificar match
            if not any(p.lower() in hist_lower for p in gatilho.palavras):
                continue

            achados.append(AchadoGatilho(
                gatilho=gatilho.codigo,
                categoria=gatilho.categoria,
                descricao=gatilho.descricao,
                justificativa=gatilho.justificativa,
                acao=gatilho.acao,
                severidade=gatilho.severidade,
                cod_conta=partida.cod_cta,
                nome_conta=nome_display,
                historico=partida.historico[:200],  # Truncar para relatório
                valor=partida.valor,
                data=partida.dt_lcto,
                num_lancamento=partida.num_lcto,
                linha_arquivo=partida.linha,
                tipo="historico",
            ))

            contadores[gatilho.codigo] = contadores.get(gatilho.codigo, 0) + 1

    logger.info("Gatilhos de histórico: %d achados", len(achados))
    return achados


def resumo_gatilhos(achados: list[AchadoGatilho]) -> dict:
    """Gera resumo estatístico dos gatilhos disparados."""
    resumo = {
        "total": len(achados),
        "por_categoria": {},
        "por_severidade": {"alta": 0, "media": 0, "baixa": 0},
        "por_gatilho": {},
        "valor_total": 0.0,
    }

    for a in achados:
        resumo["por_categoria"][a.categoria] = resumo["por_categoria"].get(a.categoria, 0) + 1
        resumo["por_severidade"][a.severidade] = resumo["por_severidade"].get(a.severidade, 0) + 1
        resumo["por_gatilho"][a.gatilho] = resumo["por_gatilho"].get(a.gatilho, 0) + 1
        resumo["valor_total"] += a.valor

    return resumo
