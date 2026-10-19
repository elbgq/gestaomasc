# Gestão MASC: avaliação para PMEs e proposta de módulo fiscal

*10/10/2026. Avaliação feita a partir do código da aplicação. As regras fiscais citadas devem ser confirmadas com o contador da empresa, porque a regulamentação da reforma tributária ainda está sendo publicada.*

## 1. Resposta curta

**Hoje a aplicação não atende sozinha uma PME brasileira.** Ela é uma boa base de **controle gerencial interno**: compras com importação de XML, estoque com custo médio, vendas, contas a pagar e a receber, caixa e DRE. Mas falta o que a lei exige para vender: **emitir nota fiscal e calcular os tributos**. Sem isso, a empresa continua precisando de outro sistema para faturar, e os dados ficam duplicados.

**Sim, dá para agregar um módulo fiscal**, e a estrutura atual ajuda. O app já recebe XML de NF-e na compra, o DRE já tem grupos para ICMS, ISS, PIS, COFINS, IRPJ e CSLL, e a venda já separa produto de serviço por item. O módulo entra como um app Django novo (`fiscal`), ligado a produtos, serviços e vendas.

## 2. O que já atende

| Área | Situação |
|---|---|
| Cadastros (produtos, serviços, contatos) | Atende o básico; faltam dados fiscais (NCM, CEST, código de serviço) |
| Compras | Bom: importa XML de NF-e, vincula itens, gera contas a pagar |
| Estoque | Bom: custo médio ponderado e histórico de movimentações |
| Vendas | Atende rascunho, finalização, parcelamento, recibo e CMV |
| Financeiro | Contas a pagar e a receber, títulos, caixa com abertura e fechamento |
| Relatórios | DRE gerencial, compras, vendas e CMV por período |

## 3. O que falta para atender uma PME

Em ordem de impacto:

1. **Fiscal (obrigatório por lei).** Emissão de NF-e (venda de produto), NFC-e (varejo/balcão) e NFS-e (serviço), cálculo de tributos por item, cancelamento e carta de correção, guarda dos XMLs por 5 anos. Detalhe na seção 4.
2. **Usuários e segurança.** Permissões por perfil (o esboço de papéis já existe mas está desligado), registro de quem alterou o quê, banco PostgreSQL no lugar do SQLite, backup automático e acesso pela internet com HTTPS.
3. **Bancos e recebimentos.** Boleto e PIX com baixa automática, importação de extrato (OFX) com conciliação, cadastro de contas bancárias, taxas de cartão.
4. **Comercial.** Orçamento e pedido antes da venda, devolução de venda e de compra, comissão de vendedores (o campo vendedor já existe), tabela de preços, inventário e ajuste de estoque.
5. **Contador e obrigações.** Exportação dos XMLs e relatórios para o contador; conforme o regime: apoio ao PGDAS-D (Simples Nacional) ou geração de SPED (EFD ICMS/IPI e EFD Contribuições) para Lucro Presumido e Real.
6. **Gestão.** Fluxo de caixa projetado, inadimplência, curva ABC e giro de estoque (já há templates vazios para eles), painel com indicadores.
7. **Mais de uma empresa** no mesmo sistema, comum em escritórios e grupos familiares.
8. **LGPD.** Controle de acesso a dados de clientes, registro de consentimento e exclusão sob pedido.

As fases 2 a 6 do [README](README.md) já cobrem a maior parte disso. O item 1 é o que mais muda o valor do produto e deveria subir de prioridade.

## 4. Módulo fiscal proposto

### 4.1 Por que agora: reforma tributária

A reforma (EC 132/2023, regulamentada pela LC 214/2025) troca PIS, COFINS, IPI, ICMS e ISS por **CBS** (federal), **IBS** (estados e municípios) e **Imposto Seletivo**. A transição é longa, e o sistema precisa calcular **os dois modelos ao mesmo tempo** durante anos:

| Período | O que muda |
|---|---|
| 2026 | Ano de teste: CBS 0,9% e IBS 0,1% informados na nota, compensáveis com PIS/COFINS. NF-e, NFC-e e NFS-e ganham campos de IBS/CBS. NFS-e no padrão nacional. |
| 2027 | CBS em vigor plena; PIS e COFINS extintos; IPI zerado (exceto Zona Franca); começa o Imposto Seletivo. Simples Nacional pode optar por recolher IBS/CBS fora do DAS. |
| 2029 a 2032 | ICMS e ISS caem gradualmente enquanto o IBS sobe. |
| 2033 | Só IBS, CBS e Imposto Seletivo. |

Também está previsto o **split payment**: o imposto separado automaticamente no pagamento (PIX, boleto, cartão). Isso afeta o financeiro, não só a nota.

Um módulo desenhado agora deve tratar cada tributo como uma **regra configurável com vigência (data inicial e final)**, e não como campos fixos no código. Assim a transição vira cadastro, não reprogramação.

### 4.2 O que o módulo precisa ter

**Dados da empresa:** CNPJ, inscrição estadual e municipal, regime (Simples, Presumido, Real), certificado digital A1, série e numeração das notas, ambiente (homologação ou produção).

**Dados fiscais nos cadastros:**
- Produto: NCM, CEST, origem da mercadoria, unidade tributável, GTIN, classificação tributária de IBS/CBS (cClassTrib).
- Serviço: código da LC 116, código de tributação nacional e NBS, município de incidência do ISS.
- Contato: CPF/CNPJ validado, IE, indicador de contribuinte, endereço completo com código IBGE.

**Motor de regras tributárias:** tabela de regras por operação (venda, devolução, remessa), UF de origem e destino, regime e NCM ou serviço, devolvendo CFOP, CST/CSOSN e alíquotas de ICMS, ICMS-ST, DIFAL, IPI, PIS, COFINS, ISS, IBS, CBS e IS. Cada regra tem vigência.

**Cálculo por item da venda:** base, alíquota e valor de cada tributo gravados no item, para auditoria e para o DRE usar os valores reais (hoje as deduções do DRE dependem de lançamentos manuais).

**Documento fiscal:** modelo `NotaFiscal` com tipo (NF-e, NFC-e, NFS-e), número, chave, status (rascunho, autorizada, rejeitada, cancelada, denegada), XML enviado e de retorno, DANFE em PDF, cancelamento, carta de correção e contingência.

**Entrada de notas:** além do upload de XML que já existe, baixar automaticamente da SEFAZ as notas emitidas contra o CNPJ (Distribuição DF-e) e registrar a manifestação do destinatário.

### 4.3 Como emitir: duas opções em Python

| | Biblioteca própria (ex.: PyNFe) | API de emissão (ex.: Focus NFe, Nuvem Fiscal, PlugNotas, NFE.io) |
|---|---|---|
| Custo | Sem mensalidade | Cobrança por nota ou plano mensal |
| Trabalho | Alto: montar XML, assinar, falar com cada SEFAZ e cada prefeitura, acompanhar notas técnicas | Baixo: o app envia JSON e recebe a nota autorizada |
| NFS-e | Difícil: muitas prefeituras ainda com padrões próprios | Já resolvido pelo provedor |
| Reforma tributária | Você atualiza a cada nota técnica | O provedor atualiza o layout |

**Recomendação:** usar uma API de emissão, com uma camada própria (`fiscal/emissores/`) para poder trocar de provedor depois. O cálculo dos tributos fica no Gestão MASC, para não depender do provedor nas regras do negócio.

### 4.4 Ordem de implementação sugerida

1. Dados fiscais da empresa e dos cadastros, com validação de CPF/CNPJ e NCM.
2. Motor de regras e cálculo por item da venda, começando pelo regime da empresa que vai usar o sistema primeiro.
3. Emissão de NF-e em homologação por um provedor; depois NFS-e; depois NFC-e, se houver venda no balcão.
4. Cancelamento, carta de correção, DANFE, guarda e envio dos XMLs ao contador.
5. DRE e financeiro usando os tributos calculados; preparação para split payment.
6. Distribuição DF-e e manifestação na entrada de notas.

### 4.5 Pontos de atenção

- Cada regime e cada UF muda o cálculo. Começar pelo regime de quem vai usar o sistema primeiro (provavelmente Simples Nacional) reduz muito o escopo inicial.
- O certificado digital A1 é uma senha da empresa: precisa ficar fora do banco e do código, com acesso restrito.
- Antes de emitir notas reais, é preciso corrigir os saldos de estoque gravados em dobro (ver `CORRECOES.md`), senão as quantidades das notas não vão bater com o estoque.
