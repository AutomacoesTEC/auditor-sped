# Catálogo de Regras de Auditoria

Cada regra tem base legal verificável e aponta os registros SPED de origem.
Achados de baixa confiança são sinalizados como hipótese.

---

## R01 — Saldo negativo de IRPJ/CSLL não compensado

**Status:** Implementada  
**Arquivo:** `src/regras/r01_saldo_negativo.py`  
**Confiança:** Alta

### O que verifica
1. IRPJ: se `estimativas + IRRF + incentivos > IRPJ devido` e IRPJ a pagar = 0 → saldo negativo não compensado
2. IRRF (Y570): IRRF retido na fonte com utilização zero e N630 linha 20 = 0
3. CSLL: se `estimativas > CSLL devida` e CSLL a pagar = 0

### Registros utilizados
- `N630` linhas 3, 4, 8, 11, 12, 20, 24, 25, 26
- `N670` linhas 4, 15, 17, 19, 20, 21
- `Y570` (IRRF retido por fonte pagadora)
- `Y580` (PER/DCOMP transmitidos)

### Base legal
- Art. 6, Lei 9.430/1996 (saldo negativo)
- Arts. 228-229, IN RFB 1.700/2017
- Arts. 714-716 RIR/2018 (IRRF dedutível)

---

## R02 — IRRF retido em contas ECD não aproveitado na ECF

**Status:** Implementada  
**Arquivo:** `src/regras/r02_irrf_contas.py`  
**Confiança:** Alta

### O que verifica
Cruzamento entre saldo de contas de IRRF/IRPJ a compensar no ECD (I155) e o valor deduzido na ECF (N630 linha 20). Se saldo contábil > valor aproveitado, há diferença não utilizada.

### Registros utilizados
- `I155` / `C155` — saldos periódicos das contas de IRRF a compensar
- `N630` linha 20 — IRRF deduzido do IRPJ
- `I050` — plano de contas (identificação das contas por nome)

### Base legal
- Arts. 714-716 RIR/2018
- Art. 36, IN RFB 1.700/2017
- Art. 6, Lei 9.430/1996

---

## R03 — CSRF retida na fonte não deduzida da CSLL/IRPJ

**Status:** Implementada  
**Arquivo:** `src/regras/r03_csrf_nao_deduzida.py`  
**Confiança:** Alta (saldo zero em N670) / Média (saldo < saldo ECD)

### O que verifica
Contas de CSRF/CSLL retida no ECD com saldo positivo versus deduções em N670 linhas 15-18. Se há saldo contábil e N670 = zero, a CSRF não está sendo aproveitada.

### Registros utilizados
- `I155` — saldo de contas de CSRF/CSLL retida
- `N670` linhas 15, 16, 17, 18

### Base legal
- Lei 10.833/2003, arts. 30-36
- IN RFB 459/2004
- IN RFB 1.234/2012

---

## R04 — Estimativas mensais de IRPJ/CSLL pagas a maior

**Status:** Implementada  
**Arquivo:** `src/regras/r04_estimativas_maior.py`  
**Confiança:** Alta

### O que verifica
1. Soma das estimativas mensais N620 linha 26 versus N630 linha 24 (divergência)
2. Total de estimativas (N630 linhas 24+25) versus IRPJ devido (linhas 3+4): se excesso > 500 e não há PER/DCOMP, há crédito não reivindicado
3. Mesma análise para CSLL (N670 linhas 19+20 vs. linha 4)

### Registros utilizados
- `N620` linha 26 (IRPJ mensal — um por mês)
- `N630` linhas 3, 4, 24, 25, 26
- `N670` linhas 4, 19, 20, 21
- `Y580` (PER/DCOMP transmitidos)

### Base legal
- Lei 9.430/1996, arts. 2-6
- IN RFB 1.700/2017, art. 5

---

## R05 — Créditos de PIS/COFINS subutilizados

**Status:** Implementada  
**Arquivo:** `src/regras/r05_creditos_pis_cofins.py`  
**Confiança:** Alta (saldos ECD) / Baixa (estimativa por despesas)

### O que verifica
1. Saldos de contas "PIS a compensar" e "COFINS a compensar" no ECD sem PER/DCOMP identificado
2. Despesas operacionais creditáveis (aluguel, combustível, frete, energia, etc.) — estimativa de crédito potencial

### Registros utilizados
- `I155` — saldos de contas de PIS/COFINS a compensar
- `I050` — plano de contas
- `I155` (débitos) — movimentação de despesas creditáveis

### Base legal
- Lei 10.637/2002, art. 3 (PIS não cumulativo)
- Lei 10.833/2003, art. 3 (COFINS não cumulativo)
- IN RFB 2.121/2022
- REsp 1.221.170/PR — STJ (conceito amplo de insumo)

---

## R06 — Incentivo PAT não deduzido do IRPJ

**Status:** Implementada  
**Arquivo:** `src/regras/r06_pat.py`  
**Confiança:** Média (requer verificação de inscrição no PAT)

### O que verifica
Contas de alimentação/refeição no ECD com movimentação versus N630 linha 8 (dedução PAT). Limite legal: 4% do IRPJ calculado a 15%.

### Registros utilizados
- `I155` — movimentação de contas de alimentação
- `N630` linha 3 (IRPJ 15%) e linha 8 (dedução PAT)

### Base legal
- Lei 6.321/1976 (PAT)
- Decreto 10.854/2021 (regulamentação)
- Art. 14, Lei 9.249/1995

### Observação
Requer inscrição ativa no PAT (Ministério do Trabalho). Sem inscrição, o incentivo não é admitido.

---

## R07 — Depreciação acelerada incentivada não escriturada no LALUR

**Status:** Implementada  
**Arquivo:** `src/regras/r07_depreciacao_acelerada.py`  
**Confiança:** Baixa (requer levantamento do imobilizado)

### O que verifica
Presença de contas de depreciação no ECD com movimentação versus ausência de exclusões de depreciação no M300 (IND_AD_EX = "E"). Ausência de exclusão pode indicar que a depreciação acelerada incentivada não foi aplicada.

### Registros utilizados
- `I155` — movimentação de contas de depreciação
- `M300` — exclusões no LALUR (tipo E, descrição com "depreciação")
- `I155` — saldo do imobilizado

### Base legal
- RIR/2018, arts. 323-326
- IN RFB 1.700/2017, art. 170
- Lei 14.871/2024 (novos setores elegíveis)

---

## R08 — Prejuízo fiscal não compensado ou abaixo do limite de 30%

**Status:** Implementada  
**Arquivo:** `src/regras/r08_prejuizo_fiscal.py`  
**Confiança:** Alta (saldo disponível confirmado em M410)

### O que verifica
1. M300 tipo C (compensações) versus saldo de prejuízo na Parte B (M410): se há saldo e nenhuma compensação foi realizada
2. Compensação realizada abaixo do limite de 30% do lucro real

### Registros utilizados
- `N630` linha 1 (base de cálculo IRPJ)
- `M300` tipo C (compensações de prejuízo)
- `M410` (saldos Parte B do LALUR)

### Base legal
- RIR/2018, arts. 580-583
- Art. 15, Lei 9.065/1995
- Art. 42, Lei 8.981/1995

---

## R09 — Subvenções governamentais sem tratamento no LALUR

**Status:** Implementada  
**Arquivo:** `src/regras/r09_subvencoes.py`  
**Confiança:** Baixa (requer análise do ato concessório)

### O que verifica
Contas de subvenção/incentivo fiscal no ECD com movimentação versus:
- Ausência de exclusão no M300 (regime Lei 12.973/2014)
- Adição sem exclusão correspondente (possível tributação indevida)

### Registros utilizados
- `I155` — movimentação de contas de subvenção
- `M300` — adições e exclusões no LALUR

### Base legal
- Art. 30, Lei 12.973/2014 (exclusão para investimento)
- Lei 14.789/2023 (crédito fiscal de 25% — regime novo)
- IN RFB 2.170/2024

### Observação crítica
Requer: (1) análise do ato concessório; (2) verificação das condicionalidades; (3) escolha do regime (irrevogável). Não transmitir PER/DCOMP sem laudo jurídico-contábil.

---

## R10 — Perdas no recebimento de créditos não deduzidas

**Status:** Implementada  
**Arquivo:** `src/regras/r10_perdas_creditos.py`  
**Confiança:** Média / Baixa (requer documentação de cada crédito)

### O que verifica
1. PDD adicionada no LALUR (M300 tipo A) sem exclusão correspondente quando há baixas definitivas (contas de perdas reais ou históricos "baixa PDD")
2. Baixas definitivas em históricos (I250) sem nenhum tratamento no LALUR

### Registros utilizados
- `I155` — saldo de contas de PDD e perdas reais
- `M300` — adições e exclusões de PDD
- `I250` — históricos com padrões de baixa definitiva

### Base legal
- Art. 9, Lei 9.430/1996
- Arts. 347-354 RIR/2018

### Requisitos do art. 9 (para dedução)
| Valor do crédito | Condição |
|-----------------|----------|
| Até R$ 15.000 | Vencido há mais de 6 meses, sem garantia |
| R$ 15.001 a R$ 100.000 | Vencido há mais de 1 ano, sem garantia |
| Acima de R$ 100.000 | Com garantia + processo judicial ou arbitral |

---

## Legislação base consolidada

| Norma | Tema |
|-------|------|
| RIR/2018 (Decreto 9.580/2018) | Regulamento do Imposto de Renda |
| Lei 9.430/1996 | Saldo negativo, compensação, perdas em créditos |
| Lei 9.249/1995 | JCP, PAT, dedutibilidade |
| Lei 9.065/1995 | Compensação de prejuízo fiscal |
| Lei 10.637/2002 | PIS não cumulativo |
| Lei 10.833/2003 | COFINS não cumulativo e CSRF |
| Lei 12.973/2014 | Subvenções para investimento |
| Lei 14.789/2023 | Crédito fiscal de subvenções (regime novo) |
| Lei 14.871/2024 | Depreciação acelerada — novos setores |
| IN RFB 459/2004 | CSRF |
| IN RFB 1.234/2012 | Retenções na fonte |
| IN RFB 1.700/2017 | IRPJ/CSLL consolidação |
| IN RFB 2.055/2021 | PER/DCOMP |
| IN RFB 2.121/2022 | PIS/COFINS |
| IN RFB 2.170/2024 | Subvenções — regime Lei 14.789/2023 |
| REsp 1.221.170/PR (STJ) | Conceito amplo de insumo PIS/COFINS |
