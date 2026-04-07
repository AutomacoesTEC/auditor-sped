"""R02: IRRF retido em contas contabeis ECD nao aproveitado na ECF.

Cruza saldos de contas de IRRF/IRPJ a compensar no ECD (I155) com
a deducao informada na ECF (N630 linha 20). Se ha saldo ativo na conta
de ativo mas N630 linha 20 = 0, o IRRF nao foi aproveitado.

Base legal: Arts. 714-716 RIR/2018; art. 36 IN RFB 1.700/2017.
"""

import logging
from src.regras.base_regra import RegraAuditoria, Achado
from config import N630_LINHAS

logger = logging.getLogger(__name__)

# Palavras-chave que identificam contas de IRRF/IRPJ a compensar
_PALAVRAS_IRRF = [
    "irrf", "ir retido", "imposto de renda retido",
    "ir a compensar", "irpj a compensar", "ir a recuperar",
    "imposto renda fonte", "imposto de renda a compensar",
]
_PALAVRAS_EXCLUIR = ["a pagar", "a recolher", "passivo", "provisao", "provisão"]


class R02IRRFContas(RegraAuditoria):

    @property
    def codigo(self) -> str:
        return "R02"

    @property
    def nome(self) -> str:
        return "IRRF retido em contas ECD nao aproveitado na ECF"

    @property
    def base_legal(self) -> str:
        return "Arts. 714-716 RIR/2018; art. 36 IN RFB 1.700/2017; art. 6 Lei 9.430/1996"

    def executar(self, dados_ecd, dados_ecf, mapa_contas: dict) -> list[Achado]:
        achados = []

        if not dados_ecd or not dados_ecf:
            logger.warning("R02: ECD e ECF sao necessarios. Pulando.")
            return achados

        irrf_ecf = dados_ecf.n630_valor(N630_LINHAS["irrf_retido"])

        # Busca contas de IRRF/IRPJ a compensar com saldo devedor (ativo)
        contas_irrf = _buscar_contas_irrf(dados_ecd.plano_contas)
        if not contas_irrf:
            logger.info("R02: Nenhuma conta de IRRF/IRPJ a compensar encontrada no ECD.")
            return achados

        saldo_total_contas = 0.0
        registros_origem = []

        for codigo in contas_irrf:
            saldos = dados_ecd.saldos.get(codigo, [])
            if not saldos:
                continue
            ultimo = saldos[-1]
            # Conta de ativo: saldo devedor (D) e positivo indica credito disponivel
            if ultimo.saldo_final > 0 and ultimo.ind_dc_fin in ("D", ""):
                saldo_total_contas += ultimo.saldo_final
                nome_conta = dados_ecd.plano_contas[codigo].nome
                registros_origem.append(
                    f"I155 conta {codigo} - {nome_conta}: saldo R$ {ultimo.saldo_final:,.2f} ({ultimo.ind_dc_fin})"
                )

        if saldo_total_contas <= 0:
            logger.info("R02: Nenhum saldo relevante em contas de IRRF a compensar.")
            return achados

        # Verifica se o valor contabil difere do aproveitado na ECF
        diferenca = saldo_total_contas - irrf_ecf
        if diferenca > 100.0:  # Tolerancia de R$ 100 para arredondamentos
            achados.append(Achado(
                regra=self.codigo,
                titulo="IRRF em contas ECD superior ao aproveitado na ECF (N630 linha 20)",
                descricao=(
                    f"Saldo total de contas de IRRF/IRPJ a compensar no ECD: R$ {saldo_total_contas:,.2f}. "
                    f"IRRF deduzido na ECF (N630 linha 20): R$ {irrf_ecf:,.2f}. "
                    f"Diferenca nao aproveitada: R$ {diferenca:,.2f}. "
                    "O saldo contabil indica que ha IRRF retido que nao foi utilizado na apuracao do IRPJ."
                ),
                valor_estimado=diferenca,
                tributo="IRPJ",
                base_legal=self.base_legal,
                confianca="alta",
                registros_origem=registros_origem + [
                    f"N630 linha 20 (ECF): IRRF deduzido = R$ {irrf_ecf:,.2f}"
                ],
                recomendacao=(
                    "Verificar se o saldo contabil representa IRRF efetivamente retido. "
                    "Se confirmado, retificar a ECF para incluir o valor em N630 linha 20 "
                    "ou transmitir PER/DCOMP Web (codigo 1300/1767)."
                ),
                risco=(
                    "Prescricao quinquenal a partir do encerramento do periodo de apuracao. "
                    "Verificar DCTF para confirmar que o IRRF foi informado corretamente."
                ),
            ))

        return achados


def _buscar_contas_irrf(plano_contas: dict) -> list[str]:
    """Identifica codigos de contas analiticas de IRRF/IRPJ a compensar."""
    resultado = []
    for codigo, conta in plano_contas.items():
        if conta.ind_cta != "A":
            continue
        nome_lower = conta.nome.lower()
        tem_exclusao = any(exc in nome_lower for exc in _PALAVRAS_EXCLUIR)
        if tem_exclusao:
            continue
        if any(p in nome_lower for p in _PALAVRAS_IRRF):
            resultado.append(codigo)
    return resultado
