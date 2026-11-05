# Proposta: Devolução de Vendas e Devolução de Compras

Gestão MASC · 28/10/2026 · **Somente proposta, nada foi implementado.**

## 1. O que existe hoje e por que não basta

- **Venda:** só existe o *estorno total* (`estornar_venda`). Ele cancela a venda inteira, devolve todo o estoque, apaga o CMV e os títulos, e é bloqueado se alguma parcela já foi recebida. Não serve para "o cliente devolveu 1 de 3 itens um mês depois".
- **Compra:** só existe desfazer a confirmação (`marcar_estornada`). Não há como devolver parte da mercadoria ao fornecedor.
- **Pós-venda:** o tipo "Devolução" do Pós-venda é só um registro, sem efeito no estoque nem no financeiro.
- **Painel e DRE:** não enxergam devoluções. Hoje a receita bruta fica inflada e o CMV fica maior do que o real quando há devolução.

A ideia é manter o **estorno** para erro de digitação (a venda "nunca existiu") e criar a **devolução** para o fato real: a venda existiu, e depois parte ou toda a mercadoria voltou.

## 2. Modelo de dados (app `comercial`)

**`Devolucao`** (cabeçalho, serve para os dois tipos)

| Campo | Uso |
|---|---|
| `tipo` | `VENDA` (cliente devolve) ou `COMPRA` (devolvemos ao fornecedor) |
| `venda` / `compra` | documento de origem (um dos dois) |
| `contato` | cliente ou fornecedor |
| `data` | data da devolução (competência no DRE) |
| `motivo` | defeito, avaria no transporte, erro de pedido, arrependimento (CDC art. 49), garantia, outro |
| `observacao` | texto livre |
| `status` | rascunho, confirmada, cancelada |
| `acerto` | como o dinheiro foi acertado (ver seção 4) |
| `valor_total`, `valor_custo` | calculados pelos itens |
| `nf_numero`, `nf_chave`, `xml_nfe` | NF-e de devolução (seção 6) |
| `usuario`, `criado_em` | auditoria |

**`DevolucaoItem`**

| Campo | Uso |
|---|---|
| `venda_item` / `compra_item` | item de origem |
| `produto` | produto (serviço não movimenta estoque) |
| `quantidade` | limitada a: quantidade original menos o que já foi devolvido |
| `preco_unitario` | preço líquido de desconto do item original (rateio do desconto da venda) |
| `custo_unitario` | venda: custo do `CMVItem` original. Compra: `custo_unitario_estoque` do item da compra |
| `volta_estoque` | sim (padrão) ou não, para produto sem condição de revenda |

Uma venda ou compra pode ter **várias devoluções parciais**, até zerar.

## 3. Estoque

**Devolução de venda:** `MovimentacaoEstoque` de **ENTRADA**, origem `DEVOLUCAO_VENDA`, ao **custo do CMV original** (não ao preço de venda). Assim o preço médio volta ao que era e a margem fica correta.

**Devolução de compra:** `MovimentacaoEstoque` de **SAÍDA**, origem `DEVOLUCAO_COMPRA`, ao **custo da compra original**. Aqui é preciso um ajuste: hoje uma SAÍDA não mexe no preço médio, mas tirar do estoque uma mercadoria pelo seu custo de entrada precisa recalcular a média (como se aquela entrada não tivesse acontecido). O `save()` e o `recalcular_preco_medio()` passam a tratar essa origem. Se o saldo for menor que a quantidade devolvida (produto já vendido), a tela bloqueia.

**Produto sem condição de revenda** (`volta_estoque = não`): entra e sai na mesma hora como perda (ENTRADA de devolução + SAÍDA "PERDA"), e o custo vai para uma despesa "Perdas de estoque". Fica rastreável e não deixa estoque fantasma.

## 4. Financeiro

**Devolução de venda.** O sistema mostra quanto o cliente ainda deve da venda e propõe o acerto, nesta ordem:

1. **Abater das parcelas pendentes** da venda (das últimas para as primeiras). Parcela abatida por inteiro fica `cancelado`; a parcial tem o valor reduzido, com observação.
2. O que sobrar (cliente já pagou), à escolha na tela:
   - **Reembolso agora:** `CaixaMovimento` de saída, origem nova `DEVOLUCAO`.
   - **Crédito do cliente:** um `FinanceiroPagar` ao cliente, origem nova `DEVOLUCAO`. Pode ser pago depois ou usado para abater uma próxima venda.

**Devolução de compra.** Mesma lógica, invertida:

1. **Abater das duplicatas pendentes** da compra.
2. O que sobrar (já pagamos o fornecedor): **reembolso** (`CaixaMovimento` de entrada) ou **crédito com o fornecedor** (`FinanceiroReceber` do fornecedor, origem `DEVOLUCAO`).

Tudo usa os serviços que já existem (`quitar_titulo` e `estornar_quitacao`), sem caminho paralelo.

**Cancelar uma devolução** desfaz tudo: o movimento de estoque recebe estorno, os títulos voltam ao valor original e o caixa recebe o lançamento inverso. Isso só é permitido se o crédito ou reembolso gerado ainda não foi usado.

## 5. DRE e CMV (regime de competência, pela data da devolução)

| Linha do DRE | Efeito |
|---|---|
| Receita bruta | **não muda** (a venda aconteceu) |
| **(−) Devoluções de vendas** | nova linha em Deduções, soma de `valor_total` das devoluções de venda no período |
| CMV | CMV das vendas **menos** o custo das devoluções de venda no período |
| Despesas | "Perdas de estoque" quando o item não volta ao estoque |
| Devolução de compra | **não entra no DRE**: só reduz estoque e contas a pagar (a compra também não entra) |

Assim, se a venda é de setembro e a devolução de outubro, setembro não muda (relatório já fechado) e outubro mostra a dedução. Esse é o tratamento contábil padrão.

## 6. Fiscal (NF-e de devolução)

| Situação | Quem emite a NF-e | CFOP (mercadoria de revenda) |
|---|---|---|
| Cliente **pessoa física** devolve | **a empresa** emite NF-e de **entrada** | 1.202 (mesmo estado) / 2.202 (outro estado). Com ST: 1.411 / 2.411 |
| Cliente **empresa (CNPJ)** devolve | **o cliente** emite NF-e de devolução; nós só registramos | 5.202 / 6.202 na nota dele |
| **Nós** devolvemos ao fornecedor | **a empresa** emite NF-e de **saída** | 5.202 / 6.202. Com ST: 5.411 / 6.411 |

A NF-e de devolução tem finalidade 4 (`finNFe=4`), referencia a chave da nota original e devolve proporcionalmente o ICMS, ICMS-ST e IPI destacados. Na compra, os créditos de impostos já registrados na importação do XML são estornados na mesma proporção.

Como o sistema ainda não emite NF-e (o módulo fiscal está planejado, mas não foi implementado), a proposta é:

- **Agora:** guardar número e chave da NF-e de devolução emitida no emissor que você já usa, e permitir **importar o XML** dela (reaproveitando o importador de compras) para conferir quantidades e valores.
- **Depois, junto com o módulo fiscal:** emitir a NF-e de devolução direto da tela.

Os CFOPs e o tratamento de ICMS dependem do regime tributário e da UF. Vale confirmar com o contador antes de usar.

## 7. Telas

- **Venda (detalhe)** e **Compra (detalhe)**: botão **"Registrar devolução"**, visível quando a venda está finalizada ou a compra confirmada.
- **Tela da devolução:** lista os itens do documento com a quantidade ainda devolvível, e você digita quanto volta. Escolhe motivo, "volta ao estoque?" e o acerto financeiro. Antes de confirmar, aparece um **resumo do impacto** (estoque, títulos abatidos, reembolso ou crédito, valor no DRE).
- **Comercial → Devoluções:** lista com filtros (tipo, período, contato, motivo), detalhe e botão "Cancelar devolução".
- **Pós-venda:** o registro do tipo "Devolução" ganha um link "Registrar devolução", e a devolução fica ligada a ele.
- **Venda e compra:** mostram "Devolvido: R$ X" e as devoluções ligadas. Uma venda com devolução não pode mais ser estornada (o estorno total iria duplicar a volta ao estoque).
- **Avisos, não bloqueios:** devolução de venda com mais de 7, 30 ou 90 dias mostra um aviso, sem impedir o registro.

**Permissões:** `comercial.add_devolucao` / `view_devolucao` / `change_devolucao`, distribuídas aos grupos como você decidir.

## 8. Painel

- **Bloco Vendas:** cartão **"Devoluções"** com valor no período, **% do faturamento** e comparação com o período anterior. O faturamento passa a mostrar também o **líquido** (bruto menos devoluções), e a margem desconta o custo devolvido.
- **Bloco Clientes:** taxa de devolução por cliente, top motivos e clientes com mais devoluções.
- **Bloco Estoque:** devoluções a fornecedor no período e perdas.
- **Bloco Resultado:** já vem certo, porque usa o DRE.

## 9. Etapas sugeridas

1. **Base e devolução de venda:** modelos, migração, estoque (ENTRADA ao custo do CMV), tela, lista e permissões.
2. **Financeiro da venda:** abatimento de parcelas, reembolso ou crédito, cancelamento da devolução.
3. **Devolução de compra:** SAÍDA com recálculo do preço médio, abatimento de duplicatas, crédito com o fornecedor.
4. **DRE e Painel:** linha de dedução, CMV líquido e cartões do painel.
5. **Fiscal:** número, chave e importação do XML da NF-e de devolução. A emissão fica para o módulo fiscal.

Cada etapa vem com testes, e o registro em CORRECOES.md segue o padrão das anteriores.

## 10. Decisões para você

1. **Venda já paga:** oferecer **reembolso e crédito do cliente** na tela (recomendado) ou só um dos dois?
2. **Produto com defeito:** baixar como **perda** quando não volta ao estoque (recomendado), ou sempre voltar ao estoque?
3. **Quem registra devolução de venda:** só **Gerente e Administrador** (recomendado), ou o Vendedor também?
4. **NF-e:** por enquanto **só registrar número, chave e XML** (recomendado), deixando a emissão para o módulo fiscal?
5. **Ordem:** começar pela **devolução de venda** (etapas 1, 2 e 4) e depois fazer a de compra (recomendado)?
