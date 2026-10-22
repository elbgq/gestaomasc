# Revisão do módulo financeiro

*19/10/2026. Revisão do código em `financeiro/` e das partes de `comercial/` que lançam no financeiro. Os itens marcados **(confirmado)** foram reproduzidos numa cópia do seu banco; os demais vêm da leitura do código. Nada foi alterado ainda.*

## Resumo

O desenho geral está certo: o lançamento gera o título (a pagar ou a receber), a quitação gera o movimento de caixa e o DRE lê os lançamentos. Os problemas estão na execução: **4 telas dão erro**, há **dois caminhos de quitação que gravam de jeitos diferentes**, a **exclusão e a edição não protegem títulos pagos**, e **cada tela calcula o saldo de um jeito**.

## A. Telas que dão erro

| # | Problema | Onde |
|---|---|---|
| 1 | **Painel financeiro** dá erro sempre: filtra por `esta_pago`, que é um método e não um campo do banco **(confirmado)** | `financeiro/views_caixa.py:260` e `:266` |
| 2 | **"Pagar" em Contas a Pagar** dá erro em qualquer título pendente: a tela aponta para `pagar_list`, rota que não existe **(confirmado)** | `financeiro/templates/financeiro/pagar_quitacao.html:30` |
| 3 | **Tela do caixa dá erro depois de abrir o caixa**: os botões Fechar, Sangria e Reforço apontam para rotas que não existem. As funções existem, mas não estão no `urls.py`. Na prática, não há como fechar o caixa nem lançar sangria ou reforço **(confirmado)** | `financeiro/templates/financeiro/caixa_detalhe.html:25-34`; funções em `financeiro/views_caixa.py:36`, `:72`, `:91` |
| 4 | **Nova conta a receber** e **editar conta a receber** dão erro: falta `{% load widget_tweaks %}` no template **(confirmado)** | `financeiro/templates/financeiro/receber_form.html` |

## B. Dados que ficam inconsistentes

| # | Problema | Onde |
|---|---|---|
| 5 | **Excluir um lançamento não exclui o título dele**, mesmo se já pago. O código de exclusão nunca roda (no Django 4+ a exclusão passa por `form_valid`, não por `delete`) e usa campos que não existem (`lanc.tipo`, `referencia_id`). Na cópia do banco, excluí o lançamento 17 e o título 7 continuou lá **(confirmado)** | `financeiro/views_lancamento.py:194` |
| 6 | **Qualquer conta a receber pode ser excluída**, inclusive de venda e já recebida. A trava tem o mesmo defeito do item 5 e ainda compara com `"Manual"` em vez de `"MANUAL"` **(confirmado com um título de venda)** | `financeiro/views_receber.py:95` |
| 7 | **Editar título já pago muda o valor sem mexer no caixa**: conta a pagar manual, conta a receber e lançamento. No lançamento, trocar a categoria de despesa para receita deixa o título a pagar antigo e não cria o a receber | `financeiro/views_contas_pagar.py:20`, `financeiro/views_receber.py:88`, `financeiro/views_lancamento.py:142` e `:175` |
| 8 | **Excluir título manual já pago deixa a saída no caixa** | `financeiro/views_contas_pagar.py:41` |
| 9 | **Duas rotinas de quitação que gravam diferente.** "Pagar" em Contas a Pagar liga o movimento de caixa ao título e não confere saldo; "Quitar" em Títulos confere saldo, mas **não liga o movimento ao título** (no seu banco: 6 contas pagas e 5 recebidas sem esse vínculo) e grava a data em horário UTC, então uma quitação depois das 21h fica com a data do dia seguinte | `financeiro/views_contas_pagar.py:226` × `financeiro/views_titulos.py:75`, `:125` |
| 10 | **Movimentos de caixa sem caixa**: a entrada (sinal) da venda e o movimento manual não informam o caixa. Eles não entram no saldo do Caixa Principal, mas aparecem no histórico e no painel. Hoje não há nenhum no seu banco, mas vai acontecer no primeiro uso | `comercial/views/views_vendas.py:314`, `financeiro/views_caixa.py:194` |
| 11 | **Abertura e fechamento de caixa**: dá para abrir o mesmo caixa duas vezes **(confirmado)**; o valor de abertura não entra no saldo; sangria e reforço não validam o valor (vazio ou negativo); o fechamento calcula a diferença com `float` | `financeiro/views_caixa.py:16`, `:50`, `:72`, `:91` |
| 12 | **Estorno de venda com entrada (sinal)**: o código apaga a entrada do caixa **e** lança uma saída, descontando duas vezes. Hoje isso não chega a acontecer porque a trava do início bloqueia o estorno de toda venda com entrada (a entrada já nasce como título recebido), ou seja, venda com sinal nunca pode ser estornada | `comercial/views/views_vendas.py:415` e `:438-450` |

## C. Cálculos e relatórios

| # | Problema | Onde |
|---|---|---|
| 13 | **O saldo muda conforme a tela**: o caixa soma saldo inicial + movimentos daquele caixa; o histórico e o painel ignoram o saldo inicial e somam movimentos de todos os caixas e sem caixa | `financeiro/models.py` (`Caixa.saldo_atual`), `financeiro/views_caixa.py:169` e `:241` |
| 14 | **Totais de Contas a Pagar somam pagas e pendentes** ("Total de contas"), sem mostrar quanto falta pagar. Os filtros "hoje" e "amanhã" incluem títulos pagos e cancelados; "vencidos" ignora o status cancelado | `financeiro/views_contas_pagar.py:68-72`, `:92-96` |
| 15 | **Gráfico de 6 meses do painel pula mês**: volta de 30 em 30 dias; em março, por exemplo, fevereiro some | `financeiro/views_caixa.py:277` |
| 16 | **DRE só lê lançamentos**: contas a pagar e a receber criadas direto (manuais) não entram no resultado | `relatorios/services/dre_service.py:43` |
| 17 | **Quitação sempre pelo valor cheio**: não há juros, multa, desconto nem pagamento parcial | `financeiro/views_contas_pagar.py:236`, `financeiro/views_titulos.py:124` |

## D. Código sem uso

`registrar_financeiro_compra`, `gerar_financeiro_pagar_da_compra` e `estornar_financeiro_pagar` (`financeiro/views_contas_pagar.py:123-212`), `receber_titulo` (`financeiro/views_receber.py:109`, que daria erro por usar campos inexistentes) e os templates `pagar_list.html`, `pagar_form.html` e `pagar_confirm_delete.html` não estão ligados a nenhuma rota. Podem ser removidos para não confundir.

## Proposta de correção

1. **Telas (itens 1 a 4).** Correções pequenas, sem mudar dados.
2. **Uma única rotina de quitação** usada pelas duas telas: liga o movimento ao título, usa a data local, grava no Caixa Principal e tudo dentro de uma transação. Inclui o estorno de quitação, para desfazer um pagamento lançado errado.
3. **Travas**: título pago não pode ser editado nem excluído (é preciso estornar a quitação antes); excluir lançamento exclui o título dele; conta a receber de venda só sai pela venda.
4. **Caixa**: ligar fechamento, sangria e reforço; impedir duas aberturas; validar valores; todo movimento com caixa; um único cálculo de saldo para caixa, histórico e painel.
5. **Relatórios**: totais de Contas a Pagar separados em pago e em aberto, filtros respeitando o status, gráfico por mês do calendário.
6. **Estorno de venda com entrada** feito corretamente.
7. Um comando para ligar os 11 títulos já quitados aos movimentos de caixa correspondentes.

Ficam para depois (Fase 2 do README): juros, multa, desconto e pagamento parcial (item 17), e incluir títulos manuais no DRE (item 16), que depende de decidir se o DRE é por competência (data do lançamento) ou por caixa.
