"""Gerador de Parecer Tecnico em PDF para o Auditor SPED.

Estrutura do documento:
  1. Capa: identificacao, periodo, classificacao
  2. Sumario executivo: valor total, achados por tributo
  3. Metodologia: descricao do processo de auditoria
  4. Achados por regra: detalhamento com base legal
  5. Gatilhos relevantes: contas e historicos de alta severidade
  6. Recomendacoes: plano de acao consolidado
  7. Ressalvas: limitacoes e alertas

Uso:
  from src.relatorios.gerador_pdf import gerar_pdf
  gerar_pdf(resultado_dict, caminho_saida)
"""

import logging
from datetime import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors as _rl_colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, PageBreak, KeepTogether,
    )
    _reportlab_ok = True

    # Paleta de cores (so definida se reportlab estiver disponivel)
    _AZUL_ESCURO = _rl_colors.HexColor("#1F3864")
    _AZUL_MEDIO = _rl_colors.HexColor("#2E75B6")
    _AZUL_CLARO = _rl_colors.HexColor("#DEEAF1")
    _VERMELHO = _rl_colors.HexColor("#C00000")
    _LARANJA = _rl_colors.HexColor("#ED7D31")
    _VERDE = _rl_colors.HexColor("#70AD47")
    _CINZA_CLARO = _rl_colors.HexColor("#F2F2F2")
    _CINZA = _rl_colors.HexColor("#767171")
    colors = _rl_colors

except ImportError:
    _reportlab_ok = False

logger = logging.getLogger(__name__)


def gerar_pdf(resultado: dict, caminho_saida: str) -> str:
    """
    Gera Parecer Tecnico em PDF com os resultados da auditoria.

    Args:
        resultado: dicionario com dados da auditoria
        caminho_saida: caminho completo do arquivo .pdf a gerar

    Returns:
        Caminho do arquivo gerado.
    """
    if not _reportlab_ok:
        logger.error("reportlab nao instalado. Execute: pip install reportlab")
        raise ImportError("reportlab e necessario para gerar o PDF.")

    empresa = resultado.get("empresa", "Empresa nao identificada")
    cnpj = resultado.get("cnpj", "")
    periodo = resultado.get("periodo", "")
    achados = resultado.get("regras", {}).get("achados", [])
    valor_total = resultado.get("regras", {}).get("valor_estimado", 0.0)
    gatilhos = resultado.get("gatilhos", {}).get("achados", [])
    resumo_gat = resultado.get("gatilhos", {}).get("resumo", {})

    doc = SimpleDocTemplate(
        caminho_saida,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2 * cm,
        title=f"Parecer Tecnico - Auditoria SPED - {empresa}",
        author="Auditor SPED v1.0",
        subject="Auditoria de Creditos Tributarios - Lucro Real",
    )

    estilos = _criar_estilos()
    elementos = []

    _adicionar_capa(elementos, estilos, empresa, cnpj, periodo)
    _adicionar_sumario_executivo(elementos, estilos, achados, valor_total, resumo_gat)
    _adicionar_metodologia(elementos, estilos)
    _adicionar_achados(elementos, estilos, achados)
    _adicionar_gatilhos(elementos, estilos, gatilhos)
    _adicionar_recomendacoes(elementos, estilos, achados)
    _adicionar_ressalvas(elementos, estilos)

    doc.build(elementos, onFirstPage=_rodape, onLaterPages=_rodape)
    logger.info("Parecer tecnico PDF salvo em: %s", caminho_saida)
    return caminho_saida


# ============================================================
# ESTILOS
# ============================================================

def _criar_estilos() -> dict:
    base = getSampleStyleSheet()
    return {
        "titulo_capa": ParagraphStyle(
            "titulo_capa", parent=base["Heading1"],
            fontSize=20, textColor=colors.white,
            alignment=TA_CENTER, spaceAfter=6,
        ),
        "subtitulo_capa": ParagraphStyle(
            "subtitulo_capa", parent=base["Normal"],
            fontSize=12, textColor=colors.white,
            alignment=TA_CENTER, spaceAfter=4,
        ),
        "titulo_secao": ParagraphStyle(
            "titulo_secao", parent=base["Heading2"],
            fontSize=13, textColor=_AZUL_ESCURO,
            spaceBefore=14, spaceAfter=6,
            borderPad=4,
        ),
        "titulo_subsecao": ParagraphStyle(
            "titulo_subsecao", parent=base["Heading3"],
            fontSize=11, textColor=_AZUL_MEDIO,
            spaceBefore=10, spaceAfter=4,
        ),
        "corpo": ParagraphStyle(
            "corpo", parent=base["Normal"],
            fontSize=9, leading=14,
            alignment=TA_JUSTIFY, spaceAfter=4,
        ),
        "corpo_negrito": ParagraphStyle(
            "corpo_negrito", parent=base["Normal"],
            fontSize=9, leading=14, fontName="Helvetica-Bold",
        ),
        "item_lista": ParagraphStyle(
            "item_lista", parent=base["Normal"],
            fontSize=9, leading=13,
            leftIndent=12, spaceAfter=2,
        ),
        "valor_destaque": ParagraphStyle(
            "valor_destaque", parent=base["Normal"],
            fontSize=14, fontName="Helvetica-Bold",
            textColor=_VERMELHO, alignment=TA_CENTER,
        ),
        "alerta": ParagraphStyle(
            "alerta", parent=base["Normal"],
            fontSize=8, leading=12,
            textColor=_CINZA, alignment=TA_JUSTIFY,
            borderPad=6, leftIndent=6,
        ),
    }


# ============================================================
# CAPA
# ============================================================

def _adicionar_capa(elementos, estilos, empresa, cnpj, periodo):
    # Fundo azul na capa via tabela
    dados_capa = [
        [Paragraph("PARECER TECNICO", estilos["titulo_capa"])],
        [Paragraph("AUDITORIA DE CREDITOS TRIBUTARIOS", estilos["subtitulo_capa"])],
        [Paragraph("Lucro Real - IRPJ / CSLL / PIS / COFINS", estilos["subtitulo_capa"])],
        [Spacer(1, 0.5 * cm)],
        [Paragraph(empresa, estilos["subtitulo_capa"])],
        [Paragraph(f"CNPJ: {cnpj}", estilos["subtitulo_capa"])],
        [Paragraph(f"Periodo: {periodo}", estilos["subtitulo_capa"])],
        [Spacer(1, 0.5 * cm)],
        [Paragraph(f"Emitido em: {datetime.now().strftime('%d/%m/%Y')}", estilos["subtitulo_capa"])],
    ]

    tabela_capa = Table(dados_capa, colWidths=[17 * cm])
    tabela_capa.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _AZUL_ESCURO),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [5]),
    ]))
    elementos.append(tabela_capa)
    elementos.append(Spacer(1, 1 * cm))
    elementos.append(PageBreak())


# ============================================================
# SUMARIO EXECUTIVO
# ============================================================

def _adicionar_sumario_executivo(elementos, estilos, achados, valor_total, resumo_gat):
    elementos.append(Paragraph("1. SUMARIO EXECUTIVO", estilos["titulo_secao"]))
    elementos.append(HRFlowable(width="100%", color=_AZUL_MEDIO, thickness=1))
    elementos.append(Spacer(1, 0.3 * cm))

    # Valor destaque
    elementos.append(Paragraph(
        f"Credito Tributario Total Estimado: R$ {valor_total:,.2f}",
        estilos["valor_destaque"],
    ))
    elementos.append(Spacer(1, 0.3 * cm))

    # Tabela resumo por tributo
    total_por_tributo: dict[str, float] = {}
    total_por_conf: dict[str, int] = {"alta": 0, "media": 0, "baixa": 0}
    for a in achados:
        trib = a.get("tributo", "Outros")
        total_por_tributo[trib] = total_por_tributo.get(trib, 0) + a.get("valor_estimado", 0)
        conf = a.get("confianca", "baixa")
        total_por_conf[conf] = total_por_conf.get(conf, 0) + 1

    dados_tab = [["Tributo", "Valor Estimado (R$)", "Achados"]]
    conf_por_trib: dict[str, int] = {}
    for a in achados:
        trib = a.get("tributo", "Outros")
        conf_por_trib[trib] = conf_por_trib.get(trib, 0) + 1

    for trib, val in sorted(total_por_tributo.items(), key=lambda x: -x[1]):
        dados_tab.append([trib, f"R$ {val:,.2f}", str(conf_por_trib.get(trib, 0))])

    dados_tab.append(["TOTAL", f"R$ {valor_total:,.2f}", str(len(achados))])

    tab = _tabela_padrao(dados_tab, [6 * cm, 6 * cm, 3 * cm], cabecalho=True)
    elementos.append(tab)
    elementos.append(Spacer(1, 0.5 * cm))

    # Confianca
    elementos.append(Paragraph(
        f"Achados por grau de confianca: "
        f"Alta = {total_por_conf['alta']} | Media = {total_por_conf['media']} | Baixa = {total_por_conf['baixa']}",
        estilos["corpo"],
    ))

    # Gatilhos
    por_sev = resumo_gat.get("por_severidade", {})
    elementos.append(Paragraph(
        f"Gatilhos disparados: {resumo_gat.get('total', 0)} total | "
        f"Alta severidade: {por_sev.get('alta', 0)} | "
        f"Media: {por_sev.get('media', 0)} | Baixa: {por_sev.get('baixa', 0)}",
        estilos["corpo"],
    ))
    elementos.append(Spacer(1, 0.5 * cm))


# ============================================================
# METODOLOGIA
# ============================================================

def _adicionar_metodologia(elementos, estilos):
    elementos.append(Paragraph("2. METODOLOGIA", estilos["titulo_secao"]))
    elementos.append(HRFlowable(width="100%", color=_AZUL_MEDIO, thickness=1))
    elementos.append(Spacer(1, 0.3 * cm))

    texto_met = (
        "A auditoria foi realizada por meio de sistema automatizado de leitura e analise "
        "de arquivos digitais do SPED (Sistema Publico de Escrituração Digital), utilizando "
        "os seguintes modulos:\n"
    )
    elementos.append(Paragraph(texto_met, estilos["corpo"]))

    modulos = [
        "ECD (Escrituração Contabil Digital): analise do plano de contas, saldos periódicos (I155), "
        "lancamentos (I200) e partidas (I250);",
        "ECF (Escrituração Contabil Fiscal): analise dos registros de apuracao de IRPJ (N630), "
        "CSLL (N670), estimativas mensais (N620), LALUR Parte A (M300), IRRF (Y570) e PER/DCOMP (Y580);",
        "EFD-Contribuicoes: analise dos creditos de PIS/COFINS (M100/M500), contribuicao devida "
        "(M200/M600), controle de creditos fiscais (1100/1500) e retencoes (F600).",
    ]
    for m in modulos:
        elementos.append(Paragraph(f"   * {m}", estilos["item_lista"]))

    elementos.append(Spacer(1, 0.3 * cm))
    elementos.append(Paragraph(
        "O sistema aplica 10 regras de auditoria baseadas na legislacao tributaria vigente e "
        "22 gatilhos automaticos de identificacao de padroes em contas e historicos contabeis. "
        "Achados de baixa confianca sao sinalizados como hipotese e requerem confirmacao documental.",
        estilos["corpo"],
    ))
    elementos.append(Spacer(1, 0.5 * cm))


# ============================================================
# ACHADOS
# ============================================================

def _adicionar_achados(elementos, estilos, achados):
    elementos.append(Paragraph("3. ACHADOS DA AUDITORIA", estilos["titulo_secao"]))
    elementos.append(HRFlowable(width="100%", color=_AZUL_MEDIO, thickness=1))
    elementos.append(Spacer(1, 0.3 * cm))

    if not achados:
        elementos.append(Paragraph("Nenhum achado identificado.", estilos["corpo"]))
        return

    for i, a in enumerate(achados, start=1):
        conf = a.get("confianca", "baixa")
        cor_conf = _VERMELHO if conf == "alta" else (_LARANJA if conf == "media" else _VERDE)
        valor = a.get("valor_estimado", 0.0)

        bloco = []

        # Titulo do achado
        titulo_txt = (
            f"<font color='#{_hex_color(cor_conf)}'><b>{a.get('regra','')} - {a.get('titulo','')}</b></font>"
        )
        bloco.append(Paragraph(titulo_txt, estilos["titulo_subsecao"]))

        # Tabela de metadados
        dados_meta = [
            ["Tributo", a.get("tributo", ""), "Confianca", conf.upper()],
            ["Base Legal", a.get("base_legal", ""), "Valor Estimado", f"R$ {valor:,.2f}"],
        ]
        tab_meta = Table(dados_meta, colWidths=[3 * cm, 7 * cm, 3 * cm, 4 * cm])
        tab_meta.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), _AZUL_CLARO),
            ("BACKGROUND", (2, 0), (2, -1), _AZUL_CLARO),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ]))
        bloco.append(tab_meta)
        bloco.append(Spacer(1, 0.15 * cm))

        # Descricao
        bloco.append(Paragraph("<b>Descricao:</b>", estilos["corpo_negrito"]))
        bloco.append(Paragraph(a.get("descricao", ""), estilos["corpo"]))
        bloco.append(Spacer(1, 0.1 * cm))

        # Registros de origem
        regs = a.get("registros_origem", [])
        if regs:
            bloco.append(Paragraph("<b>Registros de Origem:</b>", estilos["corpo_negrito"]))
            for reg in regs[:8]:  # Limita a 8 registros no PDF
                bloco.append(Paragraph(f"   {reg}", estilos["item_lista"]))

        # Recomendacao
        bloco.append(Spacer(1, 0.1 * cm))
        bloco.append(Paragraph("<b>Recomendacao:</b>", estilos["corpo_negrito"]))
        bloco.append(Paragraph(a.get("recomendacao", ""), estilos["corpo"]))

        # Risco
        if a.get("risco"):
            bloco.append(Paragraph(f"<i>Risco/Observacao: {a.get('risco','')}</i>", estilos["alerta"]))

        bloco.append(HRFlowable(width="100%", color=_CINZA_CLARO, thickness=0.5, spaceAfter=8))

        elementos.append(KeepTogether(bloco))

    elementos.append(PageBreak())


# ============================================================
# GATILHOS
# ============================================================

def _adicionar_gatilhos(elementos, estilos, gatilhos):
    elementos.append(Paragraph("4. GATILHOS RELEVANTES", estilos["titulo_secao"]))
    elementos.append(HRFlowable(width="100%", color=_AZUL_MEDIO, thickness=1))
    elementos.append(Spacer(1, 0.3 * cm))

    elementos.append(Paragraph(
        "Os gatilhos identificam padroes em nomes de contas e historicos de lancamentos "
        "que merecem atencao especial do auditor. Abaixo os de alta severidade.",
        estilos["corpo"],
    ))
    elementos.append(Spacer(1, 0.3 * cm))

    alta = [g for g in gatilhos if g.get("severidade") == "alta"]
    if not alta:
        elementos.append(Paragraph("Nenhum gatilho de alta severidade.", estilos["corpo"]))
        return

    dados_gat = [["Gatilho", "Tipo", "Conta/Contexto", "Valor (R$)", "Acao"]]
    for g in alta[:30]:  # Limita a 30 no PDF
        dados_gat.append([
            g.get("gatilho", ""),
            g.get("tipo", "").capitalize(),
            g.get("conta", "")[:35],
            f"R$ {g.get('valor',0):,.2f}",
            g.get("acao", "")[:60],
        ])

    tab_gat = _tabela_padrao(dados_gat, [2*cm, 2*cm, 5*cm, 3*cm, 5*cm], cabecalho=True)
    elementos.append(tab_gat)
    elementos.append(Spacer(1, 0.5 * cm))


# ============================================================
# RECOMENDACOES
# ============================================================

def _adicionar_recomendacoes(elementos, estilos, achados):
    elementos.append(PageBreak())
    elementos.append(Paragraph("5. PLANO DE ACAO E RECOMENDACOES", estilos["titulo_secao"]))
    elementos.append(HRFlowable(width="100%", color=_AZUL_MEDIO, thickness=1))
    elementos.append(Spacer(1, 0.3 * cm))

    elementos.append(Paragraph(
        "Com base nos achados desta auditoria, recomenda-se o seguinte plano de acao, "
        "priorizando os itens de maior valor e confianca:",
        estilos["corpo"],
    ))
    elementos.append(Spacer(1, 0.2 * cm))

    alta_conf = [a for a in achados if a.get("confianca") == "alta"]
    media_conf = [a for a in achados if a.get("confianca") == "media"]

    if alta_conf:
        elementos.append(Paragraph("ACOES IMEDIATAS (Alta Confianca):", estilos["titulo_subsecao"]))
        for a in alta_conf:
            elementos.append(Paragraph(
                f"   [{a.get('regra','')}] {a.get('titulo','')} (R$ {a.get('valor_estimado',0):,.2f}): "
                f"{a.get('recomendacao','')[:200]}",
                estilos["item_lista"],
            ))
        elementos.append(Spacer(1, 0.3 * cm))

    if media_conf:
        elementos.append(Paragraph("ACOES RECOMENDADAS (Media Confianca - requerem verificacao):", estilos["titulo_subsecao"]))
        for a in media_conf:
            elementos.append(Paragraph(
                f"   [{a.get('regra','')}] {a.get('titulo','')} (R$ {a.get('valor_estimado',0):,.2f}): "
                f"{a.get('recomendacao','')[:200]}",
                estilos["item_lista"],
            ))

    elementos.append(Spacer(1, 0.5 * cm))


# ============================================================
# RESSALVAS
# ============================================================

def _adicionar_ressalvas(elementos, estilos):
    elementos.append(Paragraph("6. RESSALVAS E LIMITACOES", estilos["titulo_secao"]))
    elementos.append(HRFlowable(width="100%", color=_AZUL_MEDIO, thickness=1))
    elementos.append(Spacer(1, 0.3 * cm))

    ressalvas = [
        "Este relatorio foi gerado por sistema automatizado de analise de arquivos SPED. "
        "Os valores sao estimados e devem ser confirmados com documentacao fiscal e contabil.",
        "Achados de media e baixa confianca sao hipoteses que requerem analise documental "
        "aprofundada antes de qualquer acao perante a Receita Federal do Brasil.",
        "A transmissao de PER/DCOMP sem a devida confirmacao dos creditos pode resultar "
        "em autuacao por compensacao indevida (multa de 75% a 150%).",
        "Este relatorio nao constitui opiniao juridica ou assessoria tributaria formal. "
        "Recomenda-se consulta a especialista tributarista antes de qualquer acao.",
        "Os dados analisados sao os informados pelo contribuinte nos arquivos SPED. "
        "O sistema nao verifica a veracidade das informacoes declaradas.",
        "Prescricao: o direito a restituicao ou compensacao extingue-se em 5 anos "
        "contados da data de pagamento indevido (art. 168, CTN).",
    ]
    for r in ressalvas:
        elementos.append(Paragraph(f"   * {r}", estilos["alerta"]))

    elementos.append(Spacer(1, 1 * cm))
    elementos.append(Paragraph(
        f"Relatorio gerado em {datetime.now().strftime('%d/%m/%Y as %H:%M')} "
        "pelo Sistema Auditor SPED v1.0.",
        ParagraphStyle("rodape_final", parent=getSampleStyleSheet()["Normal"],
                       fontSize=8, textColor=_CINZA, alignment=TA_CENTER),
    ))


# ============================================================
# UTILITARIOS
# ============================================================

def _tabela_padrao(dados, larguras, cabecalho: bool = False):
    """Cria tabela com formatacao padrao."""
    tab = Table(dados, colWidths=larguras, repeatRows=1 if cabecalho else 0)
    estilo = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1 if cabecalho else 0), (-1, -1), [colors.white, _CINZA_CLARO]),
    ]
    if cabecalho:
        estilo += [
            ("BACKGROUND", (0, 0), (-1, 0), _AZUL_MEDIO),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    tab.setStyle(TableStyle(estilo))
    return tab


def _hex_color(color_obj) -> str:
    """Converte objeto Color do reportlab para hex sem #."""
    try:
        return color_obj.hexval()[1:]
    except Exception:
        return "000000"


def _rodape(canvas, doc):
    """Adiciona rodape em todas as paginas."""
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(_CINZA)
    canvas.drawString(2 * cm, 1.2 * cm, "Auditor SPED - Sistema de Auditoria Tributaria")
    canvas.drawRightString(
        A4[0] - 2 * cm, 1.2 * cm,
        f"Pagina {doc.page} | CONFIDENCIAL"
    )
    canvas.line(2 * cm, 1.5 * cm, A4[0] - 2 * cm, 1.5 * cm)
    canvas.restoreState()
