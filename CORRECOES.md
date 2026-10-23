# Correções aplicadas (10/10/2026)

Cada problema abaixo foi primeiro reproduzido por um teste automatizado que falhava no código anterior e passa agora. Para rodar os testes:

```bash
python manage.py test comercial financeiro relatorios
```

Depois de copiar os arquivos, rode `python manage.py migrate` (há uma migração nova, `comercial/migrations/0005_compraitem_quantidade_decimal.py`).

---

## Novo visual "híbrido sóbrio" (22/10/2026)

Sem migração. Visual escolhido entre as três propostas (opção C): neumorfismo suave nas superfícies (fundo, cartões, abas, campos) e um toque de claymorfismo nos botões e etiquetas, mantendo o verde e o preto. Tudo fica num arquivo CSS novo carregado depois do Bootstrap; **para voltar ao visual antigo basta apagar a linha do `masc_tema.css` no `base.html`**. Depois de copiar, recarregue o navegador com Ctrl+F5.

Cores: fundo `#e6efe9` (menta acinzentado) no lugar do `#a9ebbd`; cartões `#fbfdfb`; verde `#2e7d32`/`#1b5e20` e menu `#2b2727` como antes. Tons novos: azul-petróleo `#2f6f8f` (botões primários, como Detalhes e Nova Venda, no lugar do azul do Bootstrap), turquesa `#2a8a86` (info), âmbar `#f2b84b` (pendente/atenção), vermelho `#c62828` (vencido/excluir).

| O que mudou | Onde |
|---|---|
| Tema completo por variáveis do Bootstrap 5.3: cartões em relevo, cabeçalhos de cartão em tom claro da mesma cor (verde = receitas, vermelho = despesas), cabeçalho de tabela verde claro em letra pequena (inclui os `table-dark`), botões com relevo, etiquetas em pílula, campos afundados, abas em formato de interruptor, paginação, janelas, Select2 e calendário | `core/static/css/masc_tema.css` (novo) |
| Liga o tema; o menu destaca em verde a tela aberta e deixa o grupo dela aberto | `core/templates/base.html` |
| **Texto de comentário aparecia na tela** abaixo do campo Categoria (Contas a Receber/Pagar, Lançamentos): comentário de várias linhas com `{# #}`, que o Django só aceita em uma linha. Trocado por `{% comment %}` | `financeiro/templates/financeiro/_sugestao_categoria.html` |

Os 143 testes continuam passando. Telas conferidas com a base real: Contas a Receber, Contas a Pagar, Lançamentos, Vendas, Nova Venda, Novo Título a Receber, Produtos, Contatos, Caixa, DRE, início e login.

---

## Preço de venda automático (21/10/2026)

Rode `python manage.py migrate` (migração nova `cadastros/migrations/0007_preco_automatico.py`). Ela marca como **manual** todo produto que já tem preço (nada muda de um dia para o outro) e dá a permissão nova "Pode revisar preços de venda e alterar o markup" aos grupos Administrador e Gerente.

Regra: preço automático = custo médio do estoque × (1 + markup), arredondado aos centavos. Markup inicial 62%, tolerância do aviso 5%, os dois alteráveis em Cadastros → Revisão de preços.

Depois do migrate, os produtos que estão com preço R$ 0,00 mas já têm custo (34 na base de 21/10) continuam automáticos e com preço zero até a próxima compra. Para calculá-los já: `python manage.py recalcular_precos_venda` (só mostra) e `python manage.py recalcular_precos_venda --aplicar` (grava; não mexe nos manuais).

| O que mudou | Onde |
|---|---|
| Campo "Preço manual" no produto e tabela de configuração (markup e tolerância, um registro só) | `cadastros/models.py` (`Produto.preco_manual`, `custo_medio`, `preco_sugerido`, `situacao_preco`, `ConfiguracaoPreco`) |
| Regra única de recálculo; manual nunca é alterado | `cadastros/precos.py` (`atualizar_preco_venda`) |
| O preço automático acompanha o custo a cada entrada de compra/NF-e e a cada recálculo do estoque (estornos, correções) | `comercial/models.py` (`MovimentacaoEstoque.save`, `Estoque.recalcular_preco_medio`) |
| Ao finalizar compra (à vista, parcelada, duplicatas): aviso com os preços que mudaram e os que ficaram para conferir | `comercial/views/views_compras.py` (`registrar_compra`, `resumo_precos`, `avisar_precos`) |
| Formulário: custo, sugerido e botão "Voltar ao automático"; preço digitado diferente do sugerido torna o produto manual, com aviso | `cadastros/forms.py` (`ProdutoForm.clean`), `cadastros/views.py`, `cadastros/templates/cadastros/produto_form.html` |
| Selos "manual", "fora do sugerido" (manual além da tolerância) e "abaixo do custo" na lista e no detalhe; custo e selos de custo só para quem tem "ver custos" | `cadastros/templates/cadastros/_selo_preco.html`, `produto_list.html`, `produto_detail.html` |
| Tela Revisão de preços: altera markup/tolerância (recalcula os automáticos), lista sinalizados ou todos os manuais, aplica o sugerido em lote | `cadastros/views.py` (`revisao_precos`), `cadastros/urls.py`, `cadastros/templates/cadastros/revisao_precos.html`, `core/permissoes.py`, `core/templates/partials/sidebar.html` |
| Importação de produtos por CSV marca o preço da planilha como manual | `cadastros/views.py` (`importar_produtos`) |
| Tela de venda avisa quando o preço de cadastro está abaixo do custo (sem mostrar o custo ao vendedor) | `comercial/views/views_vendas.py` (`api_preco`), `comercial/templates/comercial/venda_form.html` |
| Comando para simular/aplicar o preço automático | `cadastros/management/commands/recalcular_precos_venda.py` |
| **Avisos do sistema passam a aparecer na tela.** Nenhum template exibia as mensagens (`messages.success/error/warning`), então avisos como "Existem itens pendentes" nunca apareciam | `core/templates/partials/messages.html`, `core/templates/base.html` |
| 14 testes novos | `cadastros/tests.py` (`PrecoVendaAutomaticoTests`, `PrecoVendaPermissoesTests`) |

---

## Cadastro de usuários delegado ao gerente (21/10/2026)

Sem migração. Para delegar: no usuário do gerente, marque "Membro da equipe" e dê as permissões "auth | usuário | Can view/add/change user" e "auth | grupo | Can view group". Não dê "delete user" (para tirar o acesso, desmarque "Ativo") nem as de alterar grupos.

| O que mudou | Onde |
|---|---|
| Quem cadastra usuários sem ser superusuário não vê os campos "Superusuário" e "Permissões do usuário" | `core/admin.py` (`UsuarioAdmin.get_fieldsets`) |
| O grupo Administrador não aparece na lista de grupos para ele, e o sistema recusa se for enviado | `core/admin.py` (`formfield_for_manytomany`, `GRUPOS_RESERVADOS`) |
| Superusuários e membros do grupo Administrador somem da lista para ele, e ele não consegue abrir, alterar, excluir nem trocar a senha dessas contas | `core/admin.py` (`get_queryset`, `has_*_permission`) |
| Superusuário continua vendo e alterando tudo | — |
| 5 testes novos (4 deles falham sem a proteção) | `core/tests.py` (`CadastroDeUsuariosDelegadoTest`) |

---

## Permissões de usuários (21/10/2026)

Usa os usuários, grupos e permissões do próprio Django. Rode `python manage.py migrate` (migrações novas `cadastros/migrations/0006_permissoes.py`, `comercial/migrations/0010_permissoes.py`, `financeiro/migrations/0022_permissoes.py`, `relatorios/migrations/0001_permissoes.py` e `core/migrations/0001_grupos_padrao.py`, que cria os 5 grupos). Superusuários continuam com acesso total.

Para liberar alguém: em `/admin/` → Usuários, crie o usuário e marque um ou mais grupos (Administrador, Gerente, Vendedor, Compras/Estoque, Financeiro). Os grupos podem ser ajustados em `/admin/` → Grupos. Só quem tem "Membro da equipe" marcado entra no admin. `python manage.py criar_grupos --redefinir` volta os grupos ao padrão.

| O que mudou | Onde |
|---|---|
| Mapa único "tela → permissão" para as 85 rotas de cadastros, comercial, financeiro e relatórios. Rota fora do mapa fica bloqueada | `core/permissoes.py` |
| Middleware confere a permissão antes de abrir a tela; sem permissão aparece "Você não tem acesso a esta tela" (403) | `core/middleware.py` (`PermissaoMiddleware`), `gestaomasc/settings.py` (MIDDLEWARE), `core/templates/403.html` |
| Permissões especiais: importar CSV, unificar contato, importar NF-e, emitir recibo, ver custos/CMV, quitar título, estornar quitação, alterar categoria de título, operar caixa, relatórios comerciais e gerenciais | `Meta.permissions` em `cadastros/models.py`, `comercial/models.py`, `financeiro/models.py`; `relatorios/models.py` (`Relatorio`, sem tabela) |
| 5 grupos padrão e o comando para recriá-los | `core/grupos.py`, `core/migrations/0001_grupos_padrao.py`, `core/management/commands/criar_grupos.py` |
| Menu mostra só as telas liberadas e esconde o módulo inteiro quando nada dele está liberado; mostra o nome do usuário e, para membros da equipe, o link "Usuários e permissões" | `core/templates/partials/sidebar.html`, `core/templatetags/permissoes.py` (`{% pode %}`) |
| Botões Novo, Editar, Excluir, Quitar, Estornar, Alterar Categoria, Abrir/Fechar caixa, Sangria, Reforço, Importar e Unificar somem para quem não tem a permissão | 20 templates em `cadastros/`, `comercial/` e `financeiro/templates/` |
| Preço médio do estoque só aparece para quem pode ver custos | `comercial/templates/comercial/estoque_list.html`, `comercial/views/views_estoque.py` (`ajax_estoque`) |
| Removida a pasta `gestaomasc/core_s/` (tentativa antiga, não usada) | — |
| Testes existentes passam a logar como superusuário; 16 testes novos (todas as rotas mapeadas, menu e acesso por perfil, botões, custo escondido) | `core/tests.py`, `cadastros/tests.py`, `comercial/tests.py`, `financeiro/tests.py`, `relatorios/tests.py` |

---

## CMV que faltava nas vendas (20/10/2026)

Rode `python manage.py corrigir_cmv` para ver o que muda e `python manage.py corrigir_cmv --aplicar` para gravar.

| O que mudou | Onde |
|---|---|
| Comando que cria o CMV dos itens de produto de vendas finalizadas que têm saída de estoque mas não têm CMV (pelo custo médio da saída) e acerta o CMV total gravado em cada venda. No seu banco: venda V000001, 58 un. do CHUMBADOR CONE JAQUETA 3/8 (R$ 100,34); CMV total das vendas V000001 e V000002, que estava zerado | `comercial/management/commands/corrigir_cmv.py` |
| 1 teste novo | `comercial/tests.py` (`CorrigirCMVTests`) |

---

## Relatório de Movimentações de Estoque (20/10/2026)

Novo relatório em Relatórios > Movimentações de Estoque. Não precisa de migração.

| O que mudou | Onde |
|---|---|
| Filtros por período, produto, tipo (entrada/saída) e origem (compra, venda, estorno, ajuste) | `relatorios/forms.py` (`FiltroMovimentacaoEstoqueForm`) |
| Resumo por produto (saldo inicial, entradas, saídas, saldo final, valor das entradas e custo das saídas) e lista das movimentações com link para a compra ou venda | `relatorios/services/estoque_service.py`, `relatorios/views/estoque.py`, `relatorios/templates/relatorios/estoque/movimentacoes.html`, `relatorios/urls.py` |
| Link no menu | `core/templates/partials/sidebar.html` |
| Detalhe da compra mostra o CNPJ/CPF do fornecedor e o detalhe da venda, o CPF/CNPJ do cliente | `compras_detalhe.html`, `venda_detalhe.html` |
| Menu lateral pode ser recolhido também no computador | `core/templates/base.html`, `core/static/css/masc_style.css` |
| 2 testes novos | `relatorios/tests.py` (`MovimentacaoEstoqueTests`) |

---

## CPF/CNPJ sempre com máscara (20/10/2026)

Rode `python manage.py migrate` (migração nova `cadastros/migrations/0005_documento_com_mascara.py`, que põe a pontuação nos documentos gravados só com números).

| O que mudou | Onde |
|---|---|
| Fornecedor criado pela importação da NF-e grava o CNPJ com a pontuação | `comercial/services/xml_importer.py`, `cadastros/models.py` (`formatar_documento`) |
| O cadastro do contato grava o CPF/CNPJ com a pontuação mesmo se for digitado só com números | `cadastros/forms.py` (`ContatoForm.clean_documento`) |
| 2 testes novos | `cadastros/tests.py` (`DocumentoContatoTests`), `comercial/tests.py` |

---

## Unificar contatos duplicados (20/10/2026)

Não precisa de migração.

| O que mudou | Onde |
|---|---|
| Excluir um contato que tem compras, vendas, contas ou lançamentos não dá mais erro: a tela mostra o que está ligado a ele e oferece unificar | `cadastros/views.py` (`contato_delete`) |
| "Unificar com outro" no detalhe do contato: escolhe o contato que fica, todos os registros passam para ele (compras, contas, lançamentos, vendas, códigos de produto do fornecedor), telefone, e-mail, documento e categoria que faltarem são copiados, e o duplicado é apagado | `cadastros/services.py` (`unificar_contatos`), `cadastros/views.py` (`contato_unificar`), `cadastros/forms.py` (`ContatoUnificarForm`), `cadastros/urls.py`, `contato_unificar.html`, `contato_detail.html` |
| 2 testes novos | `cadastros/tests.py` (`UnificarContatoTests`) |

---

## Módulo Relatórios (20/10/2026)

Itens 1 a 11 de `REVISAO_RELATORIOS.md`. Rode `python manage.py migrate` (migração nova `financeiro/migrations/0021_grupo_custos.py`, que também passa as categorias "CMV" e "CSP" de Despesas com Vendas para o grupo novo Custos).

| O que mudou | Onde |
|---|---|
| Compras por Período soma o valor de cada item na nota (produtos + frete + seguro + outras despesas + IPI + ICMS-ST - desconto) e só compras confirmadas. A tela mostra o valor dos produtos e o total na nota | `relatorios/services/compras_service.py`, `relatorios/templates/relatorios/compras/por_periodo.html` |
| Vendas por Período só com vendas finalizadas; o total geral usa a mesma conta das linhas (com o desconto do item) e mostra à parte o desconto e o acréscimo da venda | `relatorios/services/vendas_service.py`, `relatorios/templates/relatorios/vendas/por_periodo.html` |
| CMV - Relatório inclui o último dia do período e só vendas finalizadas; a consulta passou para o serviço | `relatorios/services/cmv_service.py`, `relatorios/views/cmv.py` |
| Desconto e acréscimo da venda entram no total da venda (e com ele no contas a receber). Desconto maior que os itens ou valores negativos são recusados. A tela da venda atualiza o total ao digitar; detalhe e recibo mostram itens, desconto e acréscimo | `comercial/models.py` (`Venda.atualizar_total`, `total_itens`), `comercial/views/views_vendas.py` (`conferir_desconto_venda`), `comercial/forms.py`, `venda_form.html`, `venda_detalhe.html`, `venda_recibo.html` |
| DRE: acréscimo da venda entra na receita bruta e desconto da venda nas deduções | `relatorios/services/dre_service.py`, `relatorios/templates/relatorios/dre/dre.html` |
| DRE: grupo novo "Custos (CMV/CSP lançados à mão)", mostrado logo abaixo do CMV, com aviso para não repetir o CMV que o estoque já calcula | `financeiro/models.py`, `financeiro/migrations/0021_grupo_custos.py`, `dre_service.py`, `dre.html` |
| Filtro de fornecedor aparece em Compras; filtros listam só fornecedores (ou só clientes) e quem já tem compra (ou venda) | `relatorios/forms.py`, `compras/por_periodo.html` |
| Os quatro relatórios avisam quando a data inicial é depois da final | `relatorios/forms.py` (`PeriodoMixin`), `relatorios/templates/relatorios/_erros_filtro.html` |
| Número da nota da compra aparece como foi gravado (antes saía "C000000" quando não era só número) | `comercial/models.py` (`Compra.numero_formatado`) |
| 11 testes novos | `relatorios/tests.py`, `comercial/tests.py` (`VendaDescontoTests`) |

---

## Categoria certa nos lançamentos (20/10/2026)

Rode `python manage.py migrate` (migrações novas `cadastros/migrations/0004_contato_categoria_padrao.py` e `financeiro/migrations/0020_observacao_titulo.py`).

| O que mudou | Onde |
|---|---|
| Cadastro do contato ganhou "Categoria financeira padrão" | `cadastros/models.py` (`Contato.categoria_padrao`), `cadastros/forms.py`, `cadastros/templates/cadastros/contato_form.html` |
| Novo lançamento, nova conta a receber e edição de conta a pagar manual: ao escolher o contato, a categoria vem preenchida com a padrão dele (ou, sem padrão, com a última usada) e a tela mostra qual é. Se o usuário salvar com outra categoria, a tela pede confirmação | `financeiro/services.py` (`categoria_sugerida`), `financeiro/views_titulos.py` (`api_categoria_sugerida`), `financeiro/templates/financeiro/_sugestao_categoria.html`, `lancamento_form.html`, `receber_form.html`, `conta_pagar_form.html` |
| "Alterar Categoria" no detalhe do título, também para título já quitado: troca só a categoria, sem estorno e sem mexer no caixa. Se o título veio de um lançamento, o lançamento também muda (o DRE lê o lançamento). Fica registrado no histórico do título quem trocou, quando e de qual para qual | `financeiro/services.py` (`reclassificar_categoria`), `financeiro/views_titulos.py` (`titulo_reclassificar`), `titulo_reclassificar.html`, `titulo_detalhe.html`, `financeiro/models.py` (`observacao`) |
| 5 testes novos | `financeiro/tests.py` (`CategoriaSugeridaTests`) |

---

## Quitação com juros, multa, desconto e pagamento parcial (20/10/2026)

Item 17 de `REVISAO_FINANCEIRO.md`. Rode `python manage.py migrate` (migração nova `financeiro/migrations/0019_juros_multa_desconto.py`).

| O que mudou | Onde |
|---|---|
| As telas "Pagar" e "Quitar" pedem valor quitado, juros, multa e desconto, e mostram o total. O caixa recebe o total (valor + juros + multa − desconto); o título guarda cada parte | `financeiro/services.py` (`quitar_titulo`), `financeiro/views_titulos.py` (`ler_quitacao`), `financeiro/templates/financeiro/_quitacao_campos.html`, `titulo_confirmar_quitacao.html`, `pagar_quitacao.html` |
| Pagamento parcial: o título fica com o valor quitado e o restante vira um título novo em aberto, com o mesmo vencimento e "(saldo)" na descrição | `financeiro/services.py` (`quitar_titulo`) |
| Valores negativos, acima do título, desconto maior que o valor ou texto inválido são recusados com mensagem | `financeiro/services.py`, `financeiro/views_titulos.py` |
| O estorno devolve o total que saiu do caixa (com juros e multa) e zera os acréscimos | `financeiro/services.py` (`estornar_quitacao`) |
| Detalhe do título mostra juros, multa, desconto e total | `titulo_detalhe.html`, `titulo_estornar_quitacao.html` |
| DRE: juros e multas pagos e descontos concedidos entram em Outras Despesas; juros e multas recebidos e descontos obtidos, em Outras Receitas, pela data da quitação | `relatorios/services/dre_service.py` (`acrescimos_das_quitacoes`), `relatorios/templates/relatorios/dre/dre.html` |
| 6 testes novos | `financeiro/tests.py` (`QuitacaoAcrescimosTests`), `relatorios/tests.py` |

---

## DRE por competência (20/10/2026)

Item 16 de `REVISAO_FINANCEIRO.md`. Rode `python manage.py migrate` (migrações novas `financeiro/migrations/0017_grupos_dre_juntos.py` e `0018_corrigir_grupos_dre_antigos.py`).

| O que mudou | Onde |
|---|---|
| Contas a pagar e a receber criadas direto (manuais) entram no DRE pela data do lançamento, mesmo que pagas em outro mês. Títulos de venda, compra e lançamento continuam de fora (já entram pela venda, pelo CMV e pelo lançamento). Título cancelado não entra | `relatorios/services/dre_service.py` (`valores_por_grupo_dre`) |
| Três categorias suas tinham códigos de grupo antigos que o DRE não reconhecia, e os valores ficavam de fora sem aviso: ICMS a Recolher, PIS_COFINS e IRPJ_CSSL (R$ 1.269,00 em 2026). A migração passa essas categorias para ICMS, PIS/COFINS e IRPJ/CSLL; Juros Recebidos e Multas Pagas vão para Receitas e Despesas Financeiras | `financeiro/migrations/0018_corrigir_grupos_dre_antigos.py` |
| Grupos novos "PIS/COFINS (juntos)" e "IRPJ/CSLL (juntos)", para impostos lançados num valor só | `financeiro/models.py` (`GRUPO_DRE_CHOICES`) |
| Lançamento com grupo "Receita Bruta" passa a entrar na receita bruta (antes era ignorado) | `relatorios/services/dre_service.py` |
| As linhas IRPJ e CSLL do DRE apareciam vazias | `relatorios/services/dre_service.py`, `relatorios/templates/relatorios/dre/dre.html` |
| O DRE avisa quais categorias ficaram de fora por não ter grupo | `relatorios/templates/relatorios/dre/dre.html` |
| 4 testes novos | `relatorios/tests.py` |

---

## Financeiro: quitação, travas, caixa e relatórios (20/10/2026)

Etapas 2 a 7 da proposta de `REVISAO_FINANCEIRO.md` (itens 5 a 15). Rode `python manage.py migrate` (migração nova `financeiro/migrations/0016_origem_estorno.py`, só acrescenta as origens "Entrada de Venda" e "Estorno" ao movimento de caixa) e depois, uma vez, `python manage.py vincular_quitacoes` para ver o que muda e `python manage.py vincular_quitacoes --aplicar` para gravar.

| O que mudou | Onde |
|---|---|
| Uma única rotina de quitação para "Pagar" (Contas a Pagar) e "Quitar" (Títulos): grava no Caixa Principal, liga o movimento ao título, usa a data informada (padrão: hoje, data local), confere o saldo antes de pagar e roda numa transação | `financeiro/services.py:32` (`quitar_titulo`), `financeiro/views_contas_pagar.py:233`, `financeiro/views_titulos.py:87` |
| Estorno de quitação: botão "Estornar Quitação" no detalhe do título. Lança o movimento inverso no caixa (o original fica no histórico) e volta o título para em aberto | `financeiro/services.py:70` (`estornar_quitacao`), `financeiro/views_titulos.py:113`, `financeiro/templates/financeiro/titulo_estornar_quitacao.html`, `titulo_detalhe.html` |
| Título pago não pode ser editado nem excluído (conta a pagar, conta a receber e lançamento); é preciso estornar a quitação antes | `financeiro/views_contas_pagar.py:22` e `:47`, `financeiro/views_receber.py:90` e `:111`, `financeiro/views_lancamento.py:142` e `:162` |
| Excluir lançamento exclui o título dele. Editar lançamento trocando despesa por receita (ou o contrário) troca o título | `financeiro/views_lancamento.py:84` (`sincronizar_titulo`), `:162` |
| Conta a receber de venda ou de lançamento só sai pela origem; na edição só o vencimento pode mudar (igual a Contas a Pagar) | `financeiro/views_receber.py:90`, `financeiro/forms.py` (`ReceberVencimentoForm`), `templates/financeiro/receber_vencimento_form.html` |
| Caixa não abre duas vezes. A abertura mostra o saldo do sistema e avisa se o valor contado for diferente (não altera o saldo) | `financeiro/views_caixa.py:30`, `caixa_abrir.html` |
| Movimento manual sempre tem caixa (o campo "Origem", que era ignorado, virou "Caixa") e não aceita valor zero ou negativo. Editar e excluir movimento manual saíram da lista de caixas (abriam o movimento com o número do caixa) e foram para o detalhe do caixa | `financeiro/views_caixa.py:233`, `caixa_form.html`, `caixa_list.html`, `caixa_detalhe.html`, `caixa_movimento_detalhe.html`, `caixa_confirm_delete.html` |
| Painel e histórico mostram o mesmo saldo da tela do caixa (saldo inicial + movimentos) | `financeiro/services.py:23` (`saldo_geral`), `financeiro/views_caixa.py:207` e `:291`, `caixa_historico.html` |
| Gráfico do painel usa os meses do calendário (antes pulava mês) | `financeiro/views_caixa.py:327` |
| Contas a Pagar: totais separados em "em aberto" e "pagos"; filtros hoje, amanhã e vencidos mostram só títulos pendentes | `financeiro/views_contas_pagar.py:78-110`, `contas_pagar_lista.html` |
| Coluna Vencimento das despesas avulsas aparecia vazia | `contas_pagar_lista.html` |
| Botão do movimento no detalhe da conta de compra abria o caixa errado | `conta_detalhe.html` |
| Botão "Editar Venda" em Contas a Receber nunca aparecia | `receber_list.html` |
| Estorno de venda com entrada (sinal): devolve a entrada uma vez só, com uma saída no caixa. A entrada da venda agora entra no Caixa Principal e fica ligada ao título. Hoje nenhuma tela chama esse estorno e a venda não tem campo de entrada; a correção deixa o código certo para quando tiver | `comercial/views/views_vendas.py:298` e `:417` |
| Comando que liga os títulos já quitados ao movimento de caixa. Sem `--aplicar` só mostra o que mudaria | `financeiro/management/commands/vincular_quitacoes.py` |
| 14 testes novos | `financeiro/tests.py` (`FluxoFinanceiroTests`), `comercial/tests.py` |

---

## Financeiro: telas que davam erro (19/10/2026)

Itens 1 a 4 de `REVISAO_FINANCEIRO.md`. Não há migração.

| Problema | Onde foi corrigido |
|---|---|
| Painel financeiro dava erro sempre (filtrava por `esta_pago`, que é método) | `financeiro/views_caixa.py` (`dashboard_financeiro`) |
| "Pagar" no detalhe da conta de compra dava erro (link para `pagar_list`, que não existe); a tela de excluir conta manual tinha o mesmo erro | `financeiro/templates/financeiro/pagar_quitacao.html`, `financeiro/templates/financeiro/pagar_confirm_delete.html` |
| Tela do caixa dava erro depois de aberto; fechar, sangria e reforço não tinham rota. Agora têm, e os valores são validados (vazio ou negativo é recusado) e calculados em Decimal | `financeiro/urls.py`, `financeiro/views_caixa.py` (`ler_valor`, `caixa_abrir`, `caixa_fechar`, `caixa_sangria`, `caixa_reforco`) |
| Nova conta a receber e editar conta a receber davam erro (faltava `{% load widget_tweaks %}`) | `financeiro/templates/financeiro/receber_form.html` |
| 5 testes novos | `financeiro/tests.py` (`TelasFinanceiroTests`) |

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
