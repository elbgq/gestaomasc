# cadastros/tabela_servicos.py
#
# Reajuste anual dos serviços pela tabela de preços médios em PDF.
#   ler_tabela_pdf  -> linhas da tabela (categoria, descrição, mínimo, máximo, médio)
#   montar_previa   -> casa cada linha com um serviço do ERP e diz o que muda
#   aplicar_previa  -> grava as linhas marcadas (preço, faixa, categoria) e o histórico
#
# A tabela não tem código: o vínculo é a descrição, comparada sem acentos, maiúsculas e espaços.
# O serviço guarda a descrição como veio da tabela (descricao_tabela), para o vínculo valer mesmo
# que o nome no ERP seja mudado.
import re
import unicodedata
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from difflib import SequenceMatcher

from django.db import transaction

from .models import CategoriaServico, Servico, ReajusteServico

VALOR = re.compile(r"[\d.]+(?:,\d{1,2})?")


class TabelaInvalida(Exception):
    pass


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]+", " ", texto).strip()


def _valor(texto):
    return Decimal(texto.replace(".", "").replace(",", "."))


def _limpar(texto):
    return re.sub(r"\s+", " ", texto).strip()


def ler_texto_tabela(texto):
    # Uma linha com três valores em R$ é um serviço; a linha "Preço MÍNIMO" traz o nome da categoria
    linhas, categoria = [], ""
    for linha in texto.splitlines():
        if "MÍNIMO" in linha.upper() and "PREÇO" in linha.upper():
            categoria = _limpar(re.split(r"pre[çc]o", linha, flags=re.I)[0])
            continue
        # A leitura do PDF às vezes separa os dígitos ("R$ 23 0,00"): cada valor vai até o próximo R$
        partes = linha.split("R$")
        valores = [re.sub(r"\s+", "", p) for p in partes[1:]]
        if len(valores) != 3 or not all(VALOR.fullmatch(v) for v in valores):
            continue
        descricao = _limpar(partes[0])
        if not descricao:
            continue
        minimo, maximo, medio = (_valor(v) for v in valores)
        linhas.append({
            "categoria": categoria, "descricao": descricao,
            "minimo": minimo, "maximo": maximo, "medio": medio,
        })
    return linhas


def ler_tabela_pdf(arquivo):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise TabelaInvalida("Falta a biblioteca pypdf. Rode: pip install -r requirements.txt")
    try:
        leitor = PdfReader(arquivo)
        texto = "\n".join(p.extract_text(extraction_mode="layout") for p in leitor.pages)
    except Exception as e:
        raise TabelaInvalida(f"Não foi possível ler o PDF: {e}")
    linhas = ler_texto_tabela(texto)
    if not linhas:
        raise TabelaInvalida("Nenhum serviço com preço mínimo, máximo e médio foi encontrado no PDF.")
    return linhas, ano_do_texto(texto)


def ano_do_texto(texto):
    achado = re.search(r"\b(20\d\d)\b", texto or "")
    return int(achado.group(1)) if achado else None


def moeda(valor):
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def faixa(linha):
    # Mínimo e máximo em ordem, mesmo quando a tabela os traz invertidos
    return tuple(sorted([linha["minimo"], linha["maximo"]]))


def preco_da_linha(linha):
    # Usa o médio publicado; se a própria tabela estiver errada (mínimo acima do máximo,
    # ou médio fora da faixa), usa o meio da faixa e avisa
    minimo, maximo, medio = linha["minimo"], linha["maximo"], linha["medio"]
    if minimo <= medio <= maximo:
        return medio, ""
    menor, maior = sorted([minimo, maximo])
    meio = ((menor + maior) / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    erro = "mínimo maior que o máximo" if minimo > maximo else "médio fora da faixa mínimo–máximo"
    if meio == medio:
        return meio, f"Erro na tabela ({erro}); o médio de {moeda(medio)} confere com o meio da faixa."
    return meio, f"Erro na tabela ({erro}): usado (mínimo + máximo) / 2 = {moeda(meio)} em vez de {moeda(medio)}."


def _sugestoes(chave, servicos):
    # Serviços parecidos: um nome contido no começo do outro, ou texto muito semelhante
    pontos = []
    for s in servicos:
        nome = normalizar(s.descricao_tabela or s.descricao)
        if nome and (chave.startswith(nome) or nome.startswith(chave)):
            nota = 1.0
        else:
            nota = SequenceMatcher(None, chave, nome).ratio()
        if nota >= 0.85:
            pontos.append((nota, s))
    pontos.sort(key=lambda p: (-p[0], p[1].codsv or ""))
    return [s for _, s in pontos[:3]]


def proximo_codigo(usados=()):
    numeros = [int(c[2:]) for c in Servico.objects.values_list("codsv", flat=True)
               if c and re.fullmatch(r"SV\d+", c)]
    numeros += [int(c[2:]) for c in usados]
    return f"SV{(max(numeros) if numeros else 0) + 1:03d}"


def montar_previa(linhas):
    # Para cada linha da tabela: o serviço casado (ou sugestões) e o que muda
    servicos = list(Servico.objects.select_related("categoria"))
    por_nome = {}
    for s in servicos:
        for nome in {normalizar(s.descricao_tabela), normalizar(s.descricao)} - {""}:
            por_nome.setdefault(nome, s)

    usados, previa = set(), []
    for i, linha in enumerate(linhas):
        preco, aviso = preco_da_linha(linha)
        chave = normalizar(linha["descricao"])
        servico = por_nome.get(chave)
        if servico and servico.pk in usados:
            servico = None
        if servico:
            usados.add(servico.pk)
        previa.append({"indice": i, "linha": linha, "preco": preco, "aviso": aviso,
                       "servico": servico, "sugestoes": [], "variacao": None})

    livres = [s for s in servicos if s.pk not in usados]
    for item in previa:
        if not item["servico"]:
            item["sugestoes"] = _sugestoes(normalizar(item["linha"]["descricao"]), livres)

    for item in previa:
        servico, linha = item["servico"], item["linha"]
        if servico:
            muda_preco = servico.preco_servico != item["preco"]
            muda_dados = (
                (servico.preco_minimo, servico.preco_maximo) != faixa(linha)
                or (servico.categoria.nome if servico.categoria else "") != linha["categoria"]
                or servico.descricao_tabela != linha["descricao"]
            )
            item["situacao"] = "alterar" if muda_preco else ("dados" if muda_dados else "igual")
            if servico.preco_servico:
                item["variacao"] = ((item["preco"] / servico.preco_servico - 1) * 100).quantize(Decimal("0.1"))
        elif item["sugestoes"]:
            item["situacao"] = "vincular"
        else:
            item["situacao"] = "novo"
        item["marcado"] = item["situacao"] != "igual"

    sem_tabela = [s for s in servicos if s.pk not in usados
                  and not any(s in item["sugestoes"] for item in previa)]
    return previa, sem_tabela


@transaction.atomic
def aplicar_previa(linhas, escolhas, ano, usuario=None):
    # escolhas: {indice: {"destino": "<pk do serviço>" | "novo", "usar_descricao": bool}}
    # Devolve um resumo com o que foi feito
    resumo = {"reajustados": 0, "atualizados": 0, "criados": [], "categorias": 0}
    hoje = date.today()
    ordem_categoria = {}
    for linha in linhas:
        ordem_categoria.setdefault(linha["categoria"], len(ordem_categoria) + 1)
    codigos_novos = []

    for indice, escolha in sorted(escolhas.items()):
        linha = linhas[indice]
        preco, aviso = preco_da_linha(linha)

        categoria = None
        if linha["categoria"]:
            categoria, criada = CategoriaServico.objects.get_or_create(
                nome=linha["categoria"], defaults={"ordem": ordem_categoria[linha["categoria"]]})
            resumo["categorias"] += criada

        if escolha["destino"] == "novo":
            codigo = proximo_codigo(codigos_novos)
            codigos_novos.append(codigo)
            servico = Servico(codsv=codigo, descricao=linha["descricao"], unidade="UN")
            anterior = None
        else:
            servico = Servico.objects.get(pk=escolha["destino"])
            anterior = servico.preco_servico
            if escolha.get("usar_descricao"):
                servico.descricao = linha["descricao"]

        servico.preco_servico = preco
        servico.preco_minimo, servico.preco_maximo = faixa(linha)
        servico.categoria = categoria
        servico.descricao_tabela = linha["descricao"]
        servico.ano_tabela = ano
        if anterior != preco:
            servico.data_reajuste = hoje
        servico.save()

        if anterior is None:
            resumo["criados"].append(servico.codsv)
        elif anterior != preco:
            resumo["reajustados"] += 1
        else:
            resumo["atualizados"] += 1
        if anterior != preco:
            ReajusteServico.objects.create(
                servico=servico, usuario=usuario, ano_tabela=ano,
                preco_anterior=anterior, preco_novo=preco,
                observacao=aviso or ("Criado pela tabela" if anterior is None else ""),
            )
    return resumo
