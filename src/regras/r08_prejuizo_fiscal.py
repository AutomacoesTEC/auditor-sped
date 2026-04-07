"""R08: Prejuizo fiscal nao compensado ou compensado abaixo do limite.

No Lucro Real, o prejuizo fiscal de anos anteriores pode ser compensado
com o lucro real do periodo corrente, limitado a 30% do lucro real
ajustado pelas adicoes e exclusoes.

Verifica:
  1. M300 tipo C (compensacoes de prejuizo): se ha base positiva nao compensada
  2. Saldo de prejuizos a compensar na Parte B do LALUR
  3. Se a compensacao realizada esta dentro dos limites de 30%

Base legal: RIR/2018, arts. 580-583; art. 15, Lei 9.065/1995.
"""

import logging
from src.regras.base_regra import RegraAuditoria, Achado
from config import N630_LINHAS

logger = logging.getLogger(__name__)

_PALAVRAS_PREJUIZO_B = [
    "prejuizo fiscal", "prejuízo fiscal", "prejuizo a compensar", "prejuízo a compensar",
    "saldo negativo irpj", "base negativa csll", "base negativa de csll",
]


class R08PrejuizoFiscal(RegraAuditoria):

    @property
    def codigo(self) -> str:
        return "R08"

    @property
    def nome(self) -> str:
        return "Prejuizo fiscal nao compensado ou compensado abaixo do limite de 30%"

    @property
    def base_legal(self) -> str:
        return "RIR/2018, arts. 580-583; art. 15, Lei 9.065/1995; art. 42, Lei 8.981/1995"

    def executar(self, dados_ecd, dados_ecf, mapa_contas: dict) -> list[Achado]:
        achados = []

        if not dados_ecf:
            logger.warning("R08: ECF necessaria. Pulando.")
            return achados

        # Base de calculo IRPJ (lucro real antes da compensacao)
        base_irpj = dados_ecf.n630_valor(N630_LINHAS["base_calculo"])

        if base_irpj <= 0:
            logger.info("R08: Base de calculo IRPJ <= 0. Sem lucro para compensar.")
            return achados

        # Limite de compensacao: 30% do lucro real
        limite_compensacao = base_irpj * 0.30

        # Compensacoes de prejuizo no M300 (tipo C)
        compensacoes = [l for l in dados_ecf.m300_irpj if l.ind_ad_ex == "C"]
        total_compensado = sum(l.valor for l in compensacoes)

        # Verifica saldo de prejuizos na Parte B (M410/M500 registros brutos)
        # M410: Controle de saldos da Parte B do LALUR
        saldo_prejuizo_b = 0.0
        registros_m410 = []
        if "M410" in dados_ecf.registros_brutos:
            for reg in dados_ecf.registros_brutos["M410"]:
                descricao = reg.campo(2).lower()
                if any(p in descricao for p in _PALAVRAS_PREJUIZO_B):
                    vl = reg.campo_monetario(4)  # Saldo periodo
                    if vl > 0:
                        saldo_prejuizo_b += vl
                        registros_m410.append(
                            f"M410 {reg.campo(1)} - {reg.campo(2)}: R$ {vl:,.2f}"
                        )

        registros_origem = [
            f"N630 linha 1 (base de calculo IRPJ): R$ {base_irpj:,.2f}",
            f"Limite de compensacao (30%): R$ {limite_compensacao:,.2f}",
            f"Total compensado no M300 (tipo C): R$ {total_compensado:,.2f}",
            f"Saldo Parte B (M410): R$ {saldo_prejuizo_b:,.2f}",
        ]
        for c in compensacoes[:5]:
            registros_origem.append(f"M300 compensacao: {c.descricao} = R$ {c.valor:,.2f}")

        # Analise 1: Nenhuma compensacao realizada mas pode haver saldo de prejuizo
        if total_compensado == 0 and saldo_prejuizo_b > 0:
            compensacao_possivel = min(saldo_prejuizo_b, limite_compensacao)
            beneficio = compensacao_possivel * 0.25
            achados.append(Achado(
                regra=self.codigo,
                titulo="Saldo de prejuizo fiscal na Parte B sem compensacao no periodo",
                descricao=(
                    f"Saldo de prejuizo fiscal na Parte B do LALUR (M410): R$ {saldo_prejuizo_b:,.2f}. "
                    f"Base de calculo IRPJ no periodo: R$ {base_irpj:,.2f}. "
                    f"Limite de compensacao (30%): R$ {limite_compensacao:,.2f}. "
                    f"Compensacao possivel: R$ {compensacao_possivel:,.2f}. "
                    f"Beneficio fiscal estimado (25% IRPJ): R$ {beneficio:,.2f}."
                ),
                valor_estimado=beneficio,
                tributo="IRPJ",
                base_legal=self.base_legal,
                confianca="alta",
                registros_origem=registros_origem + registros_m410,
                recomendacao=(
                    "Verificar saldo de prejuizos fiscais acumulados na Parte B do LALUR. "
                    "Se ha saldo disponivel, retificar ECF para incluir compensacao em M300 "
                    "ate o limite de 30% do lucro real ajustado. "
                    "Compensacao gera reducao do IRPJ e potencial PER/DCOMP."
                ),
                risco=(
                    "Verificar se os prejuizos sao de atividade operacional ou nao operacional "
                    "(arts. 511-516 RIR). Prejuizos nao operacionais so podem ser compensados "
                    "com lucros nao operacionais."
                ),
            ))

        # Analise 2: Compensacao realizada mas abaixo do limite possivel com saldo disponivel
        elif (
            total_compensado > 0
            and saldo_prejuizo_b > total_compensado
            and total_compensado < limite_compensacao - 1000
        ):
            margem_nao_utilizada = min(limite_compensacao - total_compensado, saldo_prejuizo_b - total_compensado)
            if margem_nao_utilizada > 1000:
                beneficio = margem_nao_utilizada * 0.25
                achados.append(Achado(
                    regra=self.codigo,
                    titulo="Compensacao de prejuizo fiscal abaixo do limite de 30%",
                    descricao=(
                        f"Compensacao realizada: R$ {total_compensado:,.2f}. "
                        f"Limite de 30% da base: R$ {limite_compensacao:,.2f}. "
                        f"Saldo disponivel na Parte B: R$ {saldo_prejuizo_b:,.2f}. "
                        f"Margem nao utilizada: R$ {margem_nao_utilizada:,.2f}. "
                        f"Beneficio fiscal adicional estimado: R$ {beneficio:,.2f}."
                    ),
                    valor_estimado=beneficio,
                    tributo="IRPJ",
                    base_legal=self.base_legal,
                    confianca="media",
                    registros_origem=registros_origem + registros_m410,
                    recomendacao=(
                        "Verificar se havia saldo de prejuizo disponivel superior ao compensado. "
                        "Se o limite nao foi totalmente utilizado, retificar ECF para ampliar a compensacao."
                    ),
                    risco="Verificar se ha restricao de uso dos prejuizos (operacional vs. nao operacional).",
                ))

        if not achados:
            logger.info("R08: Nenhuma inconsistencia de prejuizo fiscal identificada.")

        return achados
