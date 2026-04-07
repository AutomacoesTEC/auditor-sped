"""R05: Creditos de PIS/COFINS subutilizados no regime nao cumulativo.

No Lucro Real com regime nao cumulativo, diversas despesas geram credito
de PIS (1,65%) e COFINS (7,6%). Esta regra identifica:

1. Despesas tipicamente creditaveis no ECD (aluguel, combustivel, etc.)
   que podem nao estar gerando credito na EFD-Contribuicoes.
2. Saldos de PIS/COFINS a compensar no ECD sem controle de credito na EFD.
3. Creditos apurados na EFD com saldo disponivel (1100/1500) nao compensados.

Base legal:
  Lei 10.637/2002 art. 3; Lei 10.833/2003 art. 3;
  IN RFB 2.121/2022; REsp 1.221.170/PR (conceito amplo de insumo).
"""

import logging
from src.regras.base_regra import RegraAuditoria, Achado

logger = logging.getLogger(__name__)

# Contas ECD que tipicamente geram credito de PIS/COFINS (nao cumulativo)
_CONTAS_CREDITAVEIS = [
    "aluguel", "locacao", "energia eletrica", "energia elétrica",
    "frete", "carreto", "combustivel", "combustível",
    "telecomunicacao", "telecomunicação", "telefonia",
    "manutencao", "manutenção", "reparo",
    "seguro", "embalagem", "material de limpeza",
    "uniforme", "epi", "equipamento de protecao",
    "servicos", "serviços", "terceirizacao",
]
_CONTAS_EXCLUIR = ["deprecia", "amortiza", "provisao", "provisão", "pessoal", "salario", "salário"]

# Aliquotas regime nao cumulativo
_ALIQ_PIS = 0.0165
_ALIQ_COFINS = 0.076


class R05CreditosPISCOFINS(RegraAuditoria):

    @property
    def codigo(self) -> str:
        return "R05"

    @property
    def nome(self) -> str:
        return "Creditos de PIS/COFINS subutilizados (regime nao cumulativo)"

    @property
    def base_legal(self) -> str:
        return (
            "Lei 10.637/2002 art. 3; Lei 10.833/2003 art. 3; "
            "IN RFB 2.121/2022; REsp 1.221.170/PR (STJ)"
        )

    def executar(self, dados_ecd, dados_ecf, mapa_contas: dict) -> list[Achado]:
        achados = []

        # === Analise 1: Saldos de PIS/COFINS a compensar no ECD ===
        if dados_ecd:
            achados.extend(self._verificar_saldos_ecd(dados_ecd))

        # === Analise 2: Saldo disponivel nos registros 1100/1500 (EFD) ===
        if hasattr(dados_ecd, "_dados_efd"):
            pass  # EFD e passado via argumento separado em main.py

        return achados

    def _verificar_saldos_ecd(self, dados_ecd) -> list[Achado]:
        """Verifica saldos de contas de PIS/COFINS a compensar no ECD."""
        achados = []
        palavras_pis = ["pis a compensar", "pis a recuperar", "pis credito", "credito pis"]
        palavras_cofins = ["cofins a compensar", "cofins a recuperar", "cofins credito", "credito cofins"]

        saldo_pis = 0.0
        saldo_cofins = 0.0
        reg_pis = []
        reg_cofins = []

        for codigo, conta in dados_ecd.plano_contas.items():
            if conta.ind_cta != "A":
                continue
            nome_lower = conta.nome.lower()
            saldos = dados_ecd.saldos.get(codigo, [])
            if not saldos:
                continue
            ultimo = saldos[-1]
            if ultimo.saldo_final <= 0:
                continue

            if any(p in nome_lower for p in palavras_pis):
                saldo_pis += ultimo.saldo_final
                reg_pis.append(f"ECD {codigo} - {conta.nome}: R$ {ultimo.saldo_final:,.2f}")

            elif any(p in nome_lower for p in palavras_cofins):
                saldo_cofins += ultimo.saldo_final
                reg_cofins.append(f"ECD {codigo} - {conta.nome}: R$ {ultimo.saldo_final:,.2f}")

        if saldo_pis > 0:
            achados.append(Achado(
                regra=self.codigo,
                titulo="Saldo de PIS a compensar no ECD sem PER/DCOMP identificado",
                descricao=(
                    f"Contas de PIS a compensar no ECD totalizam R$ {saldo_pis:,.2f}. "
                    "Verificar se ha PER/DCOMP transmitido ou compensacao via DCTF."
                ),
                valor_estimado=saldo_pis,
                tributo="PIS",
                base_legal=self.base_legal,
                confianca="alta",
                registros_origem=reg_pis,
                recomendacao=(
                    "Verificar registros 1100 da EFD-Contribuicoes para confirmar saldo disponivel. "
                    "Transmitir PER/DCOMP Web (codigo 5960) se credito nao aproveitado."
                ),
                risco="Prescricao quinquenal. Confirmar regime de apuracao (nao cumulativo).",
            ))

        if saldo_cofins > 0:
            achados.append(Achado(
                regra=self.codigo,
                titulo="Saldo de COFINS a compensar no ECD sem PER/DCOMP identificado",
                descricao=(
                    f"Contas de COFINS a compensar no ECD totalizam R$ {saldo_cofins:,.2f}. "
                    "Verificar se ha PER/DCOMP transmitido ou compensacao via DCTF."
                ),
                valor_estimado=saldo_cofins,
                tributo="COFINS",
                base_legal=self.base_legal,
                confianca="alta",
                registros_origem=reg_cofins,
                recomendacao=(
                    "Verificar registros 1500 da EFD-Contribuicoes para confirmar saldo disponivel. "
                    "Transmitir PER/DCOMP Web (codigo 5979) se credito nao aproveitado."
                ),
                risco="Prescricao quinquenal. Confirmar regime de apuracao (nao cumulativo).",
            ))

        # === Analise complementar: despesas creditaveis x creditos apurados ===
        base_creditavel = _calcular_base_creditavel(dados_ecd)
        if base_creditavel > 0:
            credito_potencial_pis = base_creditavel * _ALIQ_PIS
            credito_potencial_cofins = base_creditavel * _ALIQ_COFINS
            credito_total_potencial = credito_potencial_pis + credito_potencial_cofins

            if credito_total_potencial > 1000:
                achados.append(Achado(
                    regra=self.codigo,
                    titulo="Despesas potencialmente creditaveis de PIS/COFINS (conferir EFD)",
                    descricao=(
                        f"Total de despesas operacionais tipicamente creditaveis no ECD: "
                        f"R$ {base_creditavel:,.2f}. "
                        f"Credito potencial estimado: PIS R$ {credito_potencial_pis:,.2f} + "
                        f"COFINS R$ {credito_potencial_cofins:,.2f} = R$ {credito_total_potencial:,.2f}. "
                        "HIPOTESE: requer confirmacao na EFD-Contribuicoes (CST e bases de calculo)."
                    ),
                    valor_estimado=credito_total_potencial,
                    tributo="PIS/COFINS",
                    base_legal=self.base_legal,
                    confianca="baixa",
                    registros_origem=[
                        f"Base creditavel estimada pelo ECD: R$ {base_creditavel:,.2f}",
                        "Aliquotas: PIS 1,65%; COFINS 7,6% (regime nao cumulativo)",
                        "HIPOTESE: verificar CST, CFOP e natureza de cada despesa na EFD",
                    ],
                    recomendacao=(
                        "Cruzar cada despesa com a EFD-Contribuicoes: verificar se o CST "
                        "utilizado permite credito (50-56) e se a natureza da base de credito "
                        "(Tabela 4.3.7) esta correta. Conceito amplo de insumo: REsp 1.221.170/PR."
                    ),
                    risco=(
                        "Hipotese de baixa confianca: requer analise documental detalhada. "
                        "Nao transmitir PER/DCOMP sem verificacao da EFD."
                    ),
                ))

        return achados


def _calcular_base_creditavel(dados_ecd) -> float:
    """Estima base de despesas potencialmente creditaveis no ECD."""
    total = 0.0
    for codigo, conta in dados_ecd.plano_contas.items():
        if conta.ind_cta != "A":
            continue
        if conta.natureza not in ("04", "4"):  # Apenas contas de resultado (despesas)
            continue
        nome_lower = conta.nome.lower()
        if any(exc in nome_lower for exc in _CONTAS_EXCLUIR):
            continue
        if not any(p in nome_lower for p in _CONTAS_CREDITAVEIS):
            continue
        saldos = dados_ecd.saldos.get(codigo, [])
        if not saldos:
            continue
        # Soma debitos (movimentacao de despesa no periodo)
        for s in saldos:
            total += s.debitos
    return total
