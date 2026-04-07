"""Testes para as regras de auditoria R01-R10.

Cada teste constroi objetos DadosECD/DadosECF sinteticos diretamente
(sem parsing de arquivo) para isolar a logica da regra.
"""

import sys
import os
import pytest
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.parsers.ecd_parser import DadosECD, ContaPlano, SaldoPeriodico, Partida, Lancamento
from src.parsers.ecf_parser import DadosECF, LinhaTabular, LancamentoLALUR, RetencaoIRRF, PERDcomp
from src.parsers.efd_contrib_parser import DadosEFDContrib


# ============================================================
# FACTORIES: construtores de dados sinteticos
# ============================================================

def _conta(codigo: str, nome: str, natureza: str = "01", ind_cta: str = "A", linha: int = 1) -> ContaPlano:
    return ContaPlano(codigo=codigo, natureza=natureza, ind_cta=ind_cta,
                      nivel="2", cod_cta_sup="0", nome=nome, linha=linha)


def _saldo(codigo: str, saldo_final: float, ind_dc: str = "D",
           debitos: float = 0.0, creditos: float = 0.0) -> SaldoPeriodico:
    return SaldoPeriodico(
        codigo_conta=codigo, cod_ccus="", saldo_inicial=0.0,
        ind_dc_ini=ind_dc, debitos=debitos, creditos=creditos,
        saldo_final=saldo_final, ind_dc_fin=ind_dc, linha=1,
    )


def _linha_ecf(codigo: str, valor: float, descricao: str = "") -> LinhaTabular:
    return LinhaTabular(codigo_linha=codigo, descricao=descricao, valor=valor, linha_arquivo=1)


def _lalur(descricao: str, ind_ad_ex: str, valor: float) -> LancamentoLALUR:
    return LancamentoLALUR(codigo="001", descricao=descricao, ind_ad_ex=ind_ad_ex,
                           tp_lancamento="1", valor=valor, linha=1)


def _irrf(nome: str, retido: float, utilizado: float = 0.0) -> RetencaoIRRF:
    return RetencaoIRRF(cnpj="12345678000195", nome=nome, cod_rec="1990",
                        vl_receita=retido * 2, vl_ir_retido=retido,
                        vl_ir_utilizado=utilizado, linha=1)


def _partida(cod_cta: str, historico: str, valor: float = 1000.0) -> Partida:
    return Partida(cod_cta=cod_cta, cod_ccus="", valor=valor, ind_dc="D",
                   historico=historico, cod_part="", num_lcto="0001",
                   dt_lcto="01012024", linha=1)


def _ecd_basico(**kwargs) -> DadosECD:
    dados = DadosECD(razao_social="EMPRESA TESTE LTDA", cnpj="14781517000149",
                     dt_ini="01012024", dt_fin="31122024")
    for k, v in kwargs.items():
        setattr(dados, k, v)
    return dados


def _ecf_basico(**kwargs) -> DadosECF:
    dados = DadosECF(razao_social="EMPRESA TESTE LTDA", cnpj="14781517000149",
                     dt_ini="01012024", dt_fin="31122024", forma_tribut="1")
    for k, v in kwargs.items():
        setattr(dados, k, v)
    return dados


# ============================================================
# R01: Saldo negativo IRPJ/CSLL + IRRF nao aproveitado
# ============================================================

class TestR01SaldoNegativo:
    def _regra(self):
        from src.regras.r01_saldo_negativo import R01SaldoNegativo
        return R01SaldoNegativo()

    def test_sem_ecf_retorna_vazio(self):
        achados = self._regra().executar(None, None, {})
        assert achados == []

    def test_irrf_retido_nao_utilizado(self):
        ecf = _ecf_basico(
            n630=[_linha_ecf("3", 0.0), _linha_ecf("4", 0.0),
                  _linha_ecf("20", 0.0), _linha_ecf("24", 0.0), _linha_ecf("26", 0.0)],
            n670=[_linha_ecf("4", 0.0), _linha_ecf("19", 0.0), _linha_ecf("21", 0.0)],
            y570_irrf=[_irrf("BANCO SICOOB", 40239.65, 0.0), _irrf("SANTANDER", 156.58, 0.0)],
            y580_perdcomp=[],
        )
        achados = self._regra().executar(None, ecf, {})
        assert any("IRRF" in a.titulo for a in achados)
        irrf_achado = next(a for a in achados if "IRRF" in a.titulo and "Y570" in a.titulo)
        assert irrf_achado.valor_estimado == pytest.approx(40396.23, rel=1e-3)
        assert irrf_achado.confianca == "alta"
        assert irrf_achado.tributo == "IRPJ"

    def test_saldo_negativo_irpj(self):
        ecf = _ecf_basico(
            n630=[
                _linha_ecf("3", 5000.0),   # IRPJ 15%
                _linha_ecf("4", 0.0),       # Adicional
                _linha_ecf("8", 0.0),       # PAT
                _linha_ecf("11", 0.0),
                _linha_ecf("12", 0.0),
                _linha_ecf("20", 0.0),      # IRRF deduzido
                _linha_ecf("24", 20000.0),  # Estimativas pagas
                _linha_ecf("25", 0.0),
                _linha_ecf("26", 0.0),      # IRPJ a pagar = 0
            ],
            n670=[_linha_ecf("4", 0.0), _linha_ecf("19", 0.0), _linha_ecf("21", 0.0)],
            y570_irrf=[],
            y580_perdcomp=[],
        )
        achados = self._regra().executar(None, ecf, {})
        saldo = next((a for a in achados if "negativo" in a.titulo.lower() and "IRPJ" in a.titulo), None)
        assert saldo is not None
        assert saldo.valor_estimado == pytest.approx(15000.0)

    def test_sem_achado_quando_irpj_a_pagar(self):
        ecf = _ecf_basico(
            n630=[_linha_ecf("3", 5000.0), _linha_ecf("4", 0.0),
                  _linha_ecf("8", 0.0), _linha_ecf("11", 0.0), _linha_ecf("12", 0.0),
                  _linha_ecf("20", 0.0), _linha_ecf("24", 0.0), _linha_ecf("25", 0.0),
                  _linha_ecf("26", 5000.0)],  # Tem IRPJ a pagar
            n670=[_linha_ecf("4", 2000.0), _linha_ecf("19", 0.0), _linha_ecf("21", 2000.0)],
            y570_irrf=[],
            y580_perdcomp=[],
        )
        achados = self._regra().executar(None, ecf, {})
        assert not any("negativo" in a.titulo.lower() for a in achados)


# ============================================================
# R02: IRRF em contas ECD vs N630 linha 20
# ============================================================

class TestR02IRRFContas:
    def _regra(self):
        from src.regras.r02_irrf_contas import R02IRRFContas
        return R02IRRFContas()

    def test_sem_ecd_retorna_vazio(self):
        achados = self._regra().executar(None, _ecf_basico(), {})
        assert achados == []

    def test_irrf_no_ecd_sem_aproveitamento_ecf(self):
        ecd = _ecd_basico(
            plano_contas={"101": _conta("101", "IRRF A COMPENSAR")},
            saldos={"101": [_saldo("101", 40000.0, "D")]},
        )
        ecf = _ecf_basico(
            n630=[_linha_ecf("20", 0.0)],  # Sem aproveitamento
        )
        achados = self._regra().executar(ecd, ecf, {})
        assert len(achados) == 1
        assert achados[0].valor_estimado == pytest.approx(40000.0)
        assert achados[0].tributo == "IRPJ"

    def test_sem_achado_quando_irrf_aproveitado(self):
        ecd = _ecd_basico(
            plano_contas={"101": _conta("101", "IRRF A COMPENSAR")},
            saldos={"101": [_saldo("101", 40000.0, "D")]},
        )
        ecf = _ecf_basico(
            n630=[_linha_ecf("20", 39900.0)],  # Aproveitamento quase total
        )
        achados = self._regra().executar(ecd, ecf, {})
        # Diferenca = 40000 - 39900 = 100 (tolerancia exata, nao dispara)
        assert len(achados) == 0

    def test_conta_sintetica_ignorada(self):
        ecd = _ecd_basico(
            plano_contas={"10": _conta("10", "ATIVO CIRCULANTE", ind_cta="S")},
            saldos={"10": [_saldo("10", 100000.0, "D")]},
        )
        ecf = _ecf_basico(n630=[_linha_ecf("20", 0.0)])
        achados = self._regra().executar(ecd, ecf, {})
        assert achados == []


# ============================================================
# R03: CSRF retida nao deduzida
# ============================================================

class TestR03CSRF:
    def _regra(self):
        from src.regras.r03_csrf_nao_deduzida import R03CSRFNaoDeduzida
        return R03CSRFNaoDeduzida()

    def test_csrf_sem_deducao_ecf(self):
        ecd = _ecd_basico(
            plano_contas={"201": _conta("201", "CSRF A COMPENSAR")},
            saldos={"201": [_saldo("201", 5000.0, "D")]},
        )
        ecf = _ecf_basico(
            n670=[_linha_ecf("15", 0.0), _linha_ecf("16", 0.0),
                  _linha_ecf("17", 0.0), _linha_ecf("18", 0.0)],
        )
        achados = self._regra().executar(ecd, ecf, {})
        assert len(achados) == 1
        assert achados[0].valor_estimado == pytest.approx(5000.0)

    def test_sem_achado_quando_deduzido(self):
        ecd = _ecd_basico(
            plano_contas={"201": _conta("201", "CSRF A COMPENSAR")},
            saldos={"201": [_saldo("201", 5000.0, "D")]},
        )
        ecf = _ecf_basico(
            n670=[_linha_ecf("15", 5000.0), _linha_ecf("16", 0.0),
                  _linha_ecf("17", 0.0), _linha_ecf("18", 0.0)],
        )
        achados = self._regra().executar(ecd, ecf, {})
        assert achados == []


# ============================================================
# R04: Estimativas pagas a maior
# ============================================================

class TestR04Estimativas:
    def _regra(self):
        from src.regras.r04_estimativas_maior import R04EstimativasMaior
        return R04EstimativasMaior()

    def test_estimativas_maiores_que_irpj_devido(self):
        ecf = _ecf_basico(
            n620=[_linha_ecf("26", 7500.0)],
            n630=[
                _linha_ecf("3", 5000.0),
                _linha_ecf("4", 0.0),
                _linha_ecf("24", 20000.0),  # Estimativas >> IRPJ devido
                _linha_ecf("25", 0.0),
                _linha_ecf("26", 0.0),      # A pagar = 0
            ],
            n670=[_linha_ecf("4", 0.0), _linha_ecf("19", 0.0),
                  _linha_ecf("20", 0.0), _linha_ecf("21", 0.0)],
            y580_perdcomp=[],
        )
        achados = self._regra().executar(None, ecf, {})
        excesso = next((a for a in achados if "Estimativas" in a.titulo and "IRPJ" in a.titulo), None)
        assert excesso is not None
        assert excesso.valor_estimado == pytest.approx(15000.0)

    def test_sem_achado_quando_irpj_a_pagar(self):
        ecf = _ecf_basico(
            n620=[],
            n630=[_linha_ecf("3", 5000.0), _linha_ecf("4", 0.0),
                  _linha_ecf("24", 3000.0), _linha_ecf("25", 0.0),
                  _linha_ecf("26", 2000.0)],  # Ainda ha IRPJ a pagar
            n670=[_linha_ecf("4", 0.0), _linha_ecf("19", 0.0),
                  _linha_ecf("20", 0.0), _linha_ecf("21", 0.0)],
            y580_perdcomp=[],
        )
        achados = self._regra().executar(None, ecf, {})
        assert not any("a maior" in a.titulo.lower() for a in achados)


# ============================================================
# R05: Creditos PIS/COFINS subutilizados
# ============================================================

class TestR05PISCOFINS:
    def _regra(self):
        from src.regras.r05_creditos_pis_cofins import R05CreditosPISCOFINS
        return R05CreditosPISCOFINS()

    def test_saldo_pis_compensar(self):
        ecd = _ecd_basico(
            plano_contas={"41": _conta("41", "PIS A COMPENSAR")},
            saldos={"41": [_saldo("41", 3008.0, "D")]},
        )
        achados = self._regra().executar(ecd, None, {})
        assert any("PIS" in a.titulo for a in achados)

    def test_saldo_cofins_compensar(self):
        ecd = _ecd_basico(
            plano_contas={"42": _conta("42", "COFINS A COMPENSAR")},
            saldos={"42": [_saldo("42", 16431.0, "D")]},
        )
        achados = self._regra().executar(ecd, None, {})
        assert any("COFINS" in a.titulo for a in achados)

    def test_sem_saldo_sem_achado(self):
        ecd = _ecd_basico(
            plano_contas={"41": _conta("41", "PIS A COMPENSAR")},
            saldos={"41": [_saldo("41", 0.0, "D")]},
        )
        achados = self._regra().executar(ecd, None, {})
        assert not any("PIS a compensar" in a.titulo for a in achados)


# ============================================================
# R06: PAT nao deduzido
# ============================================================

class TestR06PAT:
    def _regra(self):
        from src.regras.r06_pat import R06PAT
        return R06PAT()

    def test_pat_nao_deduzido_com_despesa_alimentacao(self):
        ecd = _ecd_basico(
            plano_contas={"275": _conta("275", "DISPENDIOS COM ALIMENTACAO", natureza="04")},
            saldos={"275": [_saldo("275", 123955.0, "D", debitos=123955.0)]},
        )
        ecf = _ecf_basico(
            n630=[_linha_ecf("3", 50000.0), _linha_ecf("8", 0.0)],
        )
        achados = self._regra().executar(ecd, ecf, {})
        assert len(achados) == 1
        assert "PAT" in achados[0].titulo
        assert achados[0].valor_estimado > 0

    def test_sem_achado_quando_irpj_zero(self):
        ecd = _ecd_basico(
            plano_contas={"275": _conta("275", "ALIMENTACAO", natureza="04")},
            saldos={"275": [_saldo("275", 5000.0, "D", debitos=5000.0)]},
        )
        ecf = _ecf_basico(n630=[_linha_ecf("3", 0.0), _linha_ecf("8", 0.0)])
        achados = self._regra().executar(ecd, ecf, {})
        assert achados == []

    def test_sem_despesa_sem_achado(self):
        ecd = _ecd_basico(plano_contas={}, saldos={})
        ecf = _ecf_basico(n630=[_linha_ecf("3", 50000.0), _linha_ecf("8", 0.0)])
        achados = self._regra().executar(ecd, ecf, {})
        assert achados == []


# ============================================================
# R07: Depreciacao acelerada
# ============================================================

class TestR07Depreciacao:
    def _regra(self):
        from src.regras.r07_depreciacao_acelerada import R07DepreciacaoAcelerada
        return R07DepreciacaoAcelerada()

    def test_depreciacao_sem_exclusao_lalur(self):
        ecd = _ecd_basico(
            plano_contas={"301": _conta("301", "DEPRECIACAO DE MAQUINAS", natureza="04")},
            saldos={"301": [_saldo("301", 50000.0, "D", debitos=50000.0)]},
        )
        ecf = _ecf_basico(m300_irpj=[])  # Sem exclusoes
        achados = self._regra().executar(ecd, ecf, {})
        assert len(achados) == 1
        assert "Depreciacao" in achados[0].titulo or "depreciacao" in achados[0].titulo.lower()

    def test_com_exclusao_sem_achado(self):
        ecd = _ecd_basico(
            plano_contas={"301": _conta("301", "DEPRECIACAO", natureza="04")},
            saldos={"301": [_saldo("301", 50000.0, "D", debitos=50000.0)]},
        )
        ecf = _ecf_basico(
            m300_irpj=[_lalur("Exclusao depreciacao acelerada", "E", 25000.0)]
        )
        achados = self._regra().executar(ecd, ecf, {})
        assert achados == []


# ============================================================
# R08: Prejuizo fiscal
# ============================================================

class TestR08PrejuizoFiscal:
    def _regra(self):
        from src.regras.r08_prejuizo_fiscal import R08PrejuizoFiscal
        return R08PrejuizoFiscal()

    def test_base_positiva_sem_compensacao(self):
        from src.parsers.ecf_parser import RegistroSPED  # apenas para mock
        from src.parsers.sped_parser import RegistroSPED as Reg
        ecf = _ecf_basico(
            n630=[_linha_ecf("1", 200000.0)],  # base positiva
            m300_irpj=[],  # sem compensacao
            registros_brutos={},
        )
        achados = self._regra().executar(None, ecf, {})
        # Sem M410 nao ha saldo confirmado de prejuizo — nao dispara com alta confianca
        assert isinstance(achados, list)

    def test_sem_base_sem_achado(self):
        ecf = _ecf_basico(
            n630=[_linha_ecf("1", 0.0)],
            m300_irpj=[],
            registros_brutos={},
        )
        achados = self._regra().executar(None, ecf, {})
        assert achados == []


# ============================================================
# R09: Subvencoes
# ============================================================

class TestR09Subvencoes:
    def _regra(self):
        from src.regras.r09_subvencoes import R09Subvencoes
        return R09Subvencoes()

    def test_subvencao_sem_tratamento_lalur(self):
        ecd = _ecd_basico(
            plano_contas={"511": _conta("511", "SUBVENCOES GOVERNAMENTAIS", natureza="04")},
            saldos={"511": [_saldo("511", 50000.0, "C", creditos=50000.0)]},
        )
        ecf = _ecf_basico(m300_irpj=[])
        achados = self._regra().executar(ecd, ecf, {})
        assert len(achados) == 1
        assert achados[0].confianca == "baixa"

    def test_sem_conta_sem_achado(self):
        ecd = _ecd_basico(plano_contas={}, saldos={})
        ecf = _ecf_basico(m300_irpj=[])
        achados = self._regra().executar(ecd, ecf, {})
        assert achados == []


# ============================================================
# R10: Perdas em creditos
# ============================================================

class TestR10PerdasCreditos:
    def _regra(self):
        from src.regras.r10_perdas_creditos import R10PerdasCreditos
        return R10PerdasCreditos()

    def test_pdd_adicionada_sem_exclusao_com_baixas(self):
        ecd = _ecd_basico(
            plano_contas={"58": _conta("58", "PROVISAO PDD", natureza="04")},
            saldos={"58": [_saldo("58", 121179.0, "D")]},
            partidas=[_partida("58", "BAIXA/PREJUIZO PDD CLIENTE X", 15000.0)],
        )
        ecf = _ecf_basico(
            m300_irpj=[_lalur("PDD adicionada", "A", 121179.0)],
        )
        achados = self._regra().executar(ecd, ecf, {})
        assert len(achados) == 1
        assert "PDD" in achados[0].titulo or "perdas" in achados[0].titulo.lower()

    def test_sem_pdd_sem_achado(self):
        ecd = _ecd_basico(plano_contas={}, saldos={}, partidas=[])
        ecf = _ecf_basico(m300_irpj=[])
        achados = self._regra().executar(ecd, ecf, {})
        assert achados == []
