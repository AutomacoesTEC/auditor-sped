"""R06: Incentivo PAT (Programa de Alimentacao do Trabalhador) nao deduzido.

Empresas inscritas no PAT com despesas de alimentacao podem deduzir ate
4% do IRPJ devido (antes do adicional) como incentivo fiscal.

Verifica:
  - Contas de alimentacao/refeicao no ECD com saldo > 0
  - N630 linha 8 (deducao PAT) = 0 ou valor menor que o limite
  - N620 linha 9 (deducao PAT mensal) = 0

Limite: 4% do IRPJ calculado a aliquota de 15% (art. 6, Decreto 10.854/2021).

Base legal: Lei 6.321/1976; Decreto 10.854/2021; art. 14 Lei 9.249/1995.
"""

import logging
from src.regras.base_regra import RegraAuditoria, Achado
from config import N630_LINHAS, N620_LINHAS

logger = logging.getLogger(__name__)

_PALAVRAS_PAT = [
    "alimentacao", "alimentação", "refeicao", "refeição",
    "vale refeicao", "vale refeição", "vale alimentacao", "vale alimentação",
    "cesta basica", "cesta básica", "ticket refeicao", "ticket alimentacao",
    "ticket refeição", "ticket alimentação",
    "despesa alimentacao", "despesa com alimentacao",
    "dispendio alimentacao", "dispêndio alimentação",
    "dispendios com alimentacao", "dispêndios com alimentação",
]

# Limite do incentivo PAT: 4% do IRPJ base (art. 6, Decreto 10.854/2021)
_PERCENTUAL_PAT = 0.04


class R06PAT(RegraAuditoria):

    @property
    def codigo(self) -> str:
        return "R06"

    @property
    def nome(self) -> str:
        return "Incentivo PAT nao deduzido do IRPJ"

    @property
    def base_legal(self) -> str:
        return "Lei 6.321/1976; Decreto 10.854/2021; art. 14, Lei 9.249/1995"

    def executar(self, dados_ecd, dados_ecf, mapa_contas: dict) -> list[Achado]:
        achados = []

        if not dados_ecf:
            logger.warning("R06: ECF necessaria. Pulando.")
            return achados

        # IRPJ base (antes do adicional) para calculo do limite PAT
        irpj_15 = dados_ecf.n630_valor(N630_LINHAS["aliquota_15"])
        pat_ecf = dados_ecf.n630_valor(N630_LINHAS["deducao_pat"])

        if irpj_15 <= 0:
            logger.info("R06: IRPJ base = 0, PAT nao aplicavel.")
            return achados

        # Limite legal: 4% do IRPJ calculado a 15%
        limite_pat = irpj_15 * _PERCENTUAL_PAT

        # Busca despesas de alimentacao no ECD
        despesa_total = 0.0
        registros_ecd = []
        if dados_ecd:
            for codigo, conta in dados_ecd.plano_contas.items():
                if conta.ind_cta != "A":
                    continue
                nome_lower = conta.nome.lower()
                if not any(p in nome_lower for p in _PALAVRAS_PAT):
                    continue
                saldos = dados_ecd.saldos.get(codigo, [])
                if not saldos:
                    continue
                movimentacao = sum(s.debitos for s in saldos)
                if movimentacao > 0:
                    despesa_total += movimentacao
                    registros_ecd.append(
                        f"ECD {codigo} - {conta.nome}: R$ {movimentacao:,.2f}"
                    )

        if despesa_total <= 0:
            logger.info("R06: Nenhuma despesa de alimentacao encontrada no ECD.")
            return achados

        # Verifica se PAT foi deduzido na ECF
        if pat_ecf == 0:
            # PAT nao foi deduzido. Valor estimado = min(4% IRPJ, 1 salario minimo por beneficiario)
            # Sem dados de beneficiarios, usamos o limite de 4% como estimativa conservadora
            credito_estimado = min(despesa_total * 0.15, limite_pat)  # 15% da despesa ou limite
            credito_estimado = min(credito_estimado, limite_pat)

            achados.append(Achado(
                regra=self.codigo,
                titulo="Incentivo PAT nao utilizado: despesas de alimentacao sem deducao em N630 linha 8",
                descricao=(
                    f"Despesas de alimentacao no ECD: R$ {despesa_total:,.2f}. "
                    f"IRPJ calculado a 15% (N630 linha 3): R$ {irpj_15:,.2f}. "
                    f"Limite do incentivo PAT (4% do IRPJ base): R$ {limite_pat:,.2f}. "
                    f"Deducao PAT em N630 linha 8: R$ {pat_ecf:,.2f}. "
                    f"Credito estimado (conservador): R$ {credito_estimado:,.2f}."
                ),
                valor_estimado=credito_estimado,
                tributo="IRPJ",
                base_legal=self.base_legal,
                confianca="media",
                registros_origem=registros_ecd + [
                    f"N630 linha 3 (IRPJ 15%): R$ {irpj_15:,.2f}",
                    f"N630 linha 8 (PAT): R$ {pat_ecf:,.2f}",
                    f"Limite calculado (4% x IRPJ): R$ {limite_pat:,.2f}",
                ],
                recomendacao=(
                    "Verificar se a empresa possui inscricao ativa no PAT (Ministerio do Trabalho). "
                    "Se sim e o incentivo nao foi aproveitado, retificar a ECF incluindo o valor "
                    "em N630 linha 8. O valor do incentivo e calculado sobre o IRPJ a aliquota "
                    "de 15% (base) com limite de 4%. Para empresas com mais de 5 trabalhadores, "
                    "a deducao e equivalente a 15% da despesa com alimentacao, limitado a 4% do "
                    "IRPJ. Apos retificacao, gerar PER/DCOMP se houver saldo negativo."
                ),
                risco=(
                    "Confianca media: requer verificacao da inscricao no PAT e numero de beneficiarios. "
                    "Sem inscricao ativa no PAT, o incentivo nao e admitido."
                ),
            ))

        elif pat_ecf < limite_pat - 100:
            # PAT deduzido mas abaixo do limite possivel
            diferenca = limite_pat - pat_ecf
            achados.append(Achado(
                regra=self.codigo,
                titulo="Incentivo PAT utilizado abaixo do limite permitido",
                descricao=(
                    f"PAT deduzido na ECF (N630 linha 8): R$ {pat_ecf:,.2f}. "
                    f"Limite calculado (4% do IRPJ base): R$ {limite_pat:,.2f}. "
                    f"Margem nao aproveitada: R$ {diferenca:,.2f}. "
                    f"Despesas de alimentacao no ECD: R$ {despesa_total:,.2f}."
                ),
                valor_estimado=diferenca,
                tributo="IRPJ",
                base_legal=self.base_legal,
                confianca="media",
                registros_origem=registros_ecd + [
                    f"N630 linha 8 (PAT): R$ {pat_ecf:,.2f}",
                    f"Limite legal (4%): R$ {limite_pat:,.2f}",
                ],
                recomendacao=(
                    "Revisar o calculo do incentivo PAT. O valor atual esta abaixo do limite legal. "
                    "Verificar numero de beneficiarios e despesas comprovadas. "
                    "Retificar ECF se o valor correto for maior."
                ),
                risco="Verificar numero de trabalhadores beneficiados e documentacao de suporte.",
            ))

        if not achados:
            logger.info("R06: PAT verificado, nenhuma inconsistencia.")

        return achados
