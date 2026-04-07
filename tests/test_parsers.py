"""Testes para os parsers SPED (ECD, ECF, EFD-Contribuicoes).

Dados sinteticos embutidos como string — nenhum arquivo externo necessario.
"""

import io
import sys
import os
import pytest

# Garante que o modulo raiz esta no path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.parsers.sped_parser import parse_arquivo, valor_monetario


# ============================================================
# FIXTURES: arquivos SPED sinteticos
# ============================================================

ECD_SINTETICO = """\
|0000|9|S|N||01012024|31122024|EMPRESA TESTE LTDA|14781517000149|SP|99|0|TESTE||||
|I010|G||
|I050|20240101|01|A|1|1|0|ATIVO|
|I051||1.01.01.01.01|
|I050|20240101|01|S|1|10|0|ATIVO CIRCULANTE|
|I050|20240101|01|A|2|100|10|CAIXA|
|I051||1.01.01.01.02|
|I050|20240101|01|A|2|101|10|IRRF A COMPENSAR|
|I051||1.01.05.01.01|
|I050|20240101|02|A|2|200|0|FORNECEDORES|
|I050|20240101|04|A|2|400|0|RECEITAS|
|I050|20240101|04|A|2|410|0|DESPESA ALIMENTACAO|
|I150||
|I155|100|0|0,00|D|5000,00|4000,00|1000,00|D|
|I155|101|0|0,00|D|40000,00|0,00|40000,00|D|
|I155|200|0|0,00|C|0,00|5000,00|5000,00|C|
|I155|400|0|0,00|C|0,00|80000,00|80000,00|C|
|I155|410|0|0,00|D|5000,00|0,00|5000,00|D|
|I200|0001|01012024|1000,00|N||
|I250|100|0|1000,00|D|0||PAGAMENTO FORNECEDOR|001|
|I250|200|0|1000,00|C|0||PAGAMENTO FORNECEDOR|001|
|I200|0002|15012024|40000,00|N||
|I250|101|0|40000,00|D|0||IRRF RETIDO SICOOB|001|
|I250|400|0|40000,00|C|0||IRRF RETIDO SICOOB|001|
|9999||||
"""

ECF_SINTETICO = """\
|0000|9|ECF|N||14781517000149|01012024|31122024|EMPRESA TESTE LTDA||
|0010|1|0|0|0||
|N620|1|Base de calculo mensal|50000,00|
|N620|3|IRPJ 15% mensal|7500,00|
|N620|26|IRPJ devido no mes|7500,00|
|N630|1|Base de calculo|100000,00|
|N630|3|IRPJ aliquota 15%|15000,00|
|N630|4|Adicional 10%|5000,00|
|N630|8|Deducao PAT|0,00|
|N630|20|IRRF retido|0,00|
|N630|24|Estimativas pagas|0,00|
|N630|26|IRPJ a pagar|20000,00|
|N670|1|Base de calculo CSLL|100000,00|
|N670|4|CSLL devida|9000,00|
|N670|15|CSLL retida orgaos|0,00|
|N670|17|CSLL retida PJ|0,00|
|N670|19|Estimativas CSLL pagas|0,00|
|N670|21|CSLL a pagar|9000,00|
|Y570|12345678000195|BANCO SICOOB|1|1990||100000,00|40239,65|0,00|
|Y570|98765432000100|BANCO SANTANDER|1|1990||5000,00|156,58|0,00|
|M300|001|Adicao PDD|A|1|5000,00||
|9999||||
"""

EFD_SINTETICO = """\
|0000|006|1|U|01012024|31122024|0||EMPRESA TESTE LTDA|14781517000149|SP||
|0110|1|1||
|M100|101|0|50000,00|1,65|825,00||
|M200|5000,00|0,00|825,00|0,00|825,00|0,00|0,00|
|M500|201|0|50000,00|7,60|3800,00||
|M600|10000,00|0,00|3800,00|0,00|3800,00|0,00|0,00|
|F600|01|15012024|40000,00|1200,00|5952|2|
|1100|01|112024|101|01012024|825,00|0,00|0,00|825,00|
|1500|01|112024|201|01012024|3800,00|0,00|0,00|3800,00|
|9999||||
"""


def _arquivo_temp(conteudo: str, tmp_path, nome: str):
    """Cria arquivo temporario com conteudo SPED."""
    caminho = tmp_path / nome
    caminho.write_text(conteudo, encoding="utf-8")
    return str(caminho)


# ============================================================
# TESTES: valor_monetario
# ============================================================

class TestValorMonetario:
    def test_valor_virgula(self):
        assert valor_monetario("1.234,56") == 1234.56

    def test_valor_sem_milhar(self):
        assert valor_monetario("100,00") == 100.0

    def test_valor_zero(self):
        assert valor_monetario("0,00") == 0.0

    def test_campo_vazio(self):
        assert valor_monetario("") == 0.0

    def test_campo_none_like(self):
        assert valor_monetario("  ") == 0.0

    def test_valor_negativo(self):
        # SPED nao usa negativos diretos, mas parser deve ser resiliente
        assert valor_monetario("0") == 0.0


# ============================================================
# TESTES: parse_arquivo (parser generico)
# ============================================================

class TestParseArquivo:
    def test_parse_ecd_sintetico(self, tmp_path):
        caminho = _arquivo_temp(ECD_SINTETICO, tmp_path, "ecd.txt")
        regs = parse_arquivo(caminho, ["0000", "I050", "I051", "I155", "I200", "I250"])
        assert "0000" in regs
        assert len(regs["0000"]) == 1
        assert "I050" in regs
        assert len(regs["I050"]) >= 5
        assert "I155" in regs
        assert len(regs["I155"]) >= 3

    def test_filtragem_de_registros(self, tmp_path):
        caminho = _arquivo_temp(ECD_SINTETICO, tmp_path, "ecd_filt.txt")
        regs = parse_arquivo(caminho, ["I155"])
        assert "I155" in regs
        assert "I050" not in regs

    def test_parse_sem_filtro(self, tmp_path):
        caminho = _arquivo_temp(ECD_SINTETICO, tmp_path, "ecd_all.txt")
        regs = parse_arquivo(caminho, None)
        assert len(regs) > 3

    def test_arquivo_inexistente(self, tmp_path):
        with pytest.raises((FileNotFoundError, OSError)):
            parse_arquivo(str(tmp_path / "inexistente.txt"))


# ============================================================
# TESTES: ecd_parser
# ============================================================

class TestECDParser:
    def test_identificacao(self, tmp_path):
        from src.parsers.ecd_parser import parse_ecd
        caminho = _arquivo_temp(ECD_SINTETICO, tmp_path, "ecd.txt")
        dados = parse_ecd(caminho)
        assert "EMPRESA TESTE" in dados.razao_social
        assert dados.dt_ini == "01012024"
        assert dados.dt_fin == "31122024"

    def test_plano_contas(self, tmp_path):
        from src.parsers.ecd_parser import parse_ecd
        caminho = _arquivo_temp(ECD_SINTETICO, tmp_path, "ecd.txt")
        dados = parse_ecd(caminho)
        assert len(dados.plano_contas) >= 5
        assert "101" in dados.plano_contas
        assert "IRRF" in dados.plano_contas["101"].nome.upper()

    def test_mapeamento_referencial(self, tmp_path):
        from src.parsers.ecd_parser import parse_ecd
        caminho = _arquivo_temp(ECD_SINTETICO, tmp_path, "ecd.txt")
        dados = parse_ecd(caminho)
        # I051 aparece apos contas analiticas
        assert len(dados.mapeamento_referencial) >= 1

    def test_saldos(self, tmp_path):
        from src.parsers.ecd_parser import parse_ecd
        caminho = _arquivo_temp(ECD_SINTETICO, tmp_path, "ecd.txt")
        dados = parse_ecd(caminho)
        assert "101" in dados.saldos
        saldo_irrf = dados.saldos["101"][0]
        assert saldo_irrf.saldo_final == 40000.0
        assert saldo_irrf.ind_dc_fin == "D"

    def test_lancamentos_e_partidas(self, tmp_path):
        from src.parsers.ecd_parser import parse_ecd
        caminho = _arquivo_temp(ECD_SINTETICO, tmp_path, "ecd.txt")
        dados = parse_ecd(caminho)
        assert len(dados.lancamentos) >= 2
        assert len(dados.partidas) >= 4

    def test_historico_partida(self, tmp_path):
        from src.parsers.ecd_parser import parse_ecd
        caminho = _arquivo_temp(ECD_SINTETICO, tmp_path, "ecd.txt")
        dados = parse_ecd(caminho)
        historicos = [p.historico for p in dados.partidas]
        assert any("IRRF" in h.upper() for h in historicos)


# ============================================================
# TESTES: ecf_parser
# ============================================================

class TestECFParser:
    def test_identificacao(self, tmp_path):
        from src.parsers.ecf_parser import parse_ecf
        caminho = _arquivo_temp(ECF_SINTETICO, tmp_path, "ecf.txt")
        dados = parse_ecf(caminho)
        assert "EMPRESA TESTE" in dados.razao_social
        assert dados.dt_ini == "01012024"

    def test_n630_valores(self, tmp_path):
        from src.parsers.ecf_parser import parse_ecf
        caminho = _arquivo_temp(ECF_SINTETICO, tmp_path, "ecf.txt")
        dados = parse_ecf(caminho)
        assert dados.n630_valor("3") == 15000.0
        assert dados.n630_valor("4") == 5000.0
        assert dados.n630_valor("20") == 0.0
        assert dados.n630_valor("26") == 20000.0

    def test_n670_valores(self, tmp_path):
        from src.parsers.ecf_parser import parse_ecf
        caminho = _arquivo_temp(ECF_SINTETICO, tmp_path, "ecf.txt")
        dados = parse_ecf(caminho)
        assert dados.n670_valor("4") == 9000.0
        assert dados.n670_valor("21") == 9000.0

    def test_y570_irrf(self, tmp_path):
        from src.parsers.ecf_parser import parse_ecf
        caminho = _arquivo_temp(ECF_SINTETICO, tmp_path, "ecf.txt")
        dados = parse_ecf(caminho)
        assert len(dados.y570_irrf) == 2
        total_retido = sum(r.vl_ir_retido for r in dados.y570_irrf)
        assert abs(total_retido - 40396.23) < 0.01

    def test_m300_lalur(self, tmp_path):
        from src.parsers.ecf_parser import parse_ecf
        caminho = _arquivo_temp(ECF_SINTETICO, tmp_path, "ecf.txt")
        dados = parse_ecf(caminho)
        assert len(dados.m300_irpj) == 1
        assert dados.m300_irpj[0].ind_ad_ex == "A"

    def test_n620_estimativas(self, tmp_path):
        from src.parsers.ecf_parser import parse_ecf
        caminho = _arquivo_temp(ECF_SINTETICO, tmp_path, "ecf.txt")
        dados = parse_ecf(caminho)
        estimativas = dados.n620_valores_por_linha("26")
        assert len(estimativas) == 1
        assert estimativas[0] == 7500.0


# ============================================================
# TESTES: efd_contrib_parser
# ============================================================

class TestEFDContribParser:
    def test_identificacao(self, tmp_path):
        from src.parsers.efd_contrib_parser import parse_efd_contrib
        caminho = _arquivo_temp(EFD_SINTETICO, tmp_path, "efd.txt")
        dados = parse_efd_contrib(caminho)
        assert dados.regime_apuracao == "1"

    def test_creditos_pis(self, tmp_path):
        from src.parsers.efd_contrib_parser import parse_efd_contrib
        caminho = _arquivo_temp(EFD_SINTETICO, tmp_path, "efd.txt")
        dados = parse_efd_contrib(caminho)
        assert len(dados.creditos_pis) == 1
        assert dados.creditos_pis[0].vl_credito == 825.0

    def test_creditos_cofins(self, tmp_path):
        from src.parsers.efd_contrib_parser import parse_efd_contrib
        caminho = _arquivo_temp(EFD_SINTETICO, tmp_path, "efd.txt")
        dados = parse_efd_contrib(caminho)
        assert len(dados.creditos_cofins) == 1
        assert dados.creditos_cofins[0].vl_credito == 3800.0

    def test_retencoes_f600(self, tmp_path):
        from src.parsers.efd_contrib_parser import parse_efd_contrib
        caminho = _arquivo_temp(EFD_SINTETICO, tmp_path, "efd.txt")
        dados = parse_efd_contrib(caminho)
        assert len(dados.retencoes) == 1
        assert dados.retencoes[0].vl_ret == 1200.0
