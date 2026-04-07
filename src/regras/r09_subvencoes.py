"""R09: Subvencoes governamentais mal classificadas ou nao excluidas do LALUR.

Subvencoes para investimento podem ser:
a) Excluidas do lucro liquido no LALUR (art. 30, Lei 12.973/2014) - regime anterior
b) Computadas no credito fiscal de 25% (Lei 14.789/2023) - regime novo (2024+)

Verifica:
  - Conta 511 (subvencoes) ou similares no ECD com saldo/movimentacao
  - Ausencia de exclusao correspondente no M300 (IND_AD_EX = E)
  - Sem credito fiscal de subvencao (regime novo Lei 14.789/2023)

Base legal: Art. 30, Lei 12.973/2014; Lei 14.789/2023; IN RFB 2.170/2024.
"""

import logging
from src.regras.base_regra import RegraAuditoria, Achado

logger = logging.getLogger(__name__)

_PALAVRAS_SUBVENCAO = [
    "subvencao", "subvenção", "subvencoes", "subvenções",
    "incentivo fiscal", "beneficio fiscal", "benefício fiscal",
    "isenção icms", "isencao icms", "reducao icms", "redução icms",
    "credito presumido icms", "crédito presumido icms",
    "credito fiscal icms", "crédito fiscal icms",
    "fundap", "fomentar", "proadi", "desenvolve",
]
_PALAVRAS_EXCLUIR_SUB = ["provisao", "provisão", "a pagar", "a recolher"]

_PALAVRAS_M300_SUB = [
    "subvencao", "subvenção", "incentivo fiscal", "beneficio fiscal",
    "benefício fiscal", "credito fiscal", "isencao", "isenção",
]


class R09Subvencoes(RegraAuditoria):

    @property
    def codigo(self) -> str:
        return "R09"

    @property
    def nome(self) -> str:
        return "Subvencoes governamentais sem exclusao no LALUR ou credito fiscal nao aproveitado"

    @property
    def base_legal(self) -> str:
        return "Art. 30, Lei 12.973/2014; Lei 14.789/2023; IN RFB 2.170/2024"

    def executar(self, dados_ecd, dados_ecf, mapa_contas: dict) -> list[Achado]:
        achados = []

        if not dados_ecd or not dados_ecf:
            logger.warning("R09: ECD e ECF necessarios. Pulando.")
            return achados

        # Busca contas de subvencao no ECD
        total_subvencao = 0.0
        registros_sub = []
        for codigo, conta in dados_ecd.plano_contas.items():
            if conta.ind_cta != "A":
                continue
            nome_lower = conta.nome.lower()
            if any(exc in nome_lower for exc in _PALAVRAS_EXCLUIR_SUB):
                continue
            if not any(p in nome_lower for p in _PALAVRAS_SUBVENCAO):
                continue
            saldos = dados_ecd.saldos.get(codigo, [])
            if not saldos:
                continue
            # Subvencao pode estar em conta de receita (credito) ou ativo
            for s in saldos:
                movimentacao = max(s.creditos, s.debitos)
                if movimentacao > 0:
                    total_subvencao += movimentacao
                    registros_sub.append(
                        f"ECD {codigo} - {conta.nome}: mov. R$ {movimentacao:,.2f}"
                    )
                    break

        if total_subvencao <= 0:
            logger.info("R09: Nenhuma conta de subvencao encontrada no ECD.")
            return achados

        # Busca exclusoes de subvencao no M300
        exclusoes_sub = [
            l for l in dados_ecf.m300_irpj
            if l.ind_ad_ex == "E"
            and any(p in l.descricao.lower() for p in _PALAVRAS_M300_SUB)
        ]
        total_exclusao = sum(l.valor for l in exclusoes_sub)

        # Verifica adicoes (podem ser subvencoes erroneamente adicionadas)
        adicoes_sub = [
            l for l in dados_ecf.m300_irpj
            if l.ind_ad_ex == "A"
            and any(p in l.descricao.lower() for p in _PALAVRAS_M300_SUB)
        ]
        total_adicoes = sum(l.valor for l in adicoes_sub)

        registros_origem = registros_sub + [
            f"M300 exclusoes subvencao: {len(exclusoes_sub)} lancamentos = R$ {total_exclusao:,.2f}",
            f"M300 adicoes subvencao: {len(adicoes_sub)} lancamentos = R$ {total_adicoes:,.2f}",
        ]

        if total_exclusao == 0 and total_adicoes == 0:
            # Subvencao no ECD sem nenhum tratamento no LALUR
            # Estimativa: 25% da subvencao (credito fiscal Lei 14.789/2023)
            credito_estimado = total_subvencao * 0.25
            achados.append(Achado(
                regra=self.codigo,
                titulo="Subvencoes no ECD sem tratamento no LALUR (M300)",
                descricao=(
                    f"Contas de subvencao/incentivo fiscal no ECD: R$ {total_subvencao:,.2f}. "
                    "Nenhum tratamento identificado no M300 (nem exclusao nem adicao). "
                    "Subvencoes para investimento podem ser excluidas do LALUR (regime Lei 12.973/2014) "
                    "ou gerar credito fiscal de 25% (regime Lei 14.789/2023, vigente a partir de 2024). "
                    f"Credito fiscal estimado (hipotese Lei 14.789/2023): R$ {credito_estimado:,.2f}. "
                    "HIPOTESE: requer analise da natureza e regime aplicavel."
                ),
                valor_estimado=credito_estimado,
                tributo="IRPJ/CSLL",
                base_legal=self.base_legal,
                confianca="baixa",
                registros_origem=registros_origem,
                recomendacao=(
                    "Identificar a natureza de cada subvencao: "
                    "(1) Para investimento: verificar se atende condicionalidades do art. 30, Lei 12.973/2014 "
                    "ou se opta pelo regime da Lei 14.789/2023 (credito fiscal de 25%). "
                    "(2) Para custeio: tributada normalmente. "
                    "Se subvencao para investimento nao excluida e houve tributacao, avaliar retificacao da ECF."
                ),
                risco=(
                    "Hipotese de baixa confianca. Requer: (1) analise do ato concessorio; "
                    "(2) verificacao das condicionalidades; (3) escolha do regime (irrevogavel). "
                    "Nao transmitir PER/DCOMP sem laudo juridico-contabil."
                ),
            ))

        elif total_adicoes > 0 and total_exclusao == 0:
            # Subvencao foi adicionada ao LALUR (pior cenario: sendo tributada)
            beneficio_recuperavel = total_adicoes * 0.34  # 34% IRPJ+CSLL
            achados.append(Achado(
                regra=self.codigo,
                titulo="Subvencao adicionada ao LALUR sem exclusao correspondente",
                descricao=(
                    f"Subvencao adicionada no M300 (LALUR): R$ {total_adicoes:,.2f}. "
                    "Adicao sem exclusao pode indicar que a subvencao esta sendo tributada "
                    "quando deveria ser excluida (se para investimento). "
                    f"Beneficio recuperavel estimado: R$ {beneficio_recuperavel:,.2f}. "
                    "HIPOTESE: requer analise da natureza da subvencao."
                ),
                valor_estimado=beneficio_recuperavel,
                tributo="IRPJ/CSLL",
                base_legal=self.base_legal,
                confianca="baixa",
                registros_origem=registros_origem,
                recomendacao=(
                    "Verificar se a adicao e obrigatoria (subvencao para custeio) ou incorreta "
                    "(subvencao para investimento indevidamente adicionada). "
                    "Se incorreta, retificar ECF."
                ),
                risco="Hipotese. Analise juridica e mandatoria antes de qualquer acao.",
            ))

        if not achados:
            logger.info("R09: Subvencoes verificadas, nenhuma inconsistencia critica.")

        return achados
