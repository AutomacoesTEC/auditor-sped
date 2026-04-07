# Auditor SPED

> Sistema profissional de auditoria tributária em arquivos SPED (ECD, ECF, EFD-Contribuições) para identificação de créditos tributários restituíveis em empresas do **Lucro Real**.

---

## O que faz

Lê os arquivos digitais do SPED, cruza lançamentos contábeis com a legislação fiscal e identifica:

- **Créditos tributários não aproveitados** — saldo negativo de IRPJ/CSLL, IRRF não deduzido, estimativas pagas a maior, CSRF retida não compensada
- **Incentivos fiscais não utilizados** — PAT, depreciação acelerada, subvenções, prejuízo fiscal não compensado
- **Créditos de PIS/COFINS subutilizados** — regime não cumulativo, saldos a compensar, despesas creditáveis
- **Lançamentos suspeitos** — 22 gatilhos automáticos em nomes de contas e históricos

Cada achado aponta os registros de origem (tipo, linha, valores) e inclui base legal, recomendação e risco.

---

## Resultado validado (BRASNORTE DISTRIBUIDORA, ECD 2024)

```
684.495 registros parseados em ~10 segundos
319 contas | 172 mapeamentos | 118.743 lançamentos | 562.197 partidas

REGRAS: R01 → IRRF R$ 40.396,23 retido (SICOOB + SANTANDER) — utilização ZERO
GATILHOS: 109 disparados | Alta: 55 | Média: 32 | Baixa: 22
```

---

## Regras de auditoria implementadas

| Código | Descrição | Tributo | Base Legal |
|--------|-----------|---------|------------|
| R01 | Saldo negativo IRPJ/CSLL + IRRF não aproveitado | IRPJ/CSLL | Art. 6, Lei 9.430/96 |
| R02 | IRRF retido em contas ECD não aproveitado na ECF | IRPJ | Arts. 714-716 RIR/2018 |
| R03 | CSRF retida na fonte não deduzida da CSLL | CSLL | Lei 10.833/2003, arts. 30-36 |
| R04 | Estimativas mensais de IRPJ/CSLL pagas a maior | IRPJ/CSLL | Lei 9.430/96, arts. 2-6 |
| R05 | Créditos de PIS/COFINS subutilizados | PIS/COFINS | Lei 10.637/2002 art. 3; REsp 1.221.170/PR |
| R06 | Incentivo PAT não deduzido do IRPJ | IRPJ | Lei 6.321/1976; Decreto 10.854/2021 |
| R07 | Depreciação acelerada não escriturada no LALUR | IRPJ | RIR/2018 arts. 323-326; Lei 14.871/2024 |
| R08 | Prejuízo fiscal não compensado (limite 30%) | IRPJ/CSLL | RIR/2018 arts. 580-583 |
| R09 | Subvenções sem exclusão no LALUR ou crédito fiscal | IRPJ/CSLL | Lei 12.973/2014; Lei 14.789/2023 |
| R10 | Perdas em créditos/PDD sem dedução no LALUR | IRPJ/CSLL | Art. 9, Lei 9.430/96 |

---

## Requisitos

- Python 3.11+
- `openpyxl >= 3.1.0`
- `reportlab >= 4.0`

```bash
pip install -r requirements.txt
```

---

## Como usar

### Auditoria completa com relatórios

```bash
python main.py \
  --ecd caminho/ecd.txt \
  --ecf caminho/ecf.txt \
  --efd caminho/efd_contrib.txt \
  --saida resultado/ \
  --xlsx \
  --pdf \
  --verbose
```

### Só JSON (sem relatórios)

```bash
python main.py --ecd ecd.txt --ecf ecf.txt --saida resultado/
```

### Filtrar gatilhos de histórico

```bash
python main.py --ecd ecd.txt --ecf ecf.txt \
  --limite-valor 1000 \
  --amostra-gatilho 50
```

### Argumentos disponíveis

| Argumento | Descrição | Padrão |
|-----------|-----------|--------|
| `--ecd` | Caminho do arquivo ECD (.txt) | — |
| `--ecf` | Caminho do arquivo ECF (.txt) | — |
| `--efd` | Caminho do arquivo EFD-Contribuições (.txt) | — |
| `--saida` | Diretório de saída dos resultados | `./resultado` |
| `--xlsx` | Gerar relatório Excel profissional | off |
| `--pdf` | Gerar parecer técnico em PDF | off |
| `--limite-valor` | Valor mínimo para gatilhos de histórico | 0 |
| `--amostra-gatilho` | Máximo de achados por gatilho (0 = ilimitado) | 50 |
| `--verbose` / `-v` | Log detalhado | off |

---

## Saídas geradas

```
resultado/
  auditoria.json              Todos os achados e gatilhos (estruturado)
  auditoria_EMPRESA.xlsx      Relatório Excel (Capa, Resumo, R01-R10, Gatilhos)
  parecer_EMPRESA.pdf         Parecer técnico (7 seções, rodapé, ressalvas)
```

### Estrutura do JSON

```json
{
  "empresa": "RAZÃO SOCIAL",
  "cnpj": "XX.XXX.XXX/XXXX-XX",
  "periodo": "01012024 a 31122024",
  "regras": {
    "total_achados": 3,
    "valor_estimado": 125430.50,
    "achados": [
      {
        "regra": "R01",
        "titulo": "...",
        "valor_estimado": 40396.23,
        "tributo": "IRPJ",
        "confianca": "alta",
        "registros_origem": ["N630 linha 20: R$ 0,00", "Y570: SICOOB R$ 40.239,65"],
        "recomendacao": "Transmitir PER/DCOMP Web...",
        "risco": "Prescrição quinquenal."
      }
    ]
  },
  "gatilhos": { "total": 109, "resumo": {...}, "achados": [...] }
}
```

---

## Arquitetura

```
auditor-sped/
  main.py                     Orquestrador (parsing → regras → gatilhos → relatórios)
  config.py                   Constantes, campos SPED, linhas-chave ECF

  src/
    parsers/
      sped_parser.py          Parser genérico: encoding, separador, erros
      ecd_parser.py           ECD: I050, I051, I155, I200, I250, C050-C155
      ecf_parser.py           ECF: N620, N630, N670, M300, Y570, Y580, Y600
      efd_contrib_parser.py   EFD-Contrib: M100, M500, M200, M600, F600, 1100, 1500

    regras/
      base_regra.py           Interface RegraAuditoria + dataclass Achado
      r01_saldo_negativo.py   Saldo negativo IRPJ/CSLL + IRRF não utilizado
      r02_irrf_contas.py      IRRF em contas ECD vs. N630 linha 20
      r03_csrf_nao_deduzida.py CSRF/CSLL retida sem dedução em N670
      r04_estimativas_maior.py Estimativas pagas a maior (N620/N630/N670)
      r05_creditos_pis_cofins.py Créditos PIS/COFINS subutilizados
      r06_pat.py              PAT não deduzido (4% IRPJ, N630 linha 8)
      r07_depreciacao_acelerada.py Depreciação acelerada sem exclusão no LALUR
      r08_prejuizo_fiscal.py  Prejuízo fiscal não compensado (limite 30%)
      r09_subvencoes.py       Subvenções sem tratamento no LALUR
      r10_perdas_creditos.py  Perdas em créditos/PDD sem exclusão

    gatilhos/
      motor_gatilhos.py       12 gatilhos de conta (GC) + 10 de histórico (GH)

    relatorios/
      gerador_xlsx.py         Relatório Excel (5 abas, cores por severidade)
      gerador_pdf.py          Parecer técnico PDF (7 seções, reportlab)

  tests/                      Testes pytest (dados sintéticos)
  docs/
    REGRAS_AUDITORIA.md       Catálogo de regras com base legal completa
    GATILHOS.md               Catálogo de gatilhos
  data/
    leiautes/                 Leiautes oficiais RFB (não versionados)
    amostras/                 Arquivos de teste (não versionados)
  resultado/                  Saídas (não versionadas)
```

---

## Formato dos arquivos SPED

- **Encoding**: ISO-8859-1 (fallback UTF-8, detectado automaticamente)
- **Separador**: `|` (pipe)
- **Decimal**: vírgula
- Cada linha começa e termina com `|`

---

## Segurança

- Caminhos de entrada validados com `os.path.realpath()` (proteção contra path traversal)
- Nomes de arquivo de saída sanitizados (sem caracteres especiais)
- Arquivos SPED e resultados de auditoria no `.gitignore` (dados fiscais não versionados)
- Encoding com `errors="replace"` — arquivo corrompido não causa crash

---

## Convenções

- Python 3.11+, type hints, docstrings em português
- Variáveis e funções em `snake_case` português
- Logging: `INFO` = fluxo, `WARNING` = dados ausentes, `ERROR` = falhas
- Regras: separação estrita entre parsing (parsers/) e lógica (regras/)
- Testes: pytest com dados sintéticos embutidos como string

---

## Licença

Uso interno. Todos os direitos reservados.
