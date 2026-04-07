"""R01: Saldo negativo de IRPJ/CSLL não compensado.

Verificado com dados reais:
  - N630 linha 3 (15%) + linha 4 (adicional) = IRPJ devido
  - N630 linha 24 = estimativas pagas
  - N630 linha 20 = IRRF deduzido
  - N630 linha 26 = IRPJ a pagar
  - N670 linhas equivalentes para CSLL
  - Y570 = IRRF retido (fonte detalhada)
  - Y580 = PER/DCOMP transmitidos
"""

import logging
from src.regras.base_regra import RegraAuditoria, Achado
from config import N630_LINHAS, N670_LINHAS

logger = logging.getLogger(__name__)


class R01SaldoNegativo(RegraAuditoria):

    @property
    def codigo(self) -> str:
        return "R01"

    @property
    def nome(self) -> str:
        return "Saldo negativo de IRPJ/CSLL não compensado"

    @property
    def base_legal(self) -> str:
        return "Art. 6, Lei 9.430/1996; arts. 228-229, IN RFB 1.700/2017"

    def executar(self, dados_ecd, dados_ecf, mapa_contas: dict) -> list[Achado]:
        achados = []
        if not dados_ecf:
            return achados

        # === IRPJ ===
        irpj_15 = dados_ecf.n630_valor(N630_LINHAS["aliquota_15"])
        irpj_adic = dados_ecf.n630_valor(N630_LINHAS["adicional"])
        irpj_devido = irpj_15 + irpj_adic

        estimativas_irpj = dados_ecf.n630_valor(N630_LINHAS["estimativas_pagas"])
        irrf_deduzido = dados_ecf.n630_valor(N630_LINHAS["irrf_retido"])
        irpj_a_pagar = dados_ecf.n630_valor(N630_LINHAS["irpj_a_pagar"])

        # Deduções de incentivos (PAT, criança, idoso, etc.)
        pat = dados_ecf.n630_valor(N630_LINHAS["deducao_pat"])
        crianca = dados_ecf.n630_valor(N630_LINHAS["deducao_crianca"])
        idoso = dados_ecf.n630_valor(N630_LINHAS["deducao_idoso"])
        total_incentivos = pat + crianca + idoso

        total_deducoes = estimativas_irpj + irrf_deduzido + total_incentivos
        saldo_negativo_irpj = total_deducoes - irpj_devido

        if saldo_negativo_irpj > 0 and irpj_a_pagar == 0:
            # Verificar se há PER/DCOMP
            total_perdcomp = sum(p.valor for p in dados_ecf.y580_perdcomp)

            valor_nao_compensado = saldo_negativo_irpj - total_perdcomp
            if valor_nao_compensado > 0:
                achados.append(Achado(
                    regra=self.codigo,
                    titulo="Saldo negativo de IRPJ não compensado",
                    descricao=(
                        f"IRPJ devido: R$ {irpj_devido:,.2f} (15%: {irpj_15:,.2f} + Adic: {irpj_adic:,.2f}). "
                        f"Estimativas pagas: R$ {estimativas_irpj:,.2f}. IRRF deduzido: R$ {irrf_deduzido:,.2f}. "
                        f"Incentivos: R$ {total_incentivos:,.2f}. "
                        f"Saldo negativo: R$ {saldo_negativo_irpj:,.2f}. "
                        f"PER/DCOMP: R$ {total_perdcomp:,.2f}. "
                        f"Crédito disponível: R$ {valor_nao_compensado:,.2f}."
                    ),
                    valor_estimado=valor_nao_compensado,
                    tributo="IRPJ",
                    base_legal=self.base_legal,
                    confianca="alta",
                    registros_origem=[
                        f"N630 linha 3: 15% = R$ {irpj_15:,.2f}",
                        f"N630 linha 4: Adicional = R$ {irpj_adic:,.2f}",
                        f"N630 linha 24: Estimativas = R$ {estimativas_irpj:,.2f}",
                        f"N630 linha 20: IRRF = R$ {irrf_deduzido:,.2f}",
                        f"N630 linha 26: A pagar = R$ {irpj_a_pagar:,.2f}",
                    ],
                    recomendacao="Transmitir PER/DCOMP Web. Prazo: 5 anos do encerramento do período.",
                    risco="Prescrição quinquenal.",
                ))

        # === IRRF retido e não deduzido (Y570) ===
        total_irrf_retido = sum(r.vl_ir_retido for r in dados_ecf.y570_irrf)
        total_irrf_utilizado = sum(r.vl_ir_utilizado for r in dados_ecf.y570_irrf)

        if total_irrf_retido > 0 and total_irrf_utilizado == 0 and irrf_deduzido == 0:
            achados.append(Achado(
                regra=self.codigo,
                titulo="IRRF retido (Y570) não deduzido nem utilizado",
                descricao=(
                    f"Y570 registra IRRF retido de R$ {total_irrf_retido:,.2f} "
                    f"com utilização de R$ {total_irrf_utilizado:,.2f}. "
                    f"N630 linha 20 (IRRF deduzido) = R$ {irrf_deduzido:,.2f}. "
                    "IRRF não está sendo aproveitado."
                ),
                valor_estimado=total_irrf_retido,
                tributo="IRPJ",
                base_legal="Arts. 714-716 RIR/2018; art. 36 IN RFB 1.700/2017",
                confianca="alta",
                registros_origem=[
                    f"Y570: {r.nome} - IRRF R$ {r.vl_ir_retido:,.2f} (util: R$ {r.vl_ir_utilizado:,.2f})"
                    for r in dados_ecf.y570_irrf
                ],
                recomendacao="Incluir IRRF na dedução do IRPJ (N630 linha 20) via retificação da ECF, ou gerar PER/DCOMP.",
                risco="Prescrição quinquenal. Verificar se IRRF foi informado em DCTF.",
            ))

        # === CSLL ===
        csll_devida = dados_ecf.n670_valor(N670_LINHAS["total_csll"])
        est_csll = dados_ecf.n670_valor(N670_LINHAS["estimativas_pagas"])
        est_csll_parc = dados_ecf.n670_valor(N670_LINHAS["estimativas_parceladas"])
        csll_ret_pj = dados_ecf.n670_valor(N670_LINHAS["csll_retida_pj"])
        csll_ret_orgaos = dados_ecf.n670_valor(N670_LINHAS["csll_retida_orgaos"])
        csll_a_pagar = dados_ecf.n670_valor(N670_LINHAS["csll_a_pagar"])

        total_ded_csll = est_csll + est_csll_parc + csll_ret_pj + csll_ret_orgaos
        saldo_neg_csll = total_ded_csll - csll_devida

        if saldo_neg_csll > 0 and csll_a_pagar == 0:
            achados.append(Achado(
                regra=self.codigo,
                titulo="Saldo negativo de CSLL não compensado",
                descricao=(
                    f"CSLL devida: R$ {csll_devida:,.2f}. "
                    f"Estimativas: R$ {est_csll:,.2f} + parceladas: R$ {est_csll_parc:,.2f}. "
                    f"CSLL retida PJ: R$ {csll_ret_pj:,.2f}. "
                    f"Saldo negativo: R$ {saldo_neg_csll:,.2f}."
                ),
                valor_estimado=saldo_neg_csll,
                tributo="CSLL",
                base_legal="Art. 6, Lei 9.430/1996; IN RFB 1.700/2017",
                confianca="alta",
                registros_origem=[
                    f"N670 linha 4: CSLL devida = R$ {csll_devida:,.2f}",
                    f"N670 linha 19: Estimativas = R$ {est_csll:,.2f}",
                    f"N670 linha 20: Parceladas = R$ {est_csll_parc:,.2f}",
                    f"N670 linha 21: A pagar = R$ {csll_a_pagar:,.2f}",
                ],
                recomendacao="Transmitir PER/DCOMP Web.",
                risco="Prescrição quinquenal.",
            ))

        if not achados:
            logger.info("R01: Nenhum saldo negativo não compensado identificado.")

        return achados
