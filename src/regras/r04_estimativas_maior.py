"""R04: Estimativas mensais de IRPJ/CSLL pagas a maior.

Compara a soma das estimativas mensais (N620 linha 26, todos os meses)
com o IRPJ anual devido (N630 linhas 3+4). Se as estimativas excedem
o imposto devido e o contribuinte nao registrou saldo negativo nem
PER/DCOMP, ha credito nao reivindicado.

Logica:
  Total estimativas pagas (N620 linha 26, soma mensal)
  vs. IRPJ devido no ajuste anual (N630 linhas 3+4)
  Se total_est > irpj_devido => saldo negativo potencial.
  Verificar se N630 linha 24 coincide com N620 linha 26.

Base legal: Lei 9.430/1996, arts. 2-6; IN RFB 1.700/2017.
"""

import logging
from src.regras.base_regra import RegraAuditoria, Achado
from config import N630_LINHAS, N670_LINHAS, N620_LINHAS

logger = logging.getLogger(__name__)


class R04EstimativasMaior(RegraAuditoria):

    @property
    def codigo(self) -> str:
        return "R04"

    @property
    def nome(self) -> str:
        return "Estimativas mensais de IRPJ/CSLL pagas a maior"

    @property
    def base_legal(self) -> str:
        return "Lei 9.430/1996, arts. 2-6; IN RFB 1.700/2017, art. 5"

    def executar(self, dados_ecd, dados_ecf, mapa_contas: dict) -> list[Achado]:
        achados = []

        if not dados_ecf:
            logger.warning("R04: ECF necessaria. Pulando.")
            return achados

        # === IRPJ ===
        # Estimativas mensais: soma de N620 linha 26 (IRPJ devido no mes)
        estimativas_mensais_irpj = dados_ecf.n620_valores_por_linha(N620_LINHAS["irpj_devido_mes"])
        total_estimativas_n620 = sum(estimativas_mensais_irpj)

        # Valor registrado no ajuste anual como estimativas pagas
        estimativas_n630 = dados_ecf.n630_valor(N630_LINHAS["estimativas_pagas"])
        estimativas_parc_n630 = dados_ecf.n630_valor(N630_LINHAS.get("estimativas_parceladas", "25"))

        # IRPJ devido anual
        irpj_15 = dados_ecf.n630_valor(N630_LINHAS["aliquota_15"])
        irpj_adic = dados_ecf.n630_valor(N630_LINHAS["adicional"])
        irpj_devido = irpj_15 + irpj_adic
        irpj_a_pagar = dados_ecf.n630_valor(N630_LINHAS["irpj_a_pagar"])

        # PER/DCOMP ja transmitidos
        total_perdcomp = sum(p.valor for p in dados_ecf.y580_perdcomp)

        registros_n620 = []
        for i, v in enumerate(estimativas_mensais_irpj, start=1):
            if v > 0:
                registros_n620.append(f"N620 mes {i:02d} linha 26: R$ {v:,.2f}")

        # Analise: divergencia entre N620 acumulado e N630 linha 24
        if total_estimativas_n620 > 0 and abs(total_estimativas_n620 - estimativas_n630) > 500:
            achados.append(Achado(
                regra=self.codigo,
                titulo="Divergencia entre estimativas mensais (N620) e ajuste anual (N630 linha 24)",
                descricao=(
                    f"Soma das estimativas mensais (N620 linha 26): R$ {total_estimativas_n620:,.2f}. "
                    f"Estimativas no ajuste anual (N630 linha 24): R$ {estimativas_n630:,.2f}. "
                    f"Diferenca: R$ {abs(total_estimativas_n620 - estimativas_n630):,.2f}. "
                    "Divergencia pode indicar estimativas pagas nao escrituradas no ajuste anual."
                ),
                valor_estimado=abs(total_estimativas_n620 - estimativas_n630),
                tributo="IRPJ",
                base_legal=self.base_legal,
                confianca="media",
                registros_origem=registros_n620 + [
                    f"N630 linha 24 (estimativas no ajuste): R$ {estimativas_n630:,.2f}",
                    f"N630 linha 3+4 (IRPJ devido): R$ {irpj_devido:,.2f}",
                ],
                recomendacao=(
                    "Conciliar DARF de estimativas pagas com N620 e N630. "
                    "Se ha estimativas pagas nao incluidas em N630, retificar ECF. "
                    "Pode gerar saldo negativo adicional e direito a PER/DCOMP."
                ),
                risco="Verificar DCTF mensal para confirmar estimativas efetivamente recolhidas.",
            ))

        # Analise: estimativas > IRPJ devido sem aproveitamento
        total_est_irpj = estimativas_n630 + estimativas_parc_n630
        excesso_irpj = total_est_irpj - irpj_devido
        if excesso_irpj > 500 and irpj_a_pagar == 0 and total_perdcomp < excesso_irpj:
            credito_disponivel = excesso_irpj - total_perdcomp
            achados.append(Achado(
                regra=self.codigo,
                titulo="Estimativas de IRPJ pagas a maior sem PER/DCOMP correspondente",
                descricao=(
                    f"Total de estimativas IRPJ (N630 linhas 24+25): R$ {total_est_irpj:,.2f}. "
                    f"IRPJ devido no ajuste anual (15% + adicional): R$ {irpj_devido:,.2f}. "
                    f"Excesso: R$ {excesso_irpj:,.2f}. "
                    f"PER/DCOMP transmitidos (Y580): R$ {total_perdcomp:,.2f}. "
                    f"Credito disponivel estimado: R$ {credito_disponivel:,.2f}."
                ),
                valor_estimado=credito_disponivel,
                tributo="IRPJ",
                base_legal=self.base_legal,
                confianca="alta",
                registros_origem=[
                    f"N630 linha 3 (15%): R$ {irpj_15:,.2f}",
                    f"N630 linha 4 (adicional): R$ {irpj_adic:,.2f}",
                    f"N630 linha 24 (estimativas): R$ {estimativas_n630:,.2f}",
                    f"N630 linha 25 (estimativas parceladas): R$ {estimativas_parc_n630:,.2f}",
                    f"N630 linha 26 (IRPJ a pagar): R$ {irpj_a_pagar:,.2f}",
                    f"Y580 (PER/DCOMP): R$ {total_perdcomp:,.2f}",
                ],
                recomendacao=(
                    "Transmitir PER/DCOMP Web (codigo 1300) para restituicao ou compensacao "
                    "do saldo negativo de IRPJ. Prazo: 5 anos do encerramento do periodo."
                ),
                risco="Prescricao quinquenal. Verificar DCTF para confirmar estimativas pagas.",
            ))

        # === CSLL ===
        csll_devida = dados_ecf.n670_valor(N670_LINHAS["total_csll"])
        est_csll = dados_ecf.n670_valor(N670_LINHAS["estimativas_pagas"])
        est_csll_parc = dados_ecf.n670_valor(N670_LINHAS["estimativas_parceladas"])
        csll_a_pagar = dados_ecf.n670_valor(N670_LINHAS["csll_a_pagar"])
        total_est_csll = est_csll + est_csll_parc
        excesso_csll = total_est_csll - csll_devida

        if excesso_csll > 500 and csll_a_pagar == 0:
            achados.append(Achado(
                regra=self.codigo,
                titulo="Estimativas de CSLL pagas a maior sem aproveitamento",
                descricao=(
                    f"Total estimativas CSLL (N670 linhas 19+20): R$ {total_est_csll:,.2f}. "
                    f"CSLL devida (N670 linha 4): R$ {csll_devida:,.2f}. "
                    f"Excesso: R$ {excesso_csll:,.2f}."
                ),
                valor_estimado=excesso_csll,
                tributo="CSLL",
                base_legal=self.base_legal,
                confianca="alta",
                registros_origem=[
                    f"N670 linha 4 (CSLL devida): R$ {csll_devida:,.2f}",
                    f"N670 linha 19 (estimativas): R$ {est_csll:,.2f}",
                    f"N670 linha 20 (parceladas): R$ {est_csll_parc:,.2f}",
                    f"N670 linha 21 (a pagar): R$ {csll_a_pagar:,.2f}",
                ],
                recomendacao="Transmitir PER/DCOMP Web (codigo 5929) para CSLL.",
                risco="Prescricao quinquenal.",
            ))

        if not achados:
            logger.info("R04: Nenhum excesso de estimativas identificado.")

        return achados
