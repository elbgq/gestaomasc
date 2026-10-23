# Criar Modulo Fiscal

*Projeto registrado em 22/10/2026. **Ainda não implementado**: aguarda a definição do perfil da empresa (regime tributário, UF, atividades). As regras fiscais citadas devem ser confirmadas com o contador antes da implementação, porque a regulamentação da reforma tributária ainda está sendo publicada.*

*Complementa `AVALIACAO_PME_E_MODULO_FISCAL.md` (emissão de notas) e a Fase 7 do `README.md`.*

## Resposta curta

**É possível, e a base atual ajuda.** O Gestão MASC já guarda NCM, EAN e os dados fiscais que vêm no XML das compras, separa produto de serviço em cada item da venda e tem grupos de impostos no DRE. Um app Django novo, `fiscal`, calcularia os tributos de cada venda e compra, apuraria o mês e geraria a conta a pagar de cada guia.

O módulo **calcula e organiza**; ele não substitui o contador nem emite nota sozinho. A forma de calcular depende quase toda do **regime tributário** da empresa, que ainda não está definido.

| O módulo faz | O módulo não faz |
| --- | --- |
| Calcula tributos por item (base, alíquota, valor) | Não assume a responsabilidade legal pelo cálculo |
| Apura débitos e créditos do mês e estima as guias (DAS, DARF, ICMS, ISS) | Não transmite declarações ao governo (pelo menos nas primeiras fases) |
| Lança as guias em contas a pagar e os tributos no DRE | Não emite NF-e sem um certificado digital e um emissor (fase própria) |
| Mostra a carga tributária por produto, cliente e período | Não cobre folha de pagamento (INSS, FGTS, IRRF), que fica com o contador |

## O que calcular em cada regime

O regime decide se o módulo calcula **uma guia única sobre o faturamento** (Simples) ou **cada tributo separado, com créditos** (Presumido e Real).

| | Simples Nacional | Lucro Presumido | Lucro Real |
| --- | --- | --- | --- |
| Quem pode | Faturamento até R$ 4,8 milhões/ano | Até R$ 78 milhões/ano | Qualquer empresa (obrigatório acima de R$ 78 milhões) |
| Guia principal | DAS mensal, um valor só | DARFs separados + ICMS e ISS | DARFs separados + ICMS e ISS |
| Como se calcula | Alíquota efetiva da tabela do Anexo sobre a receita do mês | IRPJ e CSLL sobre um lucro presumido (% da receita) | IRPJ e CSLL sobre o lucro contábil ajustado |
| PIS e COFINS | Dentro do DAS | 0,65% + 3% sobre a receita, sem crédito | 1,65% + 7,6%, com crédito das compras |
| ICMS | Dentro do DAS (exceto ST e DIFAL) | Débito na venda menos crédito na compra | Débito na venda menos crédito na compra |
| Dificuldade para o módulo | Baixa a média | Média | Alta (depende da contabilidade completa) |

**Simples Nacional.** O módulo somaria a receita bruta dos últimos 12 meses (RBT12), escolheria a faixa do Anexo (I comércio, II indústria, III, IV ou V serviços) e aplicaria:

    Alíquota efetiva = (RBT12 × Alíquota nominal − Parcela a deduzir) / RBT12

Depois separaria as receitas com tratamento especial: produto com ICMS já pago por substituição, produto monofásico de PIS/COFINS (combustíveis, autopeças, bebidas, cosméticos e outros) e venda para o exterior. Essas parcelas saem do DAS; esquecer delas faz pagar imposto em dobro. Para serviços entra o **Fator R** (folha dos 12 meses ÷ receita), que move a atividade entre os Anexos III e V; o total da folha vem do contador.

**Presumido e Real.** O módulo calcularia PIS, COFINS, ICMS, IPI e ISS por nota e faria a apuração do mês. IRPJ e CSLL são trimestrais: no Presumido dá para calcular com segurança (presunção de 8% e 12% no comércio, 32% nos serviços, adicional de 10% de IRPJ sobre o que passar de R$ 60 mil no trimestre); no Real, só como estimativa. *Há mudança recente que aumenta as presunções para faturamento acima de R$ 5 milhões; confirmar com o contador.*

## Tributos por operação

Cada item de venda ou compra recebe base, alíquota e valor de cada tributo, decididos por **NCM ou código de serviço, UF de origem e destino, tipo de cliente e regime**. O resultado também traz CFOP e CST (ou CSOSN, no Simples).

| Tributo | Quando incide | O que o módulo precisa saber |
| --- | --- | --- |
| ICMS próprio | Venda de mercadoria | Alíquota interna da UF; interestadual de 12%, 7% ou 4% (importados); reduções de base por NCM |
| ICMS-ST | Produtos da lista de substituição (CEST) | MVA por NCM e UF; base = (valor + IPI + frete) × (1 + MVA); ST = base × alíquota interna − ICMS próprio. Na revenda o ICMS já foi pago |
| DIFAL | Venda para consumidor final de outra UF | Diferença entre a alíquota do destino e a interestadual |
| IPI | Só indústria ou importador | Alíquota da TIPI pelo NCM. No comércio, o IPI da compra entra no custo |
| PIS e COFINS | Receita (Presumido e Real) | Cumulativo ou não; monofásicos e alíquota zero por NCM; créditos no Real |
| ISS | Serviços | Item da LC 116 e município onde é devido; 2% a 5% por prefeitura |

**A nosso favor:** o XML de compra já traz CST, CFOP, alíquotas e valores de ICMS, ST, IPI, PIS e COFINS de cada item. Isso serve como sugestão inicial de tributação do produto e para calcular os créditos, hoje só na configuração `COMPRA_CREDITOS`.

**Taxas** (alvará, TFE, bombeiros, conselhos de classe) são valores fixos do ano: cabem num cadastro de obrigações recorrentes que gera a conta a pagar no vencimento.

## Reforma tributária

A reforma (EC 132/2023 e LC 214/2025) troca cinco tributos por três: **CBS** (no lugar de PIS e COFINS), **IBS** (no lugar de ICMS e ISS) e **Imposto Seletivo**. Até 2033 o módulo calcula **os dois sistemas ao mesmo tempo**, por isso cada alíquota precisa de data de início e fim.

| Ano | Sistema atual | Sistema novo |
| --- | --- | --- |
| 2026 | Tudo como antes | CBS 0,9% e IBS 0,1% só informados na nota, compensáveis; Simples dispensado |
| 2027 e 2028 | PIS e COFINS extintos; IPI zerado (exceto Zona Franca); ICMS e ISS integrais | CBS cheia; IBS 0,1%; começa o Imposto Seletivo |
| 2029 a 2032 | ICMS e ISS caem para 90%, 80%, 70% e 60% | IBS sobe na mesma proporção |
| 2033 | ICMS e ISS extintos | Só CBS, IBS e Imposto Seletivo |

- **Crédito amplo:** quase toda compra gera crédito de IBS/CBS, então o imposto de cada compra precisa ser registrado.
- **Classificação própria:** cada produto ganha um cClassTrib (alíquota cheia, reduzida em 60% ou 30%, ou zero).
- **Split payment:** o imposto poderá ser separado no pagamento (PIX, boleto, cartão); o valor que cai no banco será menor que o da venda.
- **Simples a partir de 2027:** a empresa poderá recolher IBS/CBS fora do DAS para o cliente aproveitar o crédito; o módulo pode simular essa escolha.

## Arquitetura

App `fiscal` com cinco peças. Regra de ouro: **nenhuma alíquota escrita no código**; tudo é tabela com vigência.

1. **Parâmetros da empresa:** regime, UF e município, CNAE, Anexo do Simples, inscrições, data de início de cada regime.
2. **Tabelas de referência:** NCM, CEST, TIPI, alíquotas de ICMS por UF, MVA de ST, LC 116, Anexos do Simples, cClassTrib. Cada linha com data inicial e final.
3. **Perfil tributário do produto e do serviço:** ST, monofásico, origem, reduções. Pré-preenchido pelo XML de compra.
4. **Motor de cálculo:** função Python pura que recebe a operação (item, valor, cliente, data, UF) e devolve os tributos com CFOP e CST. Testada com casos reais fornecidos pelo contador.
5. **Apuração mensal:** soma débitos e créditos, calcula DAS ou DARFs, gera o título em contas a pagar e alimenta o DRE com os valores reais.

O resultado é gravado por item (tabela `TributoItem`), para que vendas antigas mantenham o imposto da época.

**De onde vêm as regras:**

| Opção | Como funciona | Custo | Risco |
| --- | --- | --- | --- |
| A. Regras próprias | Você e o contador cadastram as regras dos NCMs vendidos | Sem mensalidade | Desatualizar; viável com poucos NCMs e uma UF |
| B. Base tributária contratada | Serviço especializado devolve a tributação por NCM e UF via API | Mensalidade | Dependência do fornecedor; ainda precisa conferência |
| C. Híbrida (recomendada) | Regras próprias, sugeridas pelo XML e validadas pelo contador; base contratada só se o mix crescer | Baixo no início | Revisão periódica com o contador |

## Limites

**A responsabilidade pelo imposto continua da empresa, e a validação continua do contador.** O módulo é ferramenta de cálculo e conferência.

- **Validação:** cada regra aprovada pelo contador; os primeiros dois ou três meses rodam em paralelo com a apuração dele.
- **Emissão de NF-e:** etapa separada (certificado A1, credenciamento na SEFAZ, NFS-e nacional). Recomendação: API de emissão, cálculo no Gestão MASC.
- **Obrigações acessórias:** PGDAS-D, DEFIS, SPED Fiscal, EFD Contribuições, DCTFWeb. O módulo prepara e exporta; transmitir é outro projeto.
- **Manutenção permanente:** a legislação muda várias vezes por ano, ainda mais até 2033.
- **Qualidade dos dados:** NCM e perfil corretos em cada produto; corrigir antes os saldos de estoque em dobro.

## Fases

1. **Definição com o contador:** regime, UF, município, atividades, Anexo, NCMs vendidos e quais têm ST ou são monofásicos.
2. **Cadastro fiscal:** parâmetros, tabelas com vigência, perfil dos produtos e serviços.
3. **Cálculo por item:** venda e compra mostram e gravam os tributos, só para conferência.
4. **Apuração mensal:** guia estimada, título automático em contas a pagar, DRE com tributos reais; meses em paralelo com o contador.
5. **Reforma tributária:** cClassTrib, CBS/IBS lado a lado, simulação da opção do Simples, split payment.
6. **Emissão de notas:** NF-e e NFS-e por API de emissão.
7. **Exportação para o contador:** XMLs, livros e resumos.

As fases 1 a 4 entregam a maior parte do valor gerencial.

## Pendências para iniciar

- [ ] Regime tributário: Simples Nacional, Lucro Presumido ou Lucro Real?
- [ ] UF e município; vende para outros estados?
- [ ] Vende mercadoria, serviço ou os dois? Fabrica algo?
- [ ] O contador valida as regras e roda os meses em paralelo?
