# Gestão MASC

Sistema web de gestão comercial, financeira e contábil para pequenas empresas, desenvolvido em **Python / Django**, por Eloi Lerner.

Este documento descreve o estado atual da aplicação e um **projeto de evolução em fases**, partindo do código que já existe.

---

## 1. Estado atual

### 1.1 Stack

| Item | Hoje |
|---|---|
| Linguagem | Python 3 |
| Framework | Django 5.0.6 |
| Banco de dados | SQLite (`db.sqlite3`) |
| Front-end | Templates Django + Bootstrap, `django-widget-tweaks` |
| Arquivos estáticos | WhiteNoise |
| Configuração | `python-dotenv` (`.env` com `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`) |
| Já instalados, mas sem uso | `psycopg2-binary`, `dj-database-url` (PostgreSQL) |
| Autenticação | `django.contrib.auth` + `core.middleware.LoginRequiredMiddleware` |

### 1.2 Módulos (apps Django)

| App | Responsabilidade | Principais modelos |
|---|---|---|
| `core` | Layout base, login, sidebar, middleware de login obrigatório | — |
| `cadastros` | Cadastros mestres, importação CSV | `Produto`, `Servico`, `Contato` (fornecedor, cliente, beneficiário) |
| `comercial` | Compras (manual e por XML de NF-e), vendas, estoque, CMV | `Compra`, `CompraItem`, `Venda`, `VendaItem`, `Estoque`, `MovimentacaoEstoque`, `CMVItem` |
| `financeiro` | Plano de contas, lançamentos, contas a pagar/receber, títulos, caixa, dashboard | `FinanceiroCategoria`, `FinanceiroLancamento`, `FinanceiroPagar`, `FinanceiroReceber`, `Caixa`, `CaixaMovimento`, `CaixaAbertura`, `CaixaFechamento` |
| `relatorios` | Relatórios por período e DRE | (usa `services/` sobre os modelos acima) |
| `gestaomasc/core_s` | Esboço de RBAC (papéis e permissões) | `Role`, `Permission` — **não registrado em `INSTALLED_APPS`** |

### 1.3 Fluxos já implementados

- **Compra → Estoque → Contas a Pagar**: importação de XML de NF-e (`XmlCompraImporter`), vínculo de itens importados a produtos, confirmação, finalização à vista ou parcelada, geração de títulos a pagar e estorno.
- **Venda → Estoque → CMV → Contas a Receber**: rascunho/finalização, baixa de estoque com custo médio congelado no item, parcelamento, recibo e estorno.
- **Estoque**: custo médio ponderado recalculado a cada entrada, histórico de movimentações com saldo após.
- **Financeiro**: quitação de títulos com movimento de caixa, abertura/fechamento de caixa, sangria e reforço, dashboard.
- **Relatórios**: compras e vendas por período, CMV e DRE (receita bruta, deduções, CMV, despesas por grupo, resultado).

### 1.4 Pontos de atenção encontrados na leitura do código

Itens observados que servem de insumo para a Fase 1. Os marcados com *(verificar)* foram inferidos da leitura e precisam ser confirmados com um teste.

1. **DRE ignora receitas patrimoniais**: `dre_service.py` compara `grupo_dre == "RECEITAS_PATRIMONIAIS"`, mas a opção cadastrada em `FinanceiroCategoria` é `"RECEITA_PATRIMONIAL"`.
2. **DRE não filtra status da venda**: soma `VendaItem` de vendas em rascunho junto com as finalizadas *(verificar)*.
3. **Possível dupla contagem de estoque em `comercial/services.py::registrar_compra`**: a função atualiza `Estoque` manualmente e depois cria `MovimentacaoEstoque`, cujo `save()` atualiza o estoque de novo. A função parece não ser chamada pelas views hoje *(verificar)*; se for código morto, remover.
4. **Edição de venda finalizada** (`processar_itens_venda`): apaga todas as saídas antigas, mas `formset.save(commit=False)` só devolve itens alterados, então itens não alterados podem ficar sem saída de estoque *(verificar)*.
5. **Tipos inconsistentes**: `CompraItem.quantidade` é inteiro, enquanto `Estoque` e `VendaItem` usam decimal (KG, LT, MT ficam limitados).
6. **Numeração sequencial de venda** calculada com `order_by("-numero").first()`, sujeita a duplicidade com acessos simultâneos.
7. **Transações**: só o estorno de venda usa `transaction.atomic()`; finalização de compra/venda pode deixar estoque e financeiro inconsistentes se falhar no meio.
8. **Signal duplicado** em `comercial/signals.py` (`criar_estoque_para_produto` definido duas vezes).
9. **Validadores de CPF/CNPJ e telefone** definidos em `cadastros/models.py` mas não aplicados aos campos de `Contato`.
10. **RBAC não ativo**: `core_s` (papéis, permissões, middleware e decorator) existe, mas não está instalado nem ligado ao `MIDDLEWARE`.
11. **`print()` no middleware de login** em todas as requisições.
12. **Sem testes automatizados** (`tests.py` vazios em todos os apps).
13. **Templates de relatório vazios**: vendas por cliente/produto, compras por fornecedor/produto, curva ABC, giro de estoque, contas a pagar/receber.
14. **Origens como texto livre** (`origem`, `referencia_id`) convivendo com `GenericForeignKey` em `FinanceiroPagar`/`FinanceiroReceber`; duas formas de ligar o título à origem.
15. **Parte contábil ainda é gerencial**: não há plano de contas hierárquico, partidas dobradas, contas bancárias nem conciliação.

---

## 2. Projeto em fases

Cada fase entrega algo utilizável e não depende de reescrever o que já existe. As fases 1 e 2 são pré-requisito para as demais; as fases 3 a 7 podem ser reordenadas conforme a prioridade do negócio.

```
Fase 0  Organização do projeto
Fase 1  Correções e confiabilidade dos dados
Fase 2  Segurança, usuários e infraestrutura
Fase 3  Financeiro completo (bancos, conciliação, fluxo de caixa)
Fase 4  Núcleo contábil (plano de contas e partidas dobradas)
Fase 5  Relatórios gerenciais e apoio fiscal
Fase 6  Integrações, API e multiempresa
Fase 7  Módulo fiscal (NF-e, NFC-e, NFS-e e reforma tributária)
```

### Fase 0 — Organização do projeto

**Objetivo:** deixar o projeto fácil de instalar, rodar e evoluir.

- Este README com instruções de instalação (ver seção 3).
- `.env.example` com as variáveis necessárias (sem valores reais).
- Separar `requirements.txt` em base e desenvolvimento (`pytest`, `pytest-django`, `ruff`, `coverage`).
- Padronizar formatação e lint com `ruff`.
- Remover código morto e duplicado (signal duplicado, imports repetidos em `xml_importer.py`, `comercial/views.py` vazio).
- Corrigir o nome da pasta `decoreators` → `decorators`.
- Fixture com dados iniciais: categorias padrão do plano de contas e grupos de DRE.

**Entrega:** projeto sobe do zero com `pip install`, `migrate`, `loaddata` e `runserver`.

### Fase 1 — Correções e confiabilidade dos dados

**Objetivo:** garantir que estoque, CMV, financeiro e DRE batem entre si.

- Criar uma **camada de serviços** por app (`services/`) para as regras de negócio que hoje estão nas views (finalizar compra, finalizar venda, estornar, quitar título), sempre dentro de `transaction.atomic()`.
- Corrigir os itens 1 a 8 da seção 1.4.
- `CompraItem.quantidade` → `DecimalField(max_digits=10, decimal_places=3)` com migração.
- Numeração de venda/compra via tabela de sequência com `select_for_update()`.
- Unificar a referência de origem dos títulos (manter `GenericForeignKey` e migrar `origem/referencia_id`).
- Aplicar validadores de CPF/CNPJ (com dígito verificador) e telefone em `Contato`.
- **Testes automatizados** com `pytest-django` cobrindo: custo médio, entrada/saída/estorno de estoque, compra parcelada, venda parcelada, quitação e DRE de um período conhecido.
- Comando de gestão `python manage.py verificar_consistencia` que compara saldo de `Estoque` com a soma de `MovimentacaoEstoque` e títulos com movimentos de caixa.

**Entrega:** números confiáveis e uma suíte de testes que impede regressões.

### Fase 2 — Segurança, usuários e infraestrutura

**Objetivo:** preparar para uso por mais de uma pessoa e para produção.

- Ativar o RBAC de `core_s`: transformar em app (`seguranca`), registrar em `INSTALLED_APPS` e `MIDDLEWARE`, aplicar `@permission_required` nas views. Avaliar substituir pelo sistema nativo de grupos/permissões do Django para reduzir código próprio.
- Perfis iniciais: Administrador, Financeiro, Comercial, Consulta.
- **Auditoria**: quem criou/alterou/estornou cada registro (`criado_por`, `criado_em`, `alterado_por`, `alterado_em`) e histórico com `django-simple-history`.
- Trocar `print` por `logging` configurado.
- Migrar para **PostgreSQL** usando `dj-database-url` (já instalado), com script de migração dos dados do SQLite.
- Configurações de produção: `SECURE_*`, `CSRF_TRUSTED_ORIGINS`, cookies seguros, `SECRET_KEY` obrigatória.
- Backup automático do banco e procedimento de restauração.
- Deploy documentado (Gunicorn/Waitress + Nginx, ou Docker).

**Entrega:** aplicação multiusuário, auditável e rodando em servidor.

### Fase 3 — Financeiro completo

**Objetivo:** controlar o dinheiro real, não só títulos.

- Modelo `ContaBancaria` (banco, agência, conta, saldo inicial) ao lado de `Caixa`; movimentos passam a apontar para uma conta financeira.
- Transferência entre contas (a origem `TRANSFERENCIA` já existe em `CaixaMovimento`).
- Formas de pagamento como cadastro (PIX, cartão, boleto, dinheiro) com prazo e taxa (ex.: taxa de cartão gera despesa automaticamente).
- Baixa parcial de títulos, juros, multa e desconto na quitação.
- Centro de custo nos lançamentos e títulos.
- Despesas recorrentes (aluguel, salários) geradas automaticamente.
- **Importação de extrato OFX** e tela de **conciliação bancária**.
- **Fluxo de caixa** realizado e projetado (diário, semanal, mensal).

**Entrega:** saldo bancário conciliado e previsão de caixa.

### Fase 4 — Núcleo contábil

**Objetivo:** transformar os registros gerenciais em contabilidade de partidas dobradas.

- **Plano de contas hierárquico** (ativo, passivo, PL, receitas, despesas) com código estruturado (ex.: `1.1.01.001`), substituindo ou ligando `FinanceiroCategoria` às contas contábeis.
- Modelos `LancamentoContabil` e `PartidaContabil` (débito/crédito, soma sempre zero, validado no modelo e em teste).
- **Lançamentos automáticos** a partir dos eventos já existentes: compra, venda, CMV, quitação, transferência e estorno, através de regras de contabilização configuráveis.
- Período contábil com fechamento mensal (bloqueia alterações em meses fechados).
- Relatórios: **Livro Diário, Razão, Balancete de Verificação, Balanço Patrimonial** e DRE contábil.
- DRE gerencial atual continua disponível para comparação.

**Entrega:** balancete e balanço gerados a partir das operações do dia a dia.

### Fase 5 — Relatórios gerenciais e apoio fiscal

**Objetivo:** apoiar obrigações fiscais e decisões.

- Completar os relatórios com template vazio: vendas por cliente e por produto, compras por fornecedor e por produto, contas a pagar e a receber (aging), **curva ABC** e **giro de estoque**.
- Exportação para Excel (`openpyxl`) e PDF (`weasyprint` ou `reportlab`).
- Dashboard com gráficos (faturamento, margem, inadimplência, posição de caixa).
- O cálculo de tributos por item e a emissão de notas ficam na Fase 7.
- Inventário e ajuste de estoque com motivo (origem `AJUSTE`).
- Exportação de dados para o contador (layout a definir; SPED fica como estudo futuro).

**Entrega:** relatórios gerenciais completos e exportáveis.

### Fase 6 — Integrações, API e multiempresa

**Objetivo:** abrir o sistema para outros canais e empresas.

- **API REST** com Django REST Framework (cadastros, vendas, títulos, relatórios) e autenticação por token.
- **Multiempresa**: modelo `Empresa` e campo `empresa` nos modelos principais, com filtro automático por usuário.
- A emissão de NF-e, NFC-e e NFS-e fica na Fase 7.
- Boletos e PIX com retorno automático de pagamento.
- Envio de recibos e cobranças por e-mail ou WhatsApp.
- Tarefas em segundo plano (Celery ou `django-q2`) para importações, conciliação e envios.

**Entrega:** sistema integrado e pronto para atender mais de uma empresa.

### Fase 7 — Módulo fiscal

**Objetivo:** emitir os documentos fiscais exigidos para vender e calcular os tributos de produtos e serviços, já preparado para a reforma tributária. Sem esta fase, a empresa precisa de outro sistema para faturar.

O módulo entra como um app Django novo (`fiscal`), ligado a `cadastros` e `comercial`. A estrutura atual ajuda: a compra já lê XML de NF-e, o DRE já tem grupos para ICMS, ISS, PIS, COFINS, IRPJ e CSLL, e cada item da venda já separa produto de serviço.

*As regras abaixo seguem a EC 132/2023 e a LC 214/2025. Confirme alíquotas, prazos e o regime da empresa com o contador antes de implementar, porque a regulamentação ainda está sendo publicada.*

#### 7.1 Reforma tributária: o sistema precisa calcular os dois modelos ao mesmo tempo

PIS, COFINS, IPI, ICMS e ISS serão substituídos por **CBS** (federal), **IBS** (estados e municípios) e **Imposto Seletivo (IS)**:

| Período | O que muda |
|---|---|
| 2026 | Ano de teste: CBS 0,9% e IBS 0,1% informados na nota, compensáveis com PIS/COFINS. NF-e, NFC-e e NFS-e ganham campos de IBS/CBS. NFS-e no padrão nacional. |
| 2027 | CBS em vigor plena; PIS e COFINS extintos; IPI zerado (exceto Zona Franca); começa o Imposto Seletivo. Simples Nacional pode optar por recolher IBS/CBS fora do DAS. |
| 2029 a 2032 | ICMS e ISS caem gradualmente enquanto o IBS sobe. |
| 2033 | Só IBS, CBS e Imposto Seletivo. |

Também está previsto o **split payment**: o imposto separado automaticamente no pagamento (PIX, boleto, cartão), o que afeta o financeiro e não só a nota.

**Princípio de projeto:** cada tributo é uma **regra cadastrada com vigência** (data inicial e final), e não um campo fixo no código. A transição vira cadastro, não reprogramação.

#### 7.2 Dados fiscais

- **Empresa:** CNPJ, inscrição estadual e municipal, regime (Simples, Presumido, Real), certificado digital A1, série e numeração das notas, ambiente (homologação ou produção).
- **Produto:** NCM, CEST, origem da mercadoria, unidade tributável, GTIN, classificação tributária de IBS/CBS (cClassTrib).
- **Serviço:** código da LC 116, código de tributação nacional e NBS, município de incidência do ISS.
- **Contato:** CPF/CNPJ com dígito verificador, IE, indicador de contribuinte, endereço completo com código IBGE.

#### 7.3 Motor de regras e cálculo

- Tabela de regras por operação (venda, devolução, remessa), UF de origem e destino, regime e NCM ou serviço, devolvendo CFOP, CST/CSOSN e alíquotas de ICMS, ICMS-ST, DIFAL, IPI, PIS, COFINS, ISS, IBS, CBS e IS, cada uma com vigência.
- Base, alíquota e valor de cada tributo gravados no item da venda, para auditoria.
- DRE passa a usar os tributos calculados nas deduções da receita, no lugar dos lançamentos manuais de hoje.

#### 7.4 Documento fiscal

- Modelo `NotaFiscal` com tipo (NF-e, NFC-e, NFS-e), número, série, chave, status (rascunho, autorizada, rejeitada, cancelada, denegada), XML enviado e de retorno, DANFE em PDF.
- Cancelamento, carta de correção e contingência.
- Guarda dos XMLs por 5 anos e envio ao contador.
- **Entrada de notas:** além do upload de XML que já existe, baixar da SEFAZ as notas emitidas contra o CNPJ (Distribuição DF-e), registrar a manifestação do destinatário e evitar importar a mesma nota duas vezes. Ler também os tributos, NCM, CFOP e chave de acesso dos itens.

#### 7.5 Como emitir

| | Biblioteca própria (ex.: PyNFe) | API de emissão (ex.: Focus NFe, Nuvem Fiscal, PlugNotas, NFE.io) |
|---|---|---|
| Custo | Sem mensalidade | Cobrança por nota ou plano mensal |
| Trabalho | Alto: montar XML, assinar, falar com cada SEFAZ e cada prefeitura, acompanhar notas técnicas | Baixo: o app envia JSON e recebe a nota autorizada |
| NFS-e | Difícil: muitas prefeituras ainda com padrões próprios | Já resolvido pelo provedor |
| Reforma tributária | Você atualiza a cada nota técnica | O provedor atualiza o layout |

**Recomendação:** API de emissão, com uma camada própria (`fiscal/emissores/`) para poder trocar de provedor. O cálculo dos tributos fica no Gestão MASC.

#### 7.6 Ordem de implementação

1. Dados fiscais da empresa e dos cadastros, com validação de CPF/CNPJ e NCM.
2. Motor de regras e cálculo por item da venda, começando pelo regime de quem vai usar o sistema primeiro (provavelmente Simples Nacional).
3. Emissão de NF-e em homologação por um provedor; depois NFS-e; depois NFC-e, se houver venda no balcão.
4. Cancelamento, carta de correção, DANFE, guarda e envio dos XMLs ao contador.
5. DRE e financeiro usando os tributos calculados; preparação para split payment.
6. Distribuição DF-e e manifestação na entrada de notas.

#### 7.7 Pré-requisitos e cuidados

- Fase 2 concluída (usuários, permissões, PostgreSQL e backup), porque notas fiscais não podem ser perdidas nem alteradas sem registro.
- Saldos de estoque corrigidos (ver `CORRECOES.md`), senão as quantidades das notas não batem com o estoque.
- O certificado digital A1 fica fora do banco e do código, com acesso restrito.

**Entrega:** venda finalizada gera a nota fiscal autorizada, com tributos calculados pelas regras vigentes na data da operação.

---

## 3. Como rodar (desenvolvimento)

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt

# criar o arquivo .env na raiz com:
# SECRET_KEY=uma-chave-secreta
# DEBUG=True
# ALLOWED_HOSTS=127.0.0.1,localhost

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Acesse `http://127.0.0.1:8000/` e entre com o usuário criado.

---

## 4. Estrutura de pastas

```
gestaomasc/
├── manage.py
├── requirements.txt
├── gestaomasc/          # settings, urls, wsgi/asgi, utils, core_s (RBAC)
├── core/                # base.html, sidebar, login, middleware, estáticos
├── cadastros/           # produtos, serviços, contatos
├── comercial/           # compras, vendas, estoque, CMV, importador XML
├── financeiro/          # categorias, lançamentos, pagar/receber, títulos, caixa
└── relatorios/          # services/ e views/ por relatório, DRE
```
