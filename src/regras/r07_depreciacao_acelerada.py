"""R07: Depreciacao acelerada incentivada nao aplicada no LALUR.

No Lucro Real, bens do ativo imobilizado adquiridos novos podem ser
depreciados de forma acelerada para fins fiscais (exclusao no LALUR),
enquanto a contabilidade registra a taxa normal. A diferenca entre a
depreciacao fiscal e contabil gera exclusao na Parte A do LALUR (M300).

Verificacoes:
  1. Contas de depreciacao com movimentacao no ECD
  2. Ausencia de exclusoes de depreciacao em M300 (IND_AD_EX = E)
  3. Saldo de bens do imobilizado (conta de ativo imobilizado)

Base legal: RIR/2018 arts. 323-326; IN RFB 1.700/2017; Lei 14.871/2024 (novos setores).
"""

import logging
from src.regras.base_regra import RegraAuditoria, Achado

logger = logging.getLogger(__name__)

_PALAVRAS_DEPRECIACAO = [
    "depreciacao", "depreciação", "amortizacao", "amortização",
    "despesa de depreciacao", "despesa com depreciacao",
]
_PALAVRAS_EXCLUIR_DEP = ["depreciacao acumulada", "depreciação acumulada", "provisao", "provisão"]

_PALAVRAS_IMOBILIZADO = [
    "imobilizado", "maquinas", "máquinas", "equipamentos", "veiculos",
    "veículos", "maquinario", "maquinário", "instalacoes", "instalações",
    "moveis", "móveis", "computadores", "informatica", "informática",
]
_PALAVRAS_EXCLUIR_IMOB = [
    "depreciacao acumulada", "depreciação acumulada",
    "amortizacao acumulada", "amortização acumulada",
    "alienado", "baixado",
]

# Palavras que indicam exclusao de depreciacao no M300
_PALAVRAS_M300_DEP = [
    "depreciacao", "depreciação", "amortizacao", "amortização",
    "depreciacao acelerada", "exclusao de depreciacao",
]


class R07DepreciacaoAcelerada(RegraAuditoria):

    @property
    def codigo(self) -> str:
        return "R07"

    @property
    def nome(self) -> str:
        return "Depreciacao acelerada incentivada nao aplicada no LALUR"

    @property
    def base_legal(self) -> str:
        return "RIR/2018 arts. 323-326; IN RFB 1.700/2017, art. 170; Lei 14.871/2024"

    def executar(self, dados_ecd, dados_ecf, mapa_contas: dict) -> list[Achado]:
        achados = []

        if not dados_ecd or not dados_ecf:
            logger.warning("R07: ECD e ECF necessarios. Pulando.")
            return achados

        # Depreciacao contabilizada no ECD
        total_depreciacao_ecd = 0.0
        registros_dep = []
        for codigo, conta in dados_ecd.plano_contas.items():
            if conta.ind_cta != "A":
                continue
            nome_lower = conta.nome.lower()
            if any(exc in nome_lower for exc in _PALAVRAS_EXCLUIR_DEP):
                continue
            if not any(p in nome_lower for p in _PALAVRAS_DEPRECIACAO):
                continue
            saldos = dados_ecd.saldos.get(codigo, [])
            if not saldos:
                continue
            movimentacao = sum(s.debitos for s in saldos)
            if movimentacao > 0:
                total_depreciacao_ecd += movimentacao
                registros_dep.append(
                    f"ECD {codigo} - {conta.nome}: R$ {movimentacao:,.2f}"
                )

        if total_depreciacao_ecd <= 0:
            logger.info("R07: Nenhuma depreciacao encontrada no ECD.")
            return achados

        # Busca exclusoes de depreciacao no M300 (IND_AD_EX = E)
        exclusoes_depreciacao = [
            l for l in dados_ecf.m300_irpj
            if l.ind_ad_ex == "E"
            and any(p in l.descricao.lower() for p in _PALAVRAS_M300_DEP)
        ]
        total_exclusao_m300 = sum(l.valor for l in exclusoes_depreciacao)

        # Saldo de bens do imobilizado
        total_imobilizado = 0.0
        registros_imob = []
        for codigo, conta in dados_ecd.plano_contas.items():
            if conta.ind_cta != "A":
                continue
            nome_lower = conta.nome.lower()
            if any(exc in nome_lower for exc in _PALAVRAS_EXCLUIR_IMOB):
                continue
            if not any(p in nome_lower for p in _PALAVRAS_IMOBILIZADO):
                continue
            saldos = dados_ecd.saldos.get(codigo, [])
            if not saldos:
                continue
            ultimo = saldos[-1]
            if ultimo.saldo_final > 0:
                total_imobilizado += ultimo.saldo_final
                registros_imob.append(
                    f"ECD {codigo} - {conta.nome}: saldo R$ {ultimo.saldo_final:,.2f}"
                )

        if total_exclusao_m300 == 0 and total_depreciacao_ecd > 0:
            # Nenhuma exclusao de depreciacao no LALUR
            # Estimativa conservadora: depreciacao acelerada poderia duplicar a taxa por 1 ano
            # Para bens novos, RIR permite depreciacao integral no ano de aquisicao (art. 323)
            # Estimativa = 50% da depreciacao contabilizada (presume que metade dos bens sao novos)
            estimativa_exclusao = total_depreciacao_ecd * 0.5
            beneficio_irpj = estimativa_exclusao * 0.25  # 25% (15% + 10% adicional)

            achados.append(Achado(
                regra=self.codigo,
                titulo="Depreciacao acelerada nao escriturada no LALUR (M300 sem exclusoes de depreciacao)",
                descricao=(
                    f"Depreciacao contabilizada no ECD: R$ {total_depreciacao_ecd:,.2f}. "
                    f"Exclusoes de depreciacao no M300 (LALUR): R$ {total_exclusao_m300:,.2f}. "
                    f"Saldo do imobilizado no ECD: R$ {total_imobilizado:,.2f}. "
                    "A ausencia de exclusoes pode indicar que a depreciacao acelerada incentivada "
                    "nao foi aplicada. "
                    f"Beneficio fiscal estimado (hipotese conservadora): R$ {beneficio_irpj:,.2f}. "
                    "HIPOTESE: requer levantamento dos bens adquiridos no periodo."
                ),
                valor_estimado=beneficio_irpj,
                tributo="IRPJ",
                base_legal=self.base_legal,
                confianca="baixa",
                registros_origem=registros_dep + [
                    f"M300 exclusoes de depreciacao: {len(exclusoes_depreciacao)} lancamentos (R$ {total_exclusao_m300:,.2f})",
                ] + registros_imob[:5],
                recomendacao=(
                    "Levantar o livro de imobilizado e identificar bens adquiridos novos no periodo. "
                    "Bens com vida util superior a 1 ano adquiridos novos podem ter depreciacao "
                    "acelerada de ate 50% no ano de aquisicao (RIR art. 323). "
                    "Setores beneficiados pela Lei 14.871/2024 podem ter depreciacao integral. "
                    "Se aplicavel, retificar ECF incluindo exclusao no M300."
                ),
                risco=(
                    "Hipotese de baixa confianca. Requer verificacao dos ativos adquiridos novos. "
                    "Depreciacoes de bens usados, impartizados ou ja depreciados integralmente "
                    "nao geram direito ao beneficio."
                ),
            ))

        elif total_exclusao_m300 > 0:
            logger.info(
                "R07: Exclusoes de depreciacao no M300: R$ %.2f (%d lancamentos).",
                total_exclusao_m300, len(exclusoes_depreciacao)
            )

        return achados
