"""Configurações globais do Auditor SPED."""

import logging

# Encoding padrão dos arquivos SPED
ENCODING_PRIMARIO = "iso-8859-1"
ENCODING_FALLBACK = "utf-8"

# Separador de campos SPED
SEPARADOR = "|"

# Logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_LEVEL = logging.INFO

# Registros ECD de interesse (I = escrituração corrente, C = recuperação da anterior)
REGISTROS_ECD = [
    "0000",
    # Bloco C (recuperação ECD anterior)
    "C040", "C050", "C051", "C052", "C150", "C155", "C650",
    # Bloco I (escrituração corrente)
    "I010", "I050", "I051", "I052", "I150", "I155", "I200", "I250", "I355",
    # Bloco J (demonstrações)
    "J005", "J100", "J150", "J215",
]

# Registros ECF de interesse
REGISTROS_ECF = [
    "0000", "0010", "0020", "0030",
    # Bloco C/E (recuperação ECD)
    "C050", "C051", "C155", "E010", "E015", "E155", "E355",
    # Bloco J (plano de contas)
    "J050", "J051",
    # Bloco K (saldos referenciais)
    "K155", "K156", "K355", "K356",
    # Bloco L (lucro líquido)
    "L100", "L200", "L210", "L300",
    # Bloco M (LALUR/LACS)
    "M010", "M300", "M310", "M350", "M360", "M410", "M500",
    # Bloco N (cálculo IRPJ/CSLL)
    "N500", "N600", "N610", "N620", "N630", "N650", "N660", "N670",
    # Bloco Y (informações complementares)
    "Y570", "Y580", "Y600", "Y612", "Y750",
]

# Registros EFD-Contribuições de interesse
REGISTROS_EFD_CONTRIB = [
    "0000", "0100", "0110", "0140", "0150", "0190", "0200", "0400", "0450", "0500", "0600",
    # Bloco A (serviços)
    "A010", "A100", "A170",
    # Bloco C (mercadorias)
    "C010", "C100", "C170", "C175", "C180", "C181", "C185", "C188", "C190", "C191", "C195", "C198",
    "C380", "C381", "C385", "C500", "C501", "C505",
    # Bloco D (transporte/comunicação)
    "D010", "D100", "D101", "D105", "D200", "D201", "D205", "D500", "D501", "D505",
    # Bloco F (demais documentos/operações)
    "F010", "F100", "F120", "F130", "F150", "F200", "F205", "F210", "F500", "F509", "F510", "F519",
    "F525", "F550", "F559", "F560", "F569", "F600",
    # Bloco M (apuração PIS/COFINS)
    "M001", "M100", "M105", "M110", "M115",
    "M200", "M205", "M210", "M211",
    "M300", "M350",
    "M400", "M410",
    "M500", "M505", "M510", "M515",
    "M600", "M605", "M610", "M611",
    "M700", "M800", "M810",
    # Bloco 1 (complemento)
    "1001", "1010", "1011", "1100", "1500", "1600", "1700",
]


# ============================================================
# ESTRUTURA DOS REGISTROS - CALIBRADA COM ARQUIVOS REAIS
# ============================================================

# ECD I050: Plano de contas da empresa
# |I050|DT_ALT|COD_NAT|IND_CTA|NIVEL|COD_CTA|COD_CTA_SUP|CTA|
I050_CAMPOS = {
    "dt_alt": 1,
    "cod_nat": 2,       # 01=Ativo, 02=Passivo, 03=PL, 04=Resultado, 05=Compensação
    "ind_cta": 3,        # S=Sintética, A=Analítica
    "nivel": 4,
    "cod_cta": 5,
    "cod_cta_sup": 6,
    "nome": 7,
}

# ECD I051: Plano de contas referencial
# |I051|COD_PLAN_REF|COD_CTA_REF|
# Aparece logo após o I050 (A) correspondente
I051_CAMPOS = {
    "cod_plan_ref": 1,   # Geralmente vazio
    "cod_cta_ref": 2,    # Ex: "1.01.01.01.01"
}

# ECD I155: Saldos periódicos
# |I155|COD_CTA|COD_CCUS|VL_SLD_INI|IND_DC_INI|VL_DEB|VL_CRED|VL_SLD_FIN|IND_DC_FIN|
I155_CAMPOS = {
    "cod_cta": 1,
    "cod_ccus": 2,
    "vl_sld_ini": 3,
    "ind_dc_ini": 4,     # D=Devedor, C=Credor
    "vl_deb": 5,
    "vl_cred": 6,
    "vl_sld_fin": 7,
    "ind_dc_fin": 8,
}

# ECD I200: Lançamento contábil
# |I200|NUM_LCTO|DT_LCTO|VL_LCTO|IND_LCTO|DT_LCTO_EXT|
I200_CAMPOS = {
    "num_lcto": 1,
    "dt_lcto": 2,
    "vl_lcto": 3,
    "ind_lcto": 4,       # N=Normal, E=Encerramento, X=Extemporâneo
}

# ECD I250: Partidas do lançamento
# |I250|COD_CTA|COD_CCUS|VL_DC|IND_DC|NUM_ARQ|COD_HIST_PAD|HIST|COD_PART|
I250_CAMPOS = {
    "cod_cta": 1,
    "cod_ccus": 2,
    "vl_dc": 3,
    "ind_dc": 4,         # D=Débito, C=Crédito
    "num_arq": 5,
    "cod_hist_pad": 6,
    "hist": 7,           # Histórico do lançamento (CHAVE para gatilhos)
    "cod_part": 8,
}

# ECF N620/N630/N670: Formato real = |REGISTRO|LINHA|DESCRIÇÃO|VALOR|
# São registros tabulares onde LINHA é o identificador do campo
ECF_TABULAR_CAMPOS = {
    "linha": 1,
    "descricao": 2,
    "valor": 3,
}

# ECF Y570: Rendimentos com IRRF
# |Y570|CNPJ|NOME|IND_PART|COD_REC|VL_REC|VL_IR_RET|VL_IR_UTIL|
Y570_CAMPOS = {
    "cnpj": 1,
    "nome": 2,
    "ind_part": 3,
    "cod_rec": 4,
    "vl_rec": 5,
    "vl_ir_ret": 6,
    "vl_ir_util": 7,
}

# ECF Y580: PER/DCOMP
# |Y580|TIPO|PER_APUR|DCOMP_NUM|VL_CRED|
Y580_CAMPOS = {
    "tipo": 1,
    "per_apur": 2,
    "dcomp_num": 3,
    "vl_cred": 4,
}

# ECF Y600: Participações societárias
# |Y600|DT_ALT_SOC||COD_PAIS|TIP_PES|CPF_CNPJ|NOME|QUALIF|PERC_CAP_TOT|PERC_CAP_VOT|...|QTD_QUOT|VL_PAR|VL_REM|
Y600_CAMPOS = {
    "dt_alt_soc": 1,
    "cod_pais": 3,
    "tip_pes": 4,
    "cpf_cnpj": 5,
    "nome": 6,
    "qualif": 7,
    "perc_cap_tot": 8,
}

# ECF M300: LALUR Parte A
# |M300|CODIGO|IND_AD_EX|DESCRICAO|TP_LANCAMENTO|VL_LANCAMENTO|IND_RELACAO|
M300_CAMPOS = {
    "codigo": 1,
    "descricao": 2,
    "ind_ad_ex": 3,    # A=Adição, E=Exclusão, C=Compensação de prejuízo
    "tp_lancamento": 4,
    "vl_lancamento": 5,
}


# ============================================================
# LINHAS-CHAVE DOS REGISTROS TABULARES ECF
# ============================================================

# N630 (Resultado IRPJ - Ajuste Anual)
N630_LINHAS = {
    "base_calculo": "1",
    "aliquota_15": "3",
    "adicional": "4",
    "deducao_pat": "8",
    "deducao_crianca": "11",
    "deducao_idoso": "12",
    "irrf_retido": "20",
    "irrf_orgaos": "21",
    "irrf_demais_adm": "22",
    "ganhos_renda_var": "23",
    "estimativas_pagas": "24",
    "estimativas_parceladas": "25",
    "irpj_a_pagar": "26",
}

# N670 (Resultado CSLL - Ajuste Anual)
N670_LINHAS = {
    "base_calculo": "1",
    "csll_devida": "2",
    "total_csll": "4",
    "csll_retida_orgaos": "15",
    "csll_retida_demais_adm": "16",
    "csll_retida_pj": "17",
    "csll_retida_mun": "18",
    "estimativas_pagas": "19",
    "estimativas_parceladas": "20",
    "csll_a_pagar": "21",
}

# N620 (Estimativa mensal IRPJ)
N620_LINHAS = {
    "base_calculo": "1",
    "aliquota_15": "3",
    "adicional": "4",
    "deducao_pat": "9",
    "irrf_retido": "21",
    "irpj_devido_mes": "26",
}
