import csv

from django.http import HttpResponse
from django.shortcuts import render

from relatorios.forms import FiltroJurosForm
from relatorios.services.juros_service import juros_multas_descontos


def relatorio_juros_multas(request):
    form = FiltroJurosForm(request.GET or None)
    dados = None

    if form.is_valid():
        inicio, fim = form.cleaned_data["data_inicio"], form.cleaned_data["data_fim"]
        dados = juros_multas_descontos(inicio, fim)
        if request.GET.get("formato") == "csv":
            return exportar_csv(dados, form.cleaned_data["tipo"], inicio, fim)

    return render(request, "relatorios/financeiro/juros_multas.html", {
        "form": form,
        "dados": dados,
        "tipo": form.cleaned_data.get("tipo") if dados else "",
        "query_csv": f"{request.GET.urlencode()}&formato=csv",
    })


def _br(valor):
    return f"{valor:.2f}".replace(".", ",")


# CSV para abrir no Excel: separador ";", vírgula nos decimais e BOM para os acentos
def exportar_csv(dados, tipo, inicio, fim):
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="juros_multas_{inicio:%Y%m%d}_{fim:%Y%m%d}.csv"'
    resposta.write("﻿")
    escrita = csv.writer(resposta, delimiter=";")
    escrita.writerow(["Bloco", "Data", "Contato", "Título", "Origem", "Categoria", "Vencimento", "Dias de atraso",
                      "Valor do título", "Juros", "Multa", "Desconto", "Total"])

    for chave, nome in (("pagar", "Conta paga"), ("receber", "Conta recebida")):
        if tipo and tipo != chave:
            continue
        for l in dados[chave]["linhas"]:
            lancado = l["lancado"]
            escrita.writerow([
                nome, f"{l['data']:%d/%m/%Y}", l["contato"] or "", l["descricao"], l["origem"],
                l["categoria"].nome if lancado else "",
                f"{l['vencimento']:%d/%m/%Y}" if l["vencimento"] else "",
                "" if lancado else l["atraso"],
                "" if lancado else _br(l["valor"]),
                _br(l["juros"]), _br(l["multa"]), _br(l["desconto"]), _br(l["total"]),
            ])
    return resposta
