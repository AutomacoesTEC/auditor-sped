"""R03: CSRF retida na fonte nao deduzida da CSLL apurada.

CSRF = Contribuicao Social Retida na Fonte (PIS/COFINS/CSLL retidos por
orgaos publicos e PJ de direito privado sobre pagamentos de servicos).

Cruza:
  - Contas de CSRF/CSLL retida no ECD (ativo circulante)
  - N670 linhas 15-18 da ECF (deducoes da CSLL)
  - F600 da EFD-Contribuicoes (retencoes declaradas)

Base legal: Lei 10.833/2003, arts. 30-36; IN RFB 459/2004; IN RFB 1.234/2012.
"""

import logging
from src.regras.base_regra import RegraAuditoria, Achado
from config import N670_LINHAS

logger = logging.getLogger(__name__)

_PALAVRAS_CSRF = [
    "csrf", "csll retida", "csll a compensar", "csll a recuperar",
    "contribuicao social retida", "contribuição social retida",
    "pis retido", "cofins retida", "pis a compensar",
    "cofins a compensar", "retencao fonte", "retenção fonte",
    "tributos retidos", "tributo retido",
]
_PALAVRAS_EXCLUIR = ["a pagar", "a recolher", "provisao", "provisão", "passivo"]


class R03CSRFNaoDeduzida(RegraAuditoria):

    @property
    def codigo(self) -> str:
        return "R03"

    @property
    def nome(self) -> str:
        return "CSRF retida na fonte nao deduzida da CSLL/IRPJ"

    @property
    def base_legal(self) -> str:
        return "Lei 10.833/2003, arts. 30-36; IN RFB 459/2004; IN RFB 1.234/2012"

    def executar(self, dados_ecd, dados_ecf, mapa_contas: dict) -> list[Achado]:
        achados = []

        if not dados_ecf:
            logger.warning("R03: ECF necessaria. Pulando.")
            return achados

        # Deducoes de CSLL na ECF (N670 linhas 15-18)
        csll_ret_orgaos = dados_ecf.n670_valor(N670_LINHAS["csll_retida_orgaos"])
        csll_ret_adm = dados_ecf.n670_valor(N670_LINHAS["csll_retida_demais_adm"])
        csll_ret_pj = dados_ecf.n670_valor(N670_LINHAS["csll_retida_pj"])
        csll_ret_mun = dados_ecf.n670_valor(N670_LINHAS["csll_retida_mun"])
        total_csll_deduzido_ecf = csll_ret_orgaos + csll_ret_adm + csll_ret_pj + csll_ret_mun

        registros_origem = [
            f"N670 linha 15 (CSLL retida orgaos): R$ {csll_ret_orgaos:,.2f}",
            f"N670 linha 16 (CSLL retida demais adm): R$ {csll_ret_adm:,.2f}",
            f"N670 linha 17 (CSLL retida PJ): R$ {csll_ret_pj:,.2f}",
            f"N670 linha 18 (CSLL retida mun): R$ {csll_ret_mun:,.2f}",
        ]

        # === Fonte EFD-Contrib: F600 ===
        total_csrf_efd = 0.0
        if hasattr(dados_ecf, "_dados_efd") and dados_ecf._dados_efd:
            pass  # EFD e passado via parametro separado; sera cruzado externamente

        # === Fonte ECD: contas de CSRF a compensar ===
        saldo_csrf_ecd = 0.0
        registros_ecd = []
        if dados_ecd:
            for codigo, conta in dados_ecd.plano_contas.items():
                if conta.ind_cta != "A":
                    continue
                nome_lower = conta.nome.lower()
                if any(exc in nome_lower for exc in _PALAVRAS_EXCLUIR):
                    continue
                if not any(p in nome_lower for p in _PALAVRAS_CSRF):
                    continue
                saldos = dados_ecd.saldos.get(codigo, [])
                if not saldos:
                    continue
                ultimo = saldos[-1]
                if ultimo.saldo_final > 0:
                    saldo_csrf_ecd += ultimo.saldo_final
                    registros_ecd.append(
                        f"ECD conta {codigo} - {conta.nome}: saldo R$ {ultimo.saldo_final:,.2f}"
                    )

        # Analise 1: Saldo contabil de CSRF no ECD vs. deducao na ECF
        if saldo_csrf_ecd > 0 and total_csll_deduzido_ecf == 0:
            achados.append(Achado(
                regra=self.codigo,
                titulo="CSRF/CSLL retida em contas ECD sem deducao na ECF",
                descricao=(
                    f"Contas de CSRF/CSLL a compensar no ECD totalizam R$ {saldo_csrf_ecd:,.2f}. "
                    f"Porem, N670 (CSLL) nao registra nenhuma deducao por retencao na fonte "
                    f"(linhas 15-18 = R$ {total_csll_deduzido_ecf:,.2f}). "
                    "O saldo contabil indica retencao nao aproveitada na apuracao da CSLL."
                ),
                valor_estimado=saldo_csrf_ecd,
                tributo="CSLL",
                base_legal=self.base_legal,
                confianca="alta",
                registros_origem=registros_ecd + registros_origem,
                recomendacao=(
                    "Levantar os comprovantes de retencao (DARF codigo 6015 ou similares). "
                    "Se confirmado, retificar a ECF informando os valores em N670 linhas 15-18 "
                    "ou transmitir PER/DCOMP Web (codigo 5979)."
                ),
                risco="Prescricao quinquenal. Verificar DCTF e DIRF dos tomadores de servico.",
            ))

        elif saldo_csrf_ecd > total_csll_deduzido_ecf + 100.0:
            diferenca = saldo_csrf_ecd - total_csll_deduzido_ecf
            achados.append(Achado(
                regra=self.codigo,
                titulo="CSRF retida em contas ECD excede deducao informada na ECF",
                descricao=(
                    f"Saldo CSRF no ECD: R$ {saldo_csrf_ecd:,.2f}. "
                    f"Total deduzido na ECF (N670 linhas 15-18): R$ {total_csll_deduzido_ecf:,.2f}. "
                    f"Diferenca: R$ {diferenca:,.2f}."
                ),
                valor_estimado=diferenca,
                tributo="CSLL",
                base_legal=self.base_legal,
                confianca="media",
                registros_origem=registros_ecd + registros_origem,
                recomendacao=(
                    "Conciliar saldo contabil de CSRF com comprovantes de retencao. "
                    "Se ha retencao nao deduzida, retificar ECF ou gerar PER/DCOMP."
                ),
                risco="Hipotese: diferenca pode ser de periodos anteriores ou ja compensada via DCOMP.",
            ))

        if not achados:
            logger.info("R03: Nenhuma inconsistencia de CSRF identificada.")

        return achados
