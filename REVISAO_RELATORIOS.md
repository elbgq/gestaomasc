# Revisão do módulo Relatórios

*20/10/2026. Revisão do código em `relatorios/` e dos dados que os relatórios leem. Os itens marcados **(confirmado)** foram conferidos numa cópia do seu banco de hoje; os demais vêm da leitura do código. Nada foi alterado ainda.*

## Resumo

O DRE já foi revisado e está coerente (competência, títulos manuais, juros e descontos). Os problemas estão nos outros três relatórios. **Compras por Período soma errado**, porque ignora frete, impostos e descontos da nota. **Vendas e CMV não seguem as mesmas regras do DRE**, então os números podem não bater entre si. E há **erros de tela**: o filtro de fornecedor não aparece e o número da nota sai errado.

## A. Valores errados

| # | Problema | Onde |
|---|---|---|
| 1 | **Compras por Período soma só quantidade × preço** e ignora frete, seguro, outras despesas, IPI, ICMS-ST e desconto da nota. No seu banco o relatório mostra **R$ 16.141,33**, mas as duas compras somam **R$ 15.687,62** (a diferença é quase toda o desconto de R$ 453,94 da compra 8) **(confirmado)** | `relatorios/services/compras_service.py:17` e `:30` |
| 2 | **Compras por Período inclui compras não confirmadas** (importadas e ainda sem vínculo, ou em rascunho). Hoje as duas estão confirmadas | `relatorios/services/compras_service.py:5` |
| 3 | **Vendas por Período inclui rascunhos e vendas canceladas**; o DRE conta só as finalizadas. Com uma venda cancelada no período, os dois relatórios dão valores diferentes | `relatorios/services/vendas_service.py:5` |
| 4 | **Total geral de Vendas ignora o desconto do item**, mas cada linha mostra o valor com desconto, então a soma das linhas não bate com o total. Hoje nenhum item tem desconto | `relatorios/services/vendas_service.py:35` |
| 5 | **CMV - Relatório perde o último dia do período**: filtra um campo de data e hora com uma data, então vendas feitas depois da meia-noite do último dia ficam de fora. É o mesmo erro já corrigido no DRE e em Vendas | `relatorios/views/cmv.py:8` e `:11` |
| 6 | **Desconto e acréscimo da venda são aceitos na tela mas não entram no total.** O formulário da venda mostra os campos, mas o total (e com ele as contas a receber, Vendas por Período e o DRE) soma só os itens. Hoje nenhuma venda usa esses campos. A correção é no módulo comercial | `comercial/models.py:409` (`Venda.atualizar_total`) |

## B. Telas

| # | Problema | Onde |
|---|---|---|
| 7 | **Filtro de fornecedor não aparece em Compras por Período**: a tela procura o campo `contato`, e o formulário chama `fornecedor` **(confirmado)** | `relatorios/templates/relatorios/compras/por_periodo.html:17` |
| 8 | **Número da nota sai errado em Compras**: a tela converte o número em inteiro e mostra "C000000" quando não consegue. A compra 7 aparece como C000000 porque o número gravado é "IMPORTADA" e ela não tem o XML guardado (foi importada antes da correção da importação) **(confirmado)** | `comercial/models.py:69` (`Compra.numero_formatado`), dado da compra 7 |
| 9 | **Filtros de fornecedor e de cliente listam todos os contatos** (clientes aparecem como fornecedores e vice-versa) | `relatorios/forms.py:17` e `:41` |
| 10 | **DRE aceita data inicial depois da final** e mostra tudo zerado, sem aviso **(confirmado)**. Vendas, Compras e CMV têm o mesmo comportamento | `relatorios/forms.py` |

## C. DRE

| # | Problema | Onde |
|---|---|---|
| 11 | **Risco de CMV em dobro**: as categorias "CMV" e "CSP" estão no grupo Despesas com Vendas. Um lançamento numa delas soma ao CMV que o DRE já calcula das vendas. Hoje nenhum lançamento usa essas categorias | categorias 3 e 4 do seu cadastro |

## D. Código sem uso

- `relatorios/services/cmv_service.py` e `relatorios/templates/relatorios/cmv/por_periodo.html` não são usados (a tela do CMV faz a própria consulta e usa outro template). O serviço filtra pela data da venda; a tela, pela data do CMV.
- Oito templates estão vazios e sem rota: vendas por cliente e por produto, compras por fornecedor e por produto, contas a pagar e a receber, curva ABC e giro de estoque. Eles estão previstos na **Fase 5** do README.
 
## Proposta de correção

1. **Valores (itens 1 a 5)**: Compras soma o valor da nota de cada item e só compras confirmadas; Vendas só finalizadas e com o mesmo total das linhas; CMV inclui o último dia. Uma única consulta por relatório, usada pela tela e pelo total.
2. **Telas (itens 7 a 10)**: filtro de fornecedor visível, número da nota como foi gravado, filtros só com fornecedores ou só com clientes, e aviso quando a data inicial é maior que a final.
3. **Venda (item 6)**: aplicar desconto e acréscimo da venda no total, ou tirar os campos da tela. Depende do que você prefere.
4. **CMV em dobro (item 11)**: avisar no DRE quando houver lançamento em categoria de CMV, ou tirar essas categorias do grupo Despesas com Vendas.
5. **Limpeza**: remover o serviço e o template do CMV sem uso. Os relatórios da Fase 5 ficam para quando a fase começar.
