# Catálogo de Gatilhos

## Gatilhos de Conta (GC)

| Código | Categoria | Descrição | Severidade |
|--------|-----------|-----------|------------|
| GC01 | CREDITO_TRIBUTARIO | Tributos a compensar com saldo remanescente | Alta |
| GC02 | IRPJ | IRRF a compensar/recuperar | Alta |
| GC03 | PIS_COFINS | PIS/COFINS a compensar | Alta |
| GC04 | CSLL | CSLL retida/a compensar | Alta |
| GC05 | IRPJ | Despesas com alimentação (potencial PAT) | Média |
| GC06 | IRPJ | Depreciação (taxas e aceleração) | Média |
| GC07 | IRPJ | Provisão para devedores duvidosos / PDD | Média |
| GC08 | IRPJ | Subvenções governamentais | Alta |
| GC09 | IRPJ | Juros sobre capital próprio | Média |
| GC10 | CLASSIFICACAO | Multas fiscais (dedutibilidade) | Média |
| GC11 | CLASSIFICACAO | Brindes e bonificações | Baixa |
| GC12 | PIS_COFINS | Despesas creditáveis PIS/COFINS (insumos) | Alta |

## Gatilhos de Histórico (GH)

| Código | Categoria | Descrição | Severidade |
|--------|-----------|-----------|------------|
| GH01 | PROCEDIMENTO | Ajuste/estorno (regularidade) | Baixa |
| GH02 | IRPJ | Baixa de PDD / Perda em crédito | Alta |
| GH03 | CLASSIFICACAO | Baixa de ativo / alienação | Média |
| GH04 | IRPJ | Referência a exercício anterior | Média |
| GH05 | PIS_COFINS | Devolução de vendas/compras | Baixa |
| GH06 | CREDITO_TRIBUTARIO | Retenção na fonte no histórico | Alta |
| GH07 | CLASSIFICACAO | Despesa pessoal ou de sócio | Média |
| GH08 | CREDITO_TRIBUTARIO | Crédito de fornecedor / bonificação | Média |
| GH09 | IRPJ | Contabilização incorreta declarada | Alta |
| GH10 | PROCEDIMENTO | Pagamento sem nota fiscal | Alta |

## Como funciona

1. **Gatilhos de conta**: analisam o nome de cada conta analítica (I050/C050) contra palavras-chave. Só disparam se a conta teve movimentação ou saldo > 0.

2. **Gatilhos de histórico**: analisam o campo HIST de cada partida (I250) contra padrões. Filtráveis por valor mínimo e limite de amostra por gatilho.

## Adicionar novo gatilho

Editar `src/gatilhos/motor_gatilhos.py` e adicionar instância de `Gatilho` na lista `GATILHOS_CONTA` ou `GATILHOS_HISTORICO`.
