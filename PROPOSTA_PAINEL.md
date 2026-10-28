# Proposta — Dashboard de Gestão (Gestão MASC)

Proposta original de 27/10/2026, para Eloi Lerner. Cópia do documento https://claude.ai/artifact/9t9eoX58VEzxxtPr4JSFcU, com as decisões tomadas e, no fim, um resumo do que foi implementado.

## Resumo

Proponho uma única tela **Painel** (vira a página inicial do sistema) com quatro blocos: Financeiro, Vendas, Estoque e Clientes. Cada bloco só aparece, e só é calculado, para quem tem a permissão dele, então o Gerente abre a mesma tela e vê apenas Vendas e Estoque. Todos os números saem de dados que o sistema já grava; nada precisa ser digitado a mais.

Para começar, preciso de quatro decisões suas:

1. **Visão do Gerente.** Hoje o grupo Gerente tem acesso às telas do Financeiro. Proponho permissões próprias para os blocos do painel, assim o Gerente vê só Vendas e Estoque no painel sem perder as telas do Financeiro que já usa. Se preferir, o Gerente também pode perder as telas do Financeiro.
2. **Quem é "Administrativo".** Entendi como o grupo Administrador. O grupo Financeiro deveria ver o bloco Financeiro também?
3. **Pós-venda.** O sistema não guarda garantia, devolução, atendimento ou satisfação. Na primeira versão o bloco Clientes usa recompra, clientes parados e inadimplência. Pós-venda de verdade pede um cadastro novo (fase 4).
4. **Painel financeiro antigo.** Já existe uma tela em Financeiro > Dashboard. Proponho que o novo painel a substitua.

**Decisões do Eloi (27/10/2026):**

1. O Gerente mantém as telas do Financeiro e vê só Vendas e Estoque no painel.
2. O Administrativo é o grupo Administrador, e o grupo Financeiro também vê o bloco Financeiro.
3. O bloco Clientes começa sem pós-venda; devoluções de compras e de vendas serão tratadas depois.
4. Sim: aproveitar o dashboard antigo.

## Quem vê o quê

Cada bloco ganha uma permissão própria no app relatorios, cadastrada como as outras em `core/permissoes.py` e distribuída pelos grupos em `core/grupos.py`. A rota do painel abre para quem tem qualquer uma delas; quem não tem nenhuma continua vendo a página inicial atual.

| Bloco | Permissão nova | Administrador | Gerente | Financeiro | Compras/Estoque | Vendedor |
|---|---|---|---|---|---|---|
| 1. Financeiro | `relatorios.painel_financeiro` | Sim | Não | Sim (a confirmar) | Não | Não |
| 2. Vendas e Comercial | `relatorios.painel_vendas` | Sim | Sim | Não | Não | Não |
| 3. Operações e Estoque | `relatorios.painel_estoque` | Sim | Sim | Não | Sim | Não |
| 4. Clientes e Pós-Venda | `relatorios.painel_clientes` | Sim | Não | Não | Não | Não |

Margem, CMV e valor de estoque a custo continuam presos à permissão `comercial.ver_custos`, como já acontece nas outras telas. Os grupos podem ser ajustados depois no admin, sem mexer no código.

## Indicadores por área

São 6 a 8 números por bloco, cada um ligado a um campo que o sistema já tem. Todo cartão compara com o período anterior e, quando faz sentido, leva à tela de detalhe ao clicar.

### 1. Financeiro

| Indicador | Como é calculado | De onde vem |
|---|---|---|
| Saldo dos caixas | Saldo inicial + entradas − saídas, por caixa ativo | `Caixa`, `CaixaMovimento` |
| A receber em 7 e 30 dias | Títulos pendentes por vencimento | `FinanceiroReceber` |
| A pagar em 7 e 30 dias | Títulos pendentes por vencimento | `FinanceiroPagar` |
| Vencidos (receber e pagar) | Pendentes com vencimento antes de hoje, valor e quantidade | `FinanceiroReceber`, `FinanceiroPagar` |
| Fluxo de caixa projetado | Saldo de hoje + a receber − a pagar, dia a dia, 30 dias | as três acima |
| Resultado do mês | Receita, CMV, despesas e lucro por competência | `relatorios/services/dre_service.py` (o mesmo da DRE) |
| Despesas por grupo | Despesas do mês por grupo da DRE | `FinanceiroCategoria.grupo_dre` |
| Juros e multas pagos | Soma no mês, com link para o relatório de origem | `valor_juros`, `valor_multa` |

### 2. Vendas e Comercial

| Indicador | Como é calculado | De onde vem |
|---|---|---|
| Faturamento hoje e no mês | Total das vendas finalizadas, contra o mês anterior | `Venda.total`, `data_finalizacao` |
| Número de vendas e ticket médio | Quantidade e faturamento ÷ quantidade | `Venda` |
| Margem bruta (com `ver_custos`) | Total − CMV, em R$ e % | `Venda.cmv` |
| Produtos x serviços | Faturamento separado pelo tipo do item | `VendaItem.produto` / `servico` |
| Formas de pagamento | Faturamento por PIX, cartão, dinheiro, parcelado, à vista | `Venda.forma_pagamento` |
| Top 10 itens | Produtos e serviços que mais faturaram | `VendaItem` |
| Vendas por vendedor | Faturamento e quantidade por vendedor | `Venda.vendedor` |
| Descontos concedidos | Desconto da venda + desconto dos itens, no mês | `Venda.desconto`, `VendaItem.desconto` |
| Rascunhos abertos | Vendas iniciadas e não finalizadas | `Venda.status` |

### 3. Operações e Estoque

| Indicador | Como é calculado | De onde vem |
|---|---|---|
| Valor do estoque (com `ver_custos`) | Quantidade × preço médio | `Estoque` |
| Abaixo do mínimo | Lista dos produtos com saldo menor que o mínimo | `Estoque.quantidade`, `Produto.estoque_minimo` |
| Zerados ou negativos | Quantidade de produtos sem saldo | `Estoque` |
| Cobertura em dias | Saldo ÷ média diária de saídas dos últimos 90 dias | `MovimentacaoEstoque` |
| Produtos parados | Com saldo e sem saída há 90 dias, e quanto dinheiro está neles | `MovimentacaoEstoque` |
| Compras do mês | Valor das compras confirmadas | `Compra.valor_total` |
| Pendências de compra | Notas não confirmadas e itens importados ainda sem vínculo | `Compra.confirmada`, `CompraItem.status` |
| Preços a revisar | Quantos produtos estão na fila da Revisão de preços | `Produto`, `ConfiguracaoPreco` |

### 4. Clientes e Pós-Venda

| Indicador | Como é calculado | De onde vem |
|---|---|---|
| Clientes ativos | Compraram nos últimos 90 dias | `Venda.cliente` |
| Clientes novos no mês | Primeira venda do cliente caiu no mês | `Venda` (o cadastro não tem data de criação) |
| Taxa de recompra | Clientes com 2 ou mais compras ÷ clientes do período | `Venda` |
| Clientes parados | Compravam e não compram há 90 dias, com telefone para contato | `Venda`, `Contato.telefone` |
| Curva ABC de clientes | Top 10 e quanto do faturamento eles somam | `Venda` |
| Inadimplência | Receber vencido ÷ total em aberto, e maiores devedores | `FinanceiroReceber` |
| Atraso médio de recebimento | Dias entre vencimento e pagamento dos títulos pagos | `FinanceiroReceber.data_pagamento` |

Antes de ligar o bloco de Estoque vale corrigir os 22 produtos com saldo duplicado (comando `verificar_estoque`), senão o valor do estoque já nasce errado. O fornecedor CONDUSVALE duplicado também distorce rankings, e o Unificar contatos resolve.

## Layout da tela

Uma página só, de cima para baixo: filtro de período, faixa de alertas e os blocos que o usuário pode ver. Cada bloco tem uma linha de 4 cartões (o número grande e a comparação com o período anterior) e embaixo um gráfico largo e uma lista curta.

```
+------------------------------------------------------------------+
| Painel        [Hoje] [7 dias] [Mês] [Mês anterior] [12 meses]     |
+------------------------------------------------------------------+
| Atenção: 3 títulos vencidos · 5 produtos abaixo do mínimo · ...   |
+------------------------------------------------------------------+
| 1. FINANCEIRO                                                     |
| [Saldo caixas] [A receber 30d] [A pagar 30d] [Vencidos]           |
| [ gráfico largo ................. ] [ lista curta ]               |
+------------------------------------------------------------------+
| 2. VENDAS       (mesma estrutura: 4 cartões, gráfico, lista)      |
| 3. ESTOQUE      (idem)                                            |
| 4. CLIENTES     (idem)                                            |
+------------------------------------------------------------------+
```

No celular os cartões descem em duas colunas e os gráficos ficam um embaixo do outro. A faixa de alertas reúne só o que pede ação hoje e mostra apenas os alertas dos blocos que o usuário enxerga. Os blocos que o Gerente vê ficam no topo para ele; para o Administrador a ordem pode ser Financeiro primeiro.

## Gráficos

Uso o Chart.js, com o arquivo guardado dentro do projeto (`core/static/vendor/`), para o painel funcionar sem internet. As cores vêm das variáveis do `masc_tema.css` (verde, petróleo, âmbar, vermelho), e vermelho fica reservado para o que está atrasado ou negativo.

| Gráfico | Tipo | Por quê |
|---|---|---|
| Faturamento por dia | Linha, mês atual sobre o mês anterior | Mostra se o mês está à frente ou atrás no mesmo dia |
| Top 10 itens e Top 10 clientes | Barras horizontais | Nomes longos de produto cabem melhor deitados |
| Formas de pagamento e produtos x serviços | Barra empilhada única (100%) | Lê-se melhor que pizza com 5 fatias |
| Fluxo de caixa projetado | Linha do saldo com faixa vermelha abaixo de zero | Mostra o dia em que o caixa aperta |
| Resultado do mês | Cascata: receita, CMV, despesas, lucro | É a DRE em um olhar |
| Despesas por grupo | Barras horizontais | Compara grupos da DRE |

Listas (abaixo do mínimo, parados, clientes parados, vencidos) ficam em tabelas curtas de até 10 linhas, com link "ver todos" para a tela que já existe.

## Desempenho

A meta é a tela abrir em menos de 1 segundo no SQLite atual, com cerca de 20 consultas para o Administrador e 10 para o Gerente.

- **Um serviço por bloco.** Um arquivo `relatorios/services/painel.py` com uma função por bloco (`bloco_vendas(periodo)`, `bloco_estoque()`...). A tela só chama as funções dos blocos que o usuário pode ver, então o Gerente nunca dispara as consultas do Financeiro.
- **Contas no banco, não em Python.** Somas e contagens com `aggregate`, `annotate`, `Sum`, `Count` e `TruncDay`, uma consulta por indicador, em vez de percorrer vendas uma a uma.
- **Reaproveitar o que existe.** O Resultado do mês chama o mesmo `dre_service` da DRE, assim os dois sempre batem.
- **Cache de 5 minutos.** Cada bloco fica guardado por período no cache do Django (memória local, sem instalar nada). O botão Atualizar ignora o cache, e a tela mostra a hora do cálculo.
- **Índices.** Três índices novos numa migração: `Venda (status, data_finalizacao)`, títulos `(status, data_vencimento)` e `MovimentacaoEstoque (produto, data)`.
- **Sem API extra.** Os dados dos gráficos vão na própria página com `json_script`; não há chamadas depois que a tela carrega.
- **Testes.** Cada função do serviço ganha teste com dados conhecidos, e o teste de permissões confere que o Gerente não recebe o bloco Financeiro.

## Fases

A visão do Gerente fica pronta primeiro, porque Vendas e Estoque são os blocos mais usados no dia a dia. Cada fase é entregue, testada e gravada no seu PC antes da próxima.

1. **Base + Vendas + Estoque (visão do Gerente).** Rota do painel, 4 permissões novas, filtro de período, alertas, cache, índices, Chart.js local, blocos 2 e 3. Antes disso, corrigir os saldos duplicados de estoque.
2. **Financeiro.** Bloco 1 com fluxo projetado e resultado do mês, e a saída do painel financeiro antigo.
3. **Clientes.** Bloco 4 com recompra, clientes parados, curva ABC e inadimplência.
4. **Extras, se quiser.** Meta de faturamento mensal com barra de progresso; registro de pós-venda (garantia, devolução, contato feito) para alimentar o bloco 4 de verdade.

---

## O que foi implementado (27 e 28/10/2026)

As quatro fases foram entregues. O detalhe de cada uma, com os arquivos alterados, está no `CORRECOES.md`. Onde a implementação ficou diferente da proposta:

- **Fase 1** juntou o bloco Financeiro (que aproveitou o dashboard antigo) às Vendas e ao Estoque. O endereço antigo `financeiro/dashboard/` leva ao Painel. As datas das vendas seguem a data de emissão, como na DRE, e o índice de vendas ficou em `(status, data_emissao)`. A margem usa o CMV dos itens (`CMVItem`). Os saldos de estoque em dobro foram corrigidos com o comando `corrigir_saldos_estoque`.
- **Fase 2:** o fluxo de caixa projetado cobre 90 dias, com tabela em 30, 60 e 90 dias, e os títulos vencidos ficam fora da projeção. O resultado segue o período escolhido (não só o mês), em cartões (receita líquida, lucro bruto, despesas operacionais, lucro líquido) em vez de cascata, e só aparece para quem pode ver a DRE.
- **Fase 3:** a recompra conta os clientes do período que já compraram mais de uma vez, no período ou antes. A curva ABC usa A até 80% do faturamento, B até 95% e C o resto, em tabela.
- **Fase 4:** telas de Metas de faturamento e de Pós-venda (contato, garantia, reclamação e pedido de devolução, com data de retorno). O pedido de devolução é só o registro: a devolução de compras e de vendas, que mexe no estoque e no financeiro, fica para depois.
- **Ficaram de fora:** despesas por grupo, juros e multas no Painel (estão na DRE e no relatório de juros e multas) e os gráficos de barras dos Top 10 (ficaram em tabelas).
