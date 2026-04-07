"""Testes para o motor de gatilhos (conta e historico)."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.parsers.ecd_parser import ContaPlano, SaldoPeriodico, Partida
from src.gatilhos.motor_gatilhos import (
    executar_gatilhos_conta,
    executar_gatilhos_historico,
    resumo_gatilhos,
)


def _conta(codigo: str, nome: str, ind_cta: str = "A") -> ContaPlano:
    return ContaPlano(codigo=codigo, natureza="01", ind_cta=ind_cta,
                      nivel="2", cod_cta_sup="0", nome=nome, linha=1)


def _saldo(codigo: str, saldo_final: float, debitos: float = 1000.0) -> SaldoPeriodico:
    return SaldoPeriodico(
        codigo_conta=codigo, cod_ccus="", saldo_inicial=0.0,
        ind_dc_ini="D", debitos=debitos, creditos=0.0,
        saldo_final=saldo_final, ind_dc_fin="D", linha=1,
    )


def _partida(cod_cta: str, historico: str, valor: float = 5000.0) -> Partida:
    return Partida(cod_cta=cod_cta, cod_ccus="", valor=valor, ind_dc="D",
                   historico=historico, cod_part="", num_lcto="001",
                   dt_lcto="01012024", linha=1)


class TestGatilhosConta:
    def test_gc01_tributos_a_compensar(self):
        plano = {"41": _conta("41", "PIS A COMPENSAR")}
        saldos = {"41": [_saldo("41", 3008.0)]}
        achados = executar_gatilhos_conta(plano, saldos)
        assert any(g.gatilho == "GC01" for g in achados)

    def test_gc02_irrf_a_compensar(self):
        plano = {"101": _conta("101", "IRRF A COMPENSAR")}
        saldos = {"101": [_saldo("101", 40000.0)]}
        achados = executar_gatilhos_conta(plano, saldos)
        assert any(g.gatilho == "GC02" for g in achados)

    def test_gc03_pis_cofins_compensar(self):
        plano = {"42": _conta("42", "COFINS A COMPENSAR")}
        saldos = {"42": [_saldo("42", 16431.0)]}
        achados = executar_gatilhos_conta(plano, saldos)
        assert any(g.gatilho == "GC03" for g in achados)

    def test_gc05_alimentacao_pat(self):
        plano = {"275": _conta("275", "DESPESA ALIMENTACAO")}
        saldos = {"275": [_saldo("275", 0.0, debitos=5000.0)]}
        achados = executar_gatilhos_conta(plano, saldos)
        assert any(g.gatilho == "GC05" for g in achados)

    def test_gc12_combustivel_insumo(self):
        plano = {"271": _conta("271", "COMBUSTIVEIS E LUBRIFICANTES")}
        saldos = {"271": [_saldo("271", 0.0, debitos=236239.0)]}
        achados = executar_gatilhos_conta(plano, saldos)
        assert any(g.gatilho == "GC12" for g in achados)

    def test_conta_sintetica_ignorada(self):
        plano = {"10": _conta("10", "PIS A COMPENSAR", ind_cta="S")}
        saldos = {"10": [_saldo("10", 5000.0)]}
        achados = executar_gatilhos_conta(plano, saldos)
        assert achados == []

    def test_conta_sem_saldo_ignorada(self):
        plano = {"41": _conta("41", "PIS A COMPENSAR")}
        saldos = {"41": [_saldo("41", 0.0, debitos=0.0)]}
        achados = executar_gatilhos_conta(plano, saldos)
        assert achados == []

    def test_conta_sem_saldos_registrados(self):
        plano = {"41": _conta("41", "PIS A COMPENSAR")}
        saldos = {}
        achados = executar_gatilhos_conta(plano, saldos)
        assert achados == []

    def test_severidade_alta(self):
        plano = {"41": _conta("41", "PIS A COMPENSAR")}
        saldos = {"41": [_saldo("41", 3008.0)]}
        achados = executar_gatilhos_conta(plano, saldos)
        gc01 = next(g for g in achados if g.gatilho == "GC01")
        assert gc01.severidade == "alta"

    def test_tipo_conta(self):
        plano = {"41": _conta("41", "PIS A COMPENSAR")}
        saldos = {"41": [_saldo("41", 3008.0)]}
        achados = executar_gatilhos_conta(plano, saldos)
        assert all(g.tipo == "conta" for g in achados)


class TestGatilhosHistorico:
    def _plano(self):
        return {"101": _conta("101", "IRRF A COMPENSAR")}

    def test_gh02_baixa_pdd(self):
        partidas = [_partida("58", "baixa pdd cliente inadimplente", 15000.0)]
        achados = executar_gatilhos_historico(partidas, self._plano())
        assert any(g.gatilho == "GH02" for g in achados)

    def test_gh06_retencao_na_fonte(self):
        partidas = [_partida("101", "retencao irrf sobre juros sicoob", 40000.0)]
        achados = executar_gatilhos_historico(partidas, self._plano())
        assert any(g.gatilho == "GH06" for g in achados)

    def test_gh09_contabilizacao_incorreta(self):
        partidas = [_partida("100", "estorno por erro de classificacao incorreta", 5000.0)]
        achados = executar_gatilhos_historico(partidas, self._plano())
        assert any(g.gatilho == "GH09" for g in achados)

    def test_limite_valor_filtra(self):
        partidas = [_partida("58", "baixa pdd", 500.0)]  # Abaixo do limite
        achados = executar_gatilhos_historico(partidas, self._plano(), limite_valor=1000.0)
        assert achados == []

    def test_amostra_max_limita(self):
        partidas = [_partida("58", "retencao irrf", float(i)) for i in range(1000, 1020)]
        achados = executar_gatilhos_historico(partidas, self._plano(), amostra_max=5)
        por_gatilho = {}
        for a in achados:
            por_gatilho[a.gatilho] = por_gatilho.get(a.gatilho, 0) + 1
        assert all(v <= 5 for v in por_gatilho.values())

    def test_sem_historico_ignorado(self):
        partidas = [_partida("100", "", 5000.0)]
        achados = executar_gatilhos_historico(partidas, self._plano())
        assert achados == []

    def test_tipo_historico(self):
        partidas = [_partida("58", "baixa pdd definitiva", 10000.0)]
        achados = executar_gatilhos_historico(partidas, self._plano())
        assert all(g.tipo == "historico" for g in achados)


class TestResumoGatilhos:
    def test_resumo_vazio(self):
        resumo = resumo_gatilhos([])
        assert resumo["total"] == 0
        assert resumo["por_severidade"]["alta"] == 0

    def test_contagem_por_severidade(self):
        from src.gatilhos.motor_gatilhos import AchadoGatilho
        def _ag(sev):
            return AchadoGatilho(
                gatilho="GC01", categoria="CREDITO", descricao="",
                justificativa="", acao="", severidade=sev,
                cod_conta="1", nome_conta="X", historico="",
                valor=1000.0, data="", num_lancamento="", linha_arquivo=1, tipo="conta",
            )
        achados = [_ag("alta"), _ag("alta"), _ag("media"), _ag("baixa")]
        resumo = resumo_gatilhos(achados)
        assert resumo["total"] == 4
        assert resumo["por_severidade"]["alta"] == 2
        assert resumo["por_severidade"]["media"] == 1
        assert resumo["por_severidade"]["baixa"] == 1
        assert resumo["valor_total"] == pytest.approx(4000.0)
