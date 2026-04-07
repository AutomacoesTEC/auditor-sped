"""R10: Perdas no recebimento de creditos nao deduzidas do IRPJ/CSLL.

O art. 9 da Lei 9.430/96 permite a deducao de perdas em creditos quando
atendidos requisitos especificos (valor, garantia, prazo, processo judicial).
A PDD (Provisao para Devedores Duvidosos) e adicionada no LALUR; quando
a perda e efetiva, deve ser excluida.

Verifica:
  1. Contas de PDD/perdas no ECD com movimentacao
  2. Adicoes de PDD no M300 (IND_AD_EX = A)
  3. Ausencia de exclusoes correspondentes de PDD no M300

Base legal: Art. 9, Lei 9.430/1996; arts. 347-354 RIR/2018.
"""

import logging
from src.regras.base_regra import RegraAuditoria, Achado

logger = logging.getLogger(__name__)

_PALAVRAS_PDD = [
    "pdd", "provisao para devedores duvidosos", "provisão para devedores duvidosos",
    "provisao para creditos", "provisão para créditos",
    "perdas estimadas", "perdas com recebimento",
    "perda em credito", "perda em crédito",
    "creditos de liquidacao duvidosa", "créditos de liquidação duvidosa",
    "clientes duvidosos",
]
_PALAVRAS_PERDAS_REAIS = [
    "perdas com recebimento", "baixa pdd", "baixa/prejuizo pdd",
    "perda definitiva", "credito irrecuperavel", "crédito irrecuperável",
    "cancelamento de credito", "cancelamento de crédito",
    "credito baixado", "crédito baixado",
]
_PALAVRAS_EXCLUIR = ["reversao", "reversão", "recuperacao", "recuperação"]

_PALAVRAS_M300_PDD = [
    "pdd", "provisao para devedores", "provisão para devedores",
    "perdas em creditos", "perdas com recebimento",
    "devedores duvidosos",
]


class R10PerdasCreditos(RegraAuditoria):

    @property
    def codigo(self) -> str:
        return "R10"

    @property
    def nome(self) -> str:
        return "Perdas no recebimento de creditos nao deduzidas do IRPJ"

    @property
    def base_legal(self) -> str:
        return "Art. 9, Lei 9.430/1996; arts. 347-354 RIR/2018"

    def executar(self, dados_ecd, dados_ecf, mapa_contas: dict) -> list[Achado]:
        achados = []

        if not dados_ecd or not dados_ecf:
            logger.warning("R10: ECD e ECF necessarios. Pulando.")
            return achados

        # === Busca contas PDD no ECD ===
        total_pdd_movimentacao = 0.0
        total_pdd_saldo = 0.0
        registros_pdd = []

        total_perdas_reais = 0.0
        registros_perdas = []

        for codigo, conta in dados_ecd.plano_contas.items():
            if conta.ind_cta != "A":
                continue
            nome_lower = conta.nome.lower()

            # PDD (provisao)
            if any(p in nome_lower for p in _PALAVRAS_PDD):
                if any(exc in nome_lower for exc in _PALAVRAS_EXCLUIR):
                    continue
                saldos = dados_ecd.saldos.get(codigo, [])
                if saldos:
                    ultimo = saldos[-1]
                    mov = sum(s.debitos + s.creditos for s in saldos)
                    if mov > 0:
                        total_pdd_movimentacao += ultimo.debitos if hasattr(ultimo, "debitos") else 0
                        total_pdd_saldo += ultimo.saldo_final
                        registros_pdd.append(
                            f"ECD {codigo} - {conta.nome}: saldo R$ {ultimo.saldo_final:,.2f}"
                        )

            # Perdas reais (baixas definitivas)
            elif any(p in nome_lower for p in _PALAVRAS_PERDAS_REAIS):
                saldos = dados_ecd.saldos.get(codigo, [])
                if saldos:
                    for s in saldos:
                        total_perdas_reais += s.debitos
                    registros_perdas.append(
                        f"ECD {codigo} - {conta.nome}: R$ {sum(s.debitos for s in saldos):,.2f}"
                    )

        # === Busca adicoes e exclusoes de PDD no M300 ===
        adicoes_pdd = [
            l for l in dados_ecf.m300_irpj
            if l.ind_ad_ex == "A"
            and any(p in l.descricao.lower() for p in _PALAVRAS_M300_PDD)
        ]
        exclusoes_pdd = [
            l for l in dados_ecf.m300_irpj
            if l.ind_ad_ex == "E"
            and any(p in l.descricao.lower() for p in _PALAVRAS_M300_PDD)
        ]

        total_adicoes_pdd = sum(l.valor for l in adicoes_pdd)
        total_exclusoes_pdd = sum(l.valor for l in exclusoes_pdd)

        # === Analise de gatilhos de historico para baixas de PDD ===
        baixas_pdd_historico = []
        if dados_ecd:
            _palavras_hist = ["baixa/prejuizo pdd", "baixa pdd", "perda definitiva",
                              "credito irrecuperavel", "crédito irrecuperável"]
            for partida in dados_ecd.partidas:
                if not partida.historico:
                    continue
                hist_lower = partida.historico.lower()
                if any(p in hist_lower for p in _palavras_hist):
                    baixas_pdd_historico.append(partida)

        total_baixas_hist = sum(p.valor for p in baixas_pdd_historico)

        registros_origem = registros_pdd + registros_perdas + [
            f"M300 adicoes PDD: {len(adicoes_pdd)} lancamentos = R$ {total_adicoes_pdd:,.2f}",
            f"M300 exclusoes PDD: {len(exclusoes_pdd)} lancamentos = R$ {total_exclusoes_pdd:,.2f}",
            f"Historicos de baixa PDD (I250): {len(baixas_pdd_historico)} ocorrencias = R$ {total_baixas_hist:,.2f}",
        ]

        # Cenario 1: PDD adicionada no LALUR mas sem exclusao quando ha baixas reais
        if total_adicoes_pdd > 0 and total_exclusoes_pdd == 0 and (
            total_perdas_reais > 0 or total_baixas_hist > 0
        ):
            base_exclusao = max(total_perdas_reais, total_baixas_hist)
            beneficio = base_exclusao * 0.34  # 34% IRPJ+CSLL
            achados.append(Achado(
                regra=self.codigo,
                titulo="PDD adicionada no LALUR sem exclusao correspondente quando ha baixas definitivas",
                descricao=(
                    f"PDD adicionada no LALUR (M300): R$ {total_adicoes_pdd:,.2f}. "
                    f"Baixas definitivas de creditos no ECD: R$ {total_perdas_reais:,.2f}. "
                    f"Lancamentos de baixa PDD nos historicos (I250): {len(baixas_pdd_historico)} "
                    f"ocorrencias, total R$ {total_baixas_hist:,.2f}. "
                    f"M300 sem exclusoes correspondentes (R$ {total_exclusoes_pdd:,.2f}). "
                    "Quando a perda e efetiva e atende os requisitos do art. 9, a exclusao da "
                    "adicao e obrigatoria (deducao da perda). "
                    f"Beneficio estimado: R$ {beneficio:,.2f}."
                ),
                valor_estimado=beneficio,
                tributo="IRPJ/CSLL",
                base_legal=self.base_legal,
                confianca="media",
                registros_origem=registros_origem,
                recomendacao=(
                    "Verificar cada credito baixado e aplicar os requisitos do art. 9, Lei 9.430/96: "
                    "(1) Valor ate R$ 15.000: credito vencido ha mais de 6 meses (sem garantia); "
                    "(2) Valor entre R$ 15.000 e R$ 100.000: vencido ha mais de 1 ano, sem garantia; "
                    "(3) Valor acima de R$ 100.000: com garantia e processo judicial ou arbitral. "
                    "Para creditos que atendem os requisitos, incluir exclusao no M300 via retificacao da ECF."
                ),
                risco=(
                    "Requer documentacao de cada credito: comprovante de vencimento, "
                    "valor, garantias e acoes de cobranca. Auditores da Receita podem "
                    "questionar perdas sem documentacao suficiente."
                ),
            ))

        # Cenario 2: Baixas de PDD identificadas em historicos sem nenhum tratamento no M300
        elif total_baixas_hist > 1000 and total_adicoes_pdd == 0 and total_exclusoes_pdd == 0:
            beneficio = total_baixas_hist * 0.34
            achados.append(Achado(
                regra=self.codigo,
                titulo="Baixas definitivas de PDD sem tratamento no LALUR",
                descricao=(
                    f"Historicos de baixa de PDD (I250): {len(baixas_pdd_historico)} ocorrencias "
                    f"totalizando R$ {total_baixas_hist:,.2f}. "
                    "Nenhum tratamento encontrado no M300 (sem adicao nem exclusao de PDD). "
                    "Isso pode indicar que a PDD foi diretamente debitada em resultado sem "
                    "adicao/exclusao no LALUR, ou que ha deducao nao formalizada. "
                    f"Beneficio estimado se deducao aplicavel: R$ {beneficio:,.2f}."
                ),
                valor_estimado=beneficio,
                tributo="IRPJ/CSLL",
                base_legal=self.base_legal,
                confianca="baixa",
                registros_origem=registros_origem + [
                    f"I250 hist.: {p.historico[:80]} | R$ {p.valor:,.2f} | {p.dt_lcto}"
                    for p in baixas_pdd_historico[:5]
                ],
                recomendacao=(
                    "Analisar se as baixas atendem os requisitos do art. 9, Lei 9.430/96. "
                    "Se a PDD foi contabilizada e adicionada em anos anteriores e a baixa "
                    "e definitiva neste periodo, ha direito a exclusao no M300."
                ),
                risco=(
                    "Hipotese de baixa confianca. Requer analise do historico de PDD "
                    "de anos anteriores e documentacao das perdas."
                ),
            ))

        if not achados:
            logger.info("R10: Nenhuma inconsistencia de PDD/perdas em creditos identificada.")

        return achados
