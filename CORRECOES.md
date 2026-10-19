# Correções aplicadas (10/10/2026)

Cada problema abaixo foi primeiro reproduzido por um teste automatizado que falhava no código anterior e passa agora. Para rodar os testes:

```bash
python manage.py test comercial financeiro relatorios
```

Depois de copiar os arquivos, rode `python manage.py migrate` (há uma migração nova, `comercial/migrations/0005_compraitem_quantidade_decimal.py`).

---

## Importação de NF-e: dados fiscais (etapa C, 19/10/2026)

Rode `python manage.py migrate` (migrações novas: `cadastros/migrations/0003_dados_fiscais.py` e `comercial/migrations/0009_dados_fiscais.py`) e depois, uma vez, `python manage.py reprocessar_fiscal_nfe` para preencher as compras já importadas.

| O que mudou | Onde |
|---|---|
| Cada item importado guarda CFOP, CEST, origem, CST/CSOSN do ICMS, base e alíquota do ICMS, base do ICMS-ST, alíquota do IPI e CST do PIS e da COFINS | `comercial/models.py` (`CompraItem`), `comercial/services/xml_importer.py` (`_dados_fiscais`) |
| Produto criado pela nota recebe também o CEST; cadastro de produto ganhou o campo | `cadastros/models.py`, `cadastros/forms.py`, `comercial/views/views_compras.py` (`criar_produto_do_item`) |
| Detalhe da compra mostra a chave de acesso, o botão "Baixar XML" e NCM, CFOP, CST, ICMS, IPI e ST por item | `comercial/templates/comercial/compras_detalhe.html`, `comercial/views/views_compras.py` (`compra_xml`) |
| Comando que relê o XML guardado e preenche os dados fiscais das compras antigas, sem mexer em valores, estoque ou financeiro | `comercial/management/commands/reprocessar_fiscal_nfe.py` |
| 5 testes novos | `comercial/tests.py` (`ImportacaoXmlFiscalTests`) |
| Total do item passa a ser o valor dos produtos da nota (vProd); antes o arredondamento de quantidade × preço podia deixar o total 1 centavo diferente da nota e esconder a opção das duplicatas | `comercial/services/xml_importer.py` (`_usar_total_da_nota`) |
| Comando para corrigir compra importada antes da etapa B: recalcula total, custo das entradas, custo médio atual dos produtos e parcelas pendentes. Sem `--aplicar` só mostra o que mudaria | `comercial/management/commands/corrigir_compra_nfe.py` |

Para a compra 8: `python manage.py corrigir_compra_nfe 8` (confere) e depois `python manage.py corrigir_compra_nfe 8 --aplicar` (grava).

---

## Importação de NF-e: custo e duplicatas (etapa B, 19/10/2026)

Rode `python manage.py migrate` (migração nova: `comercial/migrations/0007_importacao_nfe_custos_duplicatas.py`).

**Regime tributário:** no `.env`, `COMPRA_CREDITOS` diz quais tributos a empresa recupera como crédito e por isso saem do custo do estoque. Simples Nacional: deixe sem a linha. Lucro Presumido: em geral `COMPRA_CREDITOS=ICMS`. Lucro Real: em geral `COMPRA_CREDITOS=ICMS,PIS,COFINS` (indústria que credita IPI acrescenta `IPI`). Confirme com o contador.

| O que mudou | Onde |
|---|---|
| Lê de cada item frete, seguro, outras despesas, desconto, IPI, ICMS-ST + FCP-ST, ICMS, PIS e COFINS | `comercial/services/xml_importer.py:99`, `comercial/models.py:109` |
| Total da compra (e das contas a pagar) passa a ser o total da nota: produtos + despesas + IPI + ST − desconto; aviso se não bater com o total da NF-e | `comercial/models.py:139`, `comercial/services/xml_importer.py:259` |
| Custo no estoque = total do item na nota − créditos do regime, dividido pela quantidade convertida | `comercial/models.py:154` |
| Duplicatas da nota gravadas na compra; na confirmação, a opção "Conforme as duplicatas da nota" gera as contas a pagar com os vencimentos e valores do fornecedor (só aparece quando as duplicatas somam o total) | `comercial/models.py:169` (`CompraDuplicata`), `comercial/views/views_compras.py:285` |
| Tela de confirmação mostra total do item na nota, custo unitário no estoque e as duplicatas | `comercial/templates/comercial/compras_confirmar.html` |
| Finalizar à vista pela tela de confirmação podia ser barrado pelo navegador (campo de data oculto obrigatório) | `comercial/templates/comercial/compras_confirmar.html` |
| 7 testes novos | `comercial/tests.py` (`ImportacaoXmlCustoTests`) |
| Produto criado pela nota ficava sem código de origem (`codor`), por isso aparecia em branco no estoque; agora recebe o código do fornecedor, e a migração `0008` preenche os produtos já criados | `comercial/views/views_compras.py` (`criar_produto_do_item`), `comercial/migrations/0008_preencher_codor_produtos_importados.py` |

Compras lançadas à mão continuam iguais (sem despesas, o total é a soma dos produtos).

---

## Importação de NF-e do fornecedor (etapa A, 19/10/2026)

Depois de copiar os arquivos, rode `python manage.py migrate` (migrações novas: `cadastros/migrations/0002_produto_ean_produto_ncm.py` e `comercial/migrations/0006_importacao_nfe.py`). Opcional: coloque `EMPRESA_CNPJ=00000000000000` (só números) no `.env` para recusar notas emitidas para outro CNPJ.

Como usar: **Compras → Importar**, envie o XML da nota autorizada → confira a tela de vínculo (escolha o produto, "Criar produto novo" ou ajuste o **Fator**, ex.: 50 se 1 CX = 50 UN) → **Confirmar Compra** → à vista ou parcelado.

| O que mudou | Onde |
|---|---|
| Importação dava erro sempre (buscava o fornecedor por `cnpj`, campo que não existe); agora busca por `documento`, com ou sem pontuação, e cria o fornecedor com tipo "Fornecedor" | `comercial/services/xml_importer.py:31` |
| Só aceita nota autorizada (com protocolo da SEFAZ), recusa homologação e, com `EMPRESA_CNPJ`, nota de outro destinatário | `comercial/services/xml_importer.py:121` a `:155` |
| Chave de acesso gravada na compra e usada para bloquear nota repetida; XML guardado junto | `comercial/models.py:23`, `comercial/services/xml_importer.py:158` |
| Item guarda código do fornecedor, EAN, NCM e unidade da nota | `comercial/models.py:97` |
| Vínculo automático: pelo vínculo já gravado do fornecedor, ou pelo código de barras | `comercial/services/xml_importer.py:48` (`sugerir_vinculo`) |
| Vínculo código do fornecedor → produto gravado para as próximas notas (tabela nova, também no admin) | `comercial/models.py:133` (`ProdutoFornecedor`), `comercial/views/views_compras.py:676` |
| Fator de conversão: estoque recebe quantidade × fator e custo ÷ fator | `comercial/models.py:123`, `comercial/views/views_compras.py:693` (`registrar_compra`) |
| Criar produto novo direto do item da nota (descrição, unidade, EAN, NCM) | `comercial/views/views_compras.py:665` |
| Tela de vínculo refeita (mostrava `compra.contato`, que não existe, e o modal de produto não funcionava); compra finalizada não pode ser revinculada | `comercial/templates/comercial/vincular_itens.html`, `comercial/views/views_compras.py:578` |
| Tela de confirmação mostra o produto e quanto entra no estoque | `comercial/templates/comercial/compras_confirmar.html` |
| Preço unitário do item com 4 casas, para o total bater com a nota | `comercial/models.py:95` |
| Produto ganhou EAN e NCM no cadastro | `cadastros/models.py:30`, `cadastros/forms.py:10` |
| 13 testes novos com XMLs de exemplo | `comercial/tests.py` (`ImportacaoXmlTests`) |

---

## Ação necessária: estoque já gravado em dobro

A finalização de compra somava cada item **duas vezes** no estoque. Numa cópia do seu banco, 22 produtos têm saldo diferente do histórico de movimentações (a maioria exatamente o dobro). Para ver a lista:

```bash
python manage.py verificar_estoque
```

O comando só mostra as diferenças, não altera nada. As compras novas já entram certas; os saldos antigos precisam ser ajustados por você (por inventário ou recalculando a partir das movimentações).

---

## Compras

| Problema | Onde foi corrigido |
|---|---|
| Estoque somado duas vezes na finalização (a função atualizava o saldo e a movimentação somava de novo) | `comercial/views/views_compras.py:632` (`registrar_compra`) |
| Era possível finalizar a mesma compra duas vezes, duplicando estoque e títulos | `comercial/views/views_compras.py:285` (`compra_pode_finalizar`), usada nas linhas 212 e 244 |
| Parcelas da compra não somavam o total (ex.: 100 em 3x virava 99,99) | `comercial/views/views_compras.py:258` |
| Títulos e movimentações não apareciam no detalhe da compra | `comercial/views/views_compras.py:225` e `:271` (grava `compra=`), `:307` (filtro do detalhe) |
| "Encerrar" parcelado pela tela de confirmação dava erro (`TypeError`) | `comercial/views/views_compras.py:354` |
| Salvar uma compra nova dava erro de URL (`NoReverseMatch`) | `comercial/views/views_compras.py:70` |
| Editar compra finalizada chamava `compra.estornar()`, que não existe | `comercial/views/views_compras.py:86` (compra finalizada agora não é editável) |
| Caixa "confirmada" no formulário marcava a compra sem lançar estoque nem financeiro | `comercial/forms.py:212` |
| Quantidade da compra era inteira (KG, LT e MT perdiam a fração) | `comercial/models.py:91` + migração `0005` |

## Vendas

| Problema | Onde foi corrigido |
|---|---|
| Finalizar venda à vista dava erro (`venda.contato` não existe) | `comercial/views/views_vendas.py:303`, `:332`, `:362` |
| Venda à vista nunca ficava "finalizada" | `comercial/views/views_vendas.py:148` |
| Cada novo "Salvar" de uma venda baixava o estoque de novo | `comercial/views/views_estoque.py:201` (`registrar_cmv` estorna a baixa anterior antes de lançar a nova) |
| Editar venda finalizada perdia a baixa dos itens não alterados | `comercial/views/views_vendas.py:252` (`processar_itens_venda` não mexe mais no estoque; tudo passa por `registrar_cmv`) |
| Parcelas da venda somavam mais que o total (ajuste aplicado duas vezes) | `comercial/views/views_vendas.py:356` |
| Bloqueio de edição com parcela recebida não funcionava; parcelas não apareciam no detalhe (filtro procurava `"VendaProduto"`) | `comercial/views/views_vendas.py:36` (`titulos_da_venda`), usada nas linhas 97, 195, 224, 378 e 418 |
| Recebimentos no caixa não apareciam no detalhe da venda | `comercial/views/views_vendas.py:199` |
| Estorno de venda dava erro (`referencia_id` não existe no título) | `comercial/views/views_vendas.py:418` e `:422` |
| Estorno alterava o custo médio do produto | `comercial/models.py:203` e `:138` (entrada de estorno devolve só a quantidade) |

## Financeiro

| Problema | Onde foi corrigido |
|---|---|
| Era possível pagar o mesmo título duas vezes | `financeiro/views_contas_pagar.py:229` |
| Após pagar, a tela dava erro (`pagar_list` não existe) | `financeiro/views_contas_pagar.py:255` |
| Pagamento não entrava no saldo do caixa | `financeiro/views_contas_pagar.py:239` |
| Detalhe da conta de compra dava erro (`referencia_id`) | `financeiro/views_contas_pagar.py:281` |
| Quitar título sem "Caixa Principal" cadastrado dava erro 500 | `financeiro/views_titulos.py:103` |
| Quitar título a receber sem categoria dava erro | `financeiro/views_titulos.py:137` |

## Relatórios

| Problema | Onde foi corrigido |
|---|---|
| DRE ignorava receitas patrimoniais (`RECEITAS_PATRIMONIAIS` × `RECEITA_PATRIMONIAL`) | `relatorios/services/dre_service.py:86` |
| DRE somava vendas em rascunho | `relatorios/services/dre_service.py:11` e `:107` |
| DRE, vendas e CMV por período ignoravam as vendas do último dia | `relatorios/services/dre_service.py:11`, `relatorios/services/vendas_service.py:8`, `relatorios/services/cmv_service.py:9` |
| Filtro por número no relatório de vendas dava erro (`numero_nota` não existe em Venda) | `relatorios/services/vendas_service.py:15` |

## Outros

| Problema | Onde foi corrigido |
|---|---|
| Consulta de estoque por AJAX dava erro para produto inexistente | `comercial/views/views_estoque.py:158` |
| Signal de criação de estoque definido duas vezes | `comercial/signals.py:12` |
| `print()` de depuração no middleware e em views | `core/middleware.py:9`, `comercial/views/views_vendas.py`, `comercial/views/views_compras.py`, `financeiro/views_titulos.py` |

## Arquivos novos

- `comercial/tests.py`, `financeiro/tests.py`, `relatorios/tests.py`: 25 testes
- `comercial/migrations/0005_compraitem_quantidade_decimal.py`
- `comercial/management/commands/verificar_estoque.py`

## Não alterado

- `comercial/services.py` tem uma cópia antiga de `registrar_compra` com o mesmo erro, mas o Python nunca a carrega porque a pasta `comercial/services/` tem o mesmo nome. Pode ser apagado.
- Numeração sequencial de vendas, validação de CPF/CNPJ e ativação de permissões ficaram para as Fases 1 e 2 do README, porque mudam regras ou dados existentes.
