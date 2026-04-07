"""Auditor SPED - Orquestrador principal."""

import argparse
import logging
import os
import sys
import json

from config import LOG_FORMAT, LOG_LEVEL
from src.parsers.ecd_parser import parse_ecd, DadosECD
from src.parsers.ecf_parser import parse_ecf, DadosECF
from src.parsers.efd_contrib_parser import parse_efd_contrib, DadosEFDContrib
from src.regras.base_regra import Achado
from src.regras.r01_saldo_negativo import R01SaldoNegativo
from src.regras.r02_irrf_contas import R02IRRFContas
from src.regras.r03_csrf_nao_deduzida import R03CSRFNaoDeduzida
from src.regras.r04_estimativas_maior import R04EstimativasMaior
from src.regras.r05_creditos_pis_cofins import R05CreditosPISCOFINS
from src.regras.r06_pat import R06PAT
from src.regras.r07_depreciacao_acelerada import R07DepreciacaoAcelerada
from src.regras.r08_prejuizo_fiscal import R08PrejuizoFiscal
from src.regras.r09_subvencoes import R09Subvencoes
from src.regras.r10_perdas_creditos import R10PerdasCreditos
from src.gatilhos.motor_gatilhos import (
    executar_gatilhos_conta,
    executar_gatilhos_historico,
    resumo_gatilhos,
    AchadoGatilho,
)

# Todas as regras de auditoria implementadas
REGRAS = [
    R01SaldoNegativo(),
    R02IRRFContas(),
    R03CSRFNaoDeduzida(),
    R04EstimativasMaior(),
    R05CreditosPISCOFINS(),
    R06PAT(),
    R07DepreciacaoAcelerada(),
    R08PrejuizoFiscal(),
    R09Subvencoes(),
    R10PerdasCreditos(),
]


def configurar_logging(verbose: bool = False):
    logging.basicConfig(
        format=LOG_FORMAT,
        level=logging.DEBUG if verbose else LOG_LEVEL,
    )


def _validar_arquivo_entrada(caminho: str | None, descricao: str) -> str | None:
    """
    Valida que o caminho aponta para um arquivo regular acessivel.
    Rejeita caminhos com componentes suspeitos (path traversal).
    Retorna o caminho absoluto resolvido ou None se invalido.
    """
    if not caminho:
        return None
    abs_caminho = os.path.realpath(caminho)
    if not os.path.isfile(abs_caminho):
        logging.getLogger(__name__).error(
            "Arquivo %s nao encontrado ou nao e um arquivo regular: %s", descricao, caminho
        )
        return None
    if not os.access(abs_caminho, os.R_OK):
        logging.getLogger(__name__).error(
            "Sem permissao de leitura no arquivo %s: %s", descricao, caminho
        )
        return None
    return abs_caminho


def _sanitizar_nome_arquivo(texto: str) -> str:
    """
    Remove caracteres invalidos para nomes de arquivo em Windows e Linux.
    Impede path traversal no nome base gerado a partir de dados do usuario.
    """
    import re
    # Remove caracteres invalidos e componentes de caminho
    texto = os.path.basename(texto)  # Remove qualquer separador de diretorio
    texto = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", texto)
    texto = texto.strip(". ")  # Remove pontos e espacos no inicio/fim
    return texto[:60] or "empresa"


def executar_auditoria(
    caminho_ecd: str | None,
    caminho_ecf: str | None,
    caminho_efd: str | None,
    dir_saida: str,
    limite_valor_gatilho: float = 0.0,
    amostra_gatilho: int = 50,
    gerar_xlsx: bool = False,
    gerar_pdf: bool = False,
) -> dict:
    """
    Executa o pipeline completo de auditoria.

    Returns:
        Dicionario com achados das regras e dos gatilhos.
    """
    logger = logging.getLogger(__name__)

    if not caminho_ecd and not caminho_ecf:
        logger.error("Pelo menos um arquivo (ECD ou ECF) deve ser informado.")
        sys.exit(1)

    # Validacao de seguranca: resolve caminhos reais para evitar path traversal
    caminho_ecd = _validar_arquivo_entrada(caminho_ecd, "ECD")
    caminho_ecf = _validar_arquivo_entrada(caminho_ecf, "ECF")
    caminho_efd = _validar_arquivo_entrada(caminho_efd, "EFD-Contribuicoes")

    # Valida diretorio de saida: resolve e cria de forma segura
    dir_saida = os.path.realpath(dir_saida)

    # === 1. PARSING ===
    dados_ecd: DadosECD | None = None
    dados_ecf: DadosECF | None = None
    dados_efd: DadosEFDContrib | None = None

    if caminho_ecd:
        logger.info("Parseando ECD: %s", caminho_ecd)
        dados_ecd = parse_ecd(caminho_ecd)

    if caminho_ecf:
        logger.info("Parseando ECF: %s", caminho_ecf)
        dados_ecf = parse_ecf(caminho_ecf)

    if caminho_efd:
        logger.info("Parseando EFD-Contribuicoes: %s", caminho_efd)
        dados_efd = parse_efd_contrib(caminho_efd)

    # === 2. MAPEAMENTO ===
    mapa_contas = {}
    if dados_ecd:
        mapa_contas = dados_ecd.mapeamento_referencial
        logger.info("Mapeamento referencial: %d contas", len(mapa_contas))

    # === 3. REGRAS DE AUDITORIA ===
    todos_achados: list[Achado] = []
    for regra in REGRAS:
        logger.info("Executando regra %s: %s", regra.codigo, regra.nome)
        try:
            achados = regra.executar(dados_ecd, dados_ecf, mapa_contas)
            todos_achados.extend(achados)
            logger.info("  %d achado(s)", len(achados))
        except Exception as e:
            logger.error("Erro na regra %s: %s", regra.codigo, e, exc_info=True)

    # === 4. GATILHOS ===
    gatilhos_conta: list[AchadoGatilho] = []
    gatilhos_historico: list[AchadoGatilho] = []

    if dados_ecd:
        logger.info("Executando gatilhos de conta...")
        gatilhos_conta = executar_gatilhos_conta(
            dados_ecd.plano_contas,
            dados_ecd.saldos,
        )

        logger.info("Executando gatilhos de historico...")
        gatilhos_historico = executar_gatilhos_historico(
            dados_ecd.partidas,
            dados_ecd.plano_contas,
            limite_valor=limite_valor_gatilho,
            amostra_max=amostra_gatilho,
        )

    todos_gatilhos = gatilhos_conta + gatilhos_historico

    # === 5. IDENTIFICACAO DA EMPRESA ===
    # ECD e considerada fonte primaria (leiaute fixo e mais confiavel)
    _empresa = (dados_ecd.razao_social if dados_ecd else "") or (dados_ecf.razao_social if dados_ecf else "")
    _cnpj = (dados_ecd.cnpj if dados_ecd else "") or (dados_ecf.cnpj if dados_ecf else "")
    if dados_ecd and dados_ecd.dt_ini:
        _periodo = f"{dados_ecd.dt_ini} a {dados_ecd.dt_fin}"
    elif dados_ecf and dados_ecf.dt_ini:
        _periodo = f"{dados_ecf.dt_ini} a {dados_ecf.dt_fin}"
    else:
        _periodo = ""

    # === 6. RESUMO ===
    os.makedirs(dir_saida, exist_ok=True)

    logger.info("=" * 70)
    logger.info("AUDITORIA CONCLUIDA")
    logger.info("=" * 70)
    logger.info("Empresa: %s | CNPJ: %s | Periodo: %s", _empresa, _cnpj, _periodo)

    # Regras
    valor_regras = sum(a.valor_estimado for a in todos_achados)
    logger.info("REGRAS: %d achados | Valor estimado: R$ %s", len(todos_achados), f"{valor_regras:,.2f}")
    for a in todos_achados:
        logger.info("  [%s] %s | R$ %s | %s", a.regra, a.titulo, f"{a.valor_estimado:,.2f}", a.confianca)

    # Gatilhos
    resumo = resumo_gatilhos(todos_gatilhos)
    logger.info(
        "GATILHOS: %d disparados | alta=%d, media=%d, baixa=%d",
        resumo["total"],
        resumo["por_severidade"]["alta"],
        resumo["por_severidade"]["media"],
        resumo["por_severidade"]["baixa"],
    )
    for cod, qtd in sorted(resumo["por_gatilho"].items()):
        logger.info("  %s: %d ocorrencias", cod, qtd)

    # === 7. MONTAR RESULTADO ===
    resultado = {
        "empresa": _empresa,
        "cnpj": _cnpj,
        "periodo": _periodo,
        "regras": {
            "total_achados": len(todos_achados),
            "valor_estimado": valor_regras,
            "achados": [
                {
                    "regra": a.regra,
                    "titulo": a.titulo,
                    "descricao": a.descricao,
                    "valor_estimado": a.valor_estimado,
                    "tributo": a.tributo,
                    "base_legal": a.base_legal,
                    "confianca": a.confianca,
                    "registros_origem": a.registros_origem,
                    "recomendacao": a.recomendacao,
                    "risco": a.risco,
                }
                for a in todos_achados
            ],
        },
        "gatilhos": {
            "total": resumo["total"],
            "resumo": resumo,
            "achados": [
                {
                    "gatilho": g.gatilho,
                    "tipo": g.tipo,
                    "categoria": g.categoria,
                    "severidade": g.severidade,
                    "descricao": g.descricao,
                    "conta": f"{g.cod_conta} - {g.nome_conta}",
                    "historico": g.historico,
                    "valor": g.valor,
                    "data": g.data,
                    "justificativa": g.justificativa,
                    "acao": g.acao,
                }
                for g in todos_gatilhos
            ],
        },
    }

    # === 8. SALVAR JSON ===
    caminho_json = os.path.join(dir_saida, "auditoria.json")
    with open(caminho_json, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2, default=str)
    logger.info("Resultado JSON salvo em: %s", caminho_json)

    # === 9. RELATORIO EXCEL ===
    if gerar_xlsx:
        try:
            from src.relatorios.gerador_xlsx import gerar_xlsx as _gerar_xlsx
            nome_base = _sanitizar_nome_arquivo(_empresa or "auditoria")
            nome_arq = f"auditoria_{nome_base}.xlsx".replace(" ", "_")
            # Garante que o arquivo fica DENTRO do diretorio de saida (sem path traversal)
            caminho_xlsx = os.path.join(dir_saida, os.path.basename(nome_arq))
            _gerar_xlsx(resultado, caminho_xlsx)
            logger.info("Relatorio Excel salvo em: %s", caminho_xlsx)
        except Exception as e:
            logger.error("Erro ao gerar relatorio Excel: %s", e, exc_info=True)

    # === 10. RELATORIO PDF ===
    if gerar_pdf:
        try:
            from src.relatorios.gerador_pdf import gerar_pdf as _gerar_pdf
            nome_base = _sanitizar_nome_arquivo(_empresa or "auditoria")
            nome_arq = f"parecer_{nome_base}.pdf".replace(" ", "_")
            caminho_pdf = os.path.join(dir_saida, os.path.basename(nome_arq))
            _gerar_pdf(resultado, caminho_pdf)
            logger.info("Parecer tecnico PDF salvo em: %s", caminho_pdf)
        except Exception as e:
            logger.error("Erro ao gerar relatorio PDF: %s", e, exc_info=True)

    return resultado


def main():
    parser = argparse.ArgumentParser(description="Auditor SPED - Auditoria ECF/ECD/EFD-Contribuicoes")
    parser.add_argument("--ecd", help="Caminho do arquivo ECD (.txt)", default=None)
    parser.add_argument("--ecf", help="Caminho do arquivo ECF (.txt)", default=None)
    parser.add_argument("--efd", help="Caminho do arquivo EFD-Contribuicoes (.txt)", default=None)
    parser.add_argument("--saida", help="Diretorio de saida", default="./resultado")
    parser.add_argument("--verbose", "-v", action="store_true", help="Modo verboso")
    parser.add_argument("--limite-valor", type=float, default=0.0,
                        help="Valor minimo para gatilhos de historico")
    parser.add_argument("--amostra-gatilho", type=int, default=50,
                        help="Maximo de achados por gatilho de historico (0=ilimitado)")
    parser.add_argument("--xlsx", action="store_true", help="Gerar relatorio Excel (.xlsx)")
    parser.add_argument("--pdf", action="store_true", help="Gerar parecer tecnico PDF")
    args = parser.parse_args()

    configurar_logging(args.verbose)
    executar_auditoria(
        args.ecd, args.ecf, args.efd,
        args.saida,
        args.limite_valor,
        args.amostra_gatilho,
        gerar_xlsx=args.xlsx,
        gerar_pdf=args.pdf,
    )


if __name__ == "__main__":
    main()
