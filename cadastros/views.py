# cadastros/views.py
from django.views.generic import ListView, DetailView
from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.http import JsonResponse
from .models import Produto, Servico, Contato, ConfiguracaoPreco
from .forms import ProdutoForm, ServicoForm, ContatoForm, ContatoUnificarForm, ConfiguracaoPrecoForm
from .services import unificar_contatos, vinculos_do_contato
from .precos import atualizar_preco_venda, recalcular_precos_automaticos, produtos_sinalizados
from comercial.models import CompraItem

# Adicional imports para importação via CSV
import csv
from decimal import Decimal
from django.contrib import messages
from django.core.files.storage import FileSystemStorage

#========================
# Produtos CRUD Views
#========================
class ProdutoListView(ListView):
    model = Produto
    template_name = "cadastros/produto_list.html"
    paginate_by = 20

    def get_queryset(self):
        return Produto.objects.all().order_by("descricao").prefetch_related("estoque_set")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Sinal de preço (abaixo do custo / fora do sugerido) de cada produto da página
        config = ConfiguracaoPreco.atual()
        for produto in context["page_obj"]:
            produto.situacao = produto.situacao_preco(config)
        return context

class ProdutoDetailView(DetailView):
    model = Produto
    template_name = "cadastros/produto_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        produto = self.object

        config = ConfiguracaoPreco.atual()
        context["config_preco"] = config
        context["custo_medio"] = produto.custo_medio
        context["preco_sugerido"] = produto.preco_sugerido(config)
        context["situacao_preco"] = produto.situacao_preco(config)

        # Histórico de compras do produto
        context["historico_compras"] = (
            CompraItem.objects
            .filter(produto=produto)
            .select_related("compra")
            .order_by("-compra__data")[:10]
        )

        return context

# 
def produto_create_ajax(request):
    if request.method == "POST":
        descricao = request.POST.get("descricao")
        preco_custo = request.POST.get("preco_custo")

        produto = Produto.objects.create(
            descricao=descricao,
            preco_custo=preco_custo,
            estoque=0
        )

        return JsonResponse({
            "id": produto.id,
            "descricao": produto.descricao
        })

    return JsonResponse({"error": "Método inválido"}, status=400)

def produto_create(request):
    if request.method == "POST":
        form = ProdutoForm(request.POST)
        if form.is_valid():
            form.save()
            avisar_preco_manual(request, form)
            # Verifica qual botão foi clicado: Salvar ou Salvar e Novo
            action = request.POST.get("action")
            if action == "save_new":
                # Redireciona para a mesma página de criação para um novo cadastro
                return redirect("cadastros:produto_create")
            else:
                # Redireciona para a lista de produtos
                return redirect("cadastros:produto_list")
    else:
        form = ProdutoForm()
    return render(request, "cadastros/produto_form.html", {"form": form})

def produto_update(request, pk):
    obj = get_object_or_404(Produto, pk=pk)
    if request.method == "POST":
        form = ProdutoForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            avisar_preco_manual(request, form)
            return redirect("cadastros:produto_detail", pk=obj.pk)
    else:
        form = ProdutoForm(instance=obj)
    return render(request, "cadastros/produto_form.html", {
        "form": form, "obj": obj,
        "custo_medio": obj.custo_medio,
        "preco_sugerido": form.sugerido,
        "config_preco": ConfiguracaoPreco.atual(),
    })


def avisar_preco_manual(request, form):
    if form.virou_manual:
        messages.warning(
            request,
            "O preço digitado é diferente do sugerido pelo custo: o produto passou a ter preço manual "
            "e não será recalculado nas próximas compras.",
        )


#=====================
# Revisão de preços de venda
#=====================
# Produtos com preço abaixo do custo ou manual fora da tolerância; aqui também se altera o markup
def revisao_precos(request):
    config = ConfiguracaoPreco.atual()
    form_config = ConfiguracaoPrecoForm(instance=config)

    if request.method == "POST":
        acao = request.POST.get("acao")

        if acao == "config":
            markup_antes = config.markup
            form_config = ConfiguracaoPrecoForm(request.POST, instance=config)
            if form_config.is_valid():
                config = form_config.save()
                msg = f"Configuração salva: markup {config.markup}%, tolerância {config.tolerancia}%."
                if config.markup != markup_antes:
                    msg += f" {recalcular_precos_automaticos()} produto(s) automático(s) recalculado(s)."
                messages.success(request, msg)
                return redirect("cadastros:revisao_precos")

        elif acao == "aplicar":
            ids = request.POST.getlist("produtos")
            alterados = 0
            for produto in Produto.objects.filter(pk__in=ids):
                produto.preco_manual = False
                produto.save(update_fields=["preco_manual"])
                if atualizar_preco_venda(produto, config):
                    alterados += 1
            if ids:
                messages.success(
                    request,
                    f"{len(ids)} produto(s) voltaram ao preço automático; {alterados} tiveram o preço alterado.",
                )
            else:
                messages.warning(request, "Marque ao menos um produto.")
            return redirect(f"{request.path}?mostrar={request.POST.get('mostrar', 'sinalizados')}")

    mostrar = request.GET.get("mostrar", "sinalizados")
    produtos = Produto.objects.order_by("descricao").prefetch_related("estoque_set")
    if mostrar == "manuais":
        produtos = produtos.filter(preco_manual=True)
        linhas = [
            {
                "produto": p, "situacao": p.situacao_preco(config), "custo": p.custo_medio,
                "sugerido": p.preco_sugerido(config), "diferenca": p.diferenca_sugerido(config),
            }
            for p in produtos
        ]
    else:
        mostrar = "sinalizados"
        linhas = produtos_sinalizados(produtos)

    return render(request, "cadastros/revisao_precos.html", {
        "config": config,
        "form_config": form_config,
        "linhas": linhas,
        "mostrar": mostrar,
        "total_manuais": Produto.objects.filter(preco_manual=True).count(),
    })

def produto_delete(request, pk):
    obj = get_object_or_404(Produto, pk=pk)
    if request.method == "POST":
        obj.delete()
        return redirect("produto_list")
    return render(request, "cadastros/confirm_delete.html", {"obj": obj})

#=====================
# Serviços CRUD Views

def servico_list(request):
    q = request.GET.get("q", "")
    qs = Servico.objects.all()
    if q:
        qs = qs.filter(descricao__icontains=q)
    paginator = Paginator(qs.order_by("codsv"), 20)
    page = request.GET.get("page")
    ctx = {"page_obj": paginator.get_page(page), "q": q}
    return render(request, "cadastros/servico_list.html", ctx)

def servico_detail(request, pk):
    obj = get_object_or_404(Servico, pk=pk)
    return render(request, "cadastros/servico_detail.html", {"obj": obj})

def servico_create(request):
    if request.method == "POST":
        form = ServicoForm(request.POST)
        if form.is_valid():
            form.save()
            # Verifica qual botão foi clicado: Salvar ou Salvar e Novo
            action = request.POST.get("action")
            if action == "save_new":
                # Redireciona para a mesma página de criação para um novo cadastro
                return redirect("cadastros:servico_create")
            else:
                # Redireciona para a lista de serviços
                return redirect("cadastros:servico_list")
    else:
        form = ServicoForm()
    return render(request, "cadastros/servico_form.html", {"form": form})

def servico_update(request, pk):
    obj = get_object_or_404(Servico, pk=pk)
    if request.method == "POST":
        form = ServicoForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            return redirect("cadastros:servico_detail", pk=obj.pk)
    else:
        form = ServicoForm(instance=obj)
    return render(request, "cadastros/servico_form.html", {"form": form, "obj": obj})

def servico_delete(request, pk):
    obj = get_object_or_404(Servico, pk=pk)
    if request.method == "POST":
        obj.delete()
        return redirect("cadastros:servico_list")
    return render(request, "cadastros/confirm_delete.html", {"obj": obj})


#==========================
# Contatos CRUD Views
#==========================
def contato_list(request):
    q = request.GET.get("q", "")
    qs = Contato.objects.all().order_by("nome")

    if q:
        qs = qs.filter(nome__icontains=q)
    paginator = Paginator(qs, 20)
    page_number =request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "cadastros/contato_list.html", {
        "page_obj": page_obj,
        "q": q,
    })

def contato_detail(request, pk):
    obj = get_object_or_404(Contato, pk=pk)
    return render(request, "cadastros/contato_detail.html", {"obj": obj})

def contato_create(request):
    form = ContatoForm(request.POST or None)
    if form.is_valid():
        obj = form.save()
        messages.success(request, "Contato criado com sucesso.")
        return redirect("cadastros:contato_detail", pk=obj.pk)
        
    return render(request, "cadastros/contato_form.html", {
        "form": form,
        "titulo": "Novo Contato"
    })

def contato_update(request, pk):
    obj = get_object_or_404(Contato, pk=pk)
    form = ContatoForm(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        messages.success(request, "Contato atualizado com sucesso.")
        return redirect("cadastros:contato_detail", pk=obj.pk)
    
    return render(request, "cadastros/contato_form.html", {
        "form": form,
        "obj": obj,
        "titulo": "Editar Contato"
    })

def contato_delete(request, pk):
    obj = get_object_or_404(Contato, pk=pk)
    vinculos = vinculos_do_contato(obj)

    # Contato com compras, vendas ou contas não pode ser apagado; o caminho é unificar
    if vinculos:
        return render(request, "cadastros/contato_unificar.html", {
            "obj": obj, "vinculos": vinculos, "bloqueado": True,
            "form": ContatoUnificarForm(remover=obj),
        })

    if request.method == "POST":
        obj.delete()
        messages.success(request, "Contato excluído com sucesso.")
        return redirect("cadastros:contato_list")
    return render(request, "cadastros/confirm_delete.html", {"obj": obj})


# Unifica um contato duplicado com outro: tudo passa para o contato escolhido e este é apagado
def contato_unificar(request, pk):
    obj = get_object_or_404(Contato, pk=pk)
    form = ContatoUnificarForm(request.POST or None, remover=obj)

    if request.method == "POST" and form.is_valid():
        manter = form.cleaned_data["manter"]
        nome = str(obj)
        unificar_contatos(manter, obj)
        messages.success(request, f'Contato "{nome}" unificado com "{manter}". Os registros dele passaram para "{manter}".')
        return redirect("cadastros:contato_detail", pk=manter.pk)

    return render(request, "cadastros/contato_unificar.html", {
        "obj": obj, "vinculos": vinculos_do_contato(obj), "form": form,
    })

#=====================
# Importação de produtos via CSV

def importar_produtos(request):
    if request.method == "POST" and request.FILES.get("csv_file"):
        csv_file = request.FILES["csv_file"]
        # Validar a extensão
        if not csv_file.name.endswith(".csv"):
            messages.error(request, "Envie um arquivo CSV válido.")
            return redirect("cadastros:produto_list")

        fs = FileSystemStorage()
        filename = fs.save(csv_file.name, csv_file)
        filepath = fs.path(filename)

        try:
            # utf-8-sig remove BOM (\ufeff) que aparece em arquivos do Excel
            with open(filepath, newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f, delimiter=';')

                # normaliza cabeçalhos
                reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]

                required_headers = {"codor", "descricao", "unidade", "preco", "marca"}
                if not required_headers.issubset(set(reader.fieldnames)):
                    messages.error(request, f"CSV inválido. Cabeçalhos esperados: {required_headers}")
                    return redirect("cadastros:produto_list")
                count_created = 0
                count_update = 0

                for row in reader:
                    try:
                        codor = row['codor'].strip()
                        descricao = row['descricao'].strip()
                        unidade = row['unidade'].strip()
                        preco = row['preco'].strip().replace(',', '.')
                        marca = row['marca'].strip()

                        # cria ou atualiza produto
                        produto, created = Produto.objects.update_or_create(
                            codor=codor,
                            descricao=descricao,
                            defaults={
                                "unidade": unidade,
                                "preco_venda": preco,
                                # Preço vindo da planilha foi definido pelo administrador
                                "preco_manual": Decimal(preco or 0) > 0,
                                "marca": marca
                            }
                        )
                        if created:
                            count_created += 1
                        else:
                            count_update += 1

                    except Exception as e:
                        messages.error(request, f"Erro ao importar linha {row}: {e}")

            messages.success(request, "Importação de produtos concluída com sucesso!")
        except Exception as e:
            messages.error(request, f"Erro ao processar arquivo: {e}")

        return redirect("cadastros:produto_list")

    return render(request, "cadastros/importar_produtos.html")
 
#=====================
# Importação de serviços via CSV

def importar_servicos(request):
    if request.method == "POST" and request.FILES.get("csv_file"):
        csv_file = request.FILES["csv_file"]
        # Validar a extensão
        if not csv_file.name.endswith(".csv"):
            messages.error(request, "Envie um arquivo CSV válido.")
            return redirect("cadastros:produto_list")

        fs = FileSystemStorage()
        filename = fs.save(csv_file.name, csv_file)
        filepath = fs.path(filename)

        try:
            # utf-8-sig remove BOM (\ufeff) que aparece em arquivos do Excel
            with open(filepath, newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f, delimiter=';')
              
                # normaliza cabeçalhos
                reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]

                required_headers = {"codsv", "descricao", "unidade", "preco_servico"}
                if not required_headers.issubset(set(reader.fieldnames)):
                    messages.error(request, f"CSV inválido. Cabeçalhos esperados: {required_headers}")
                    return redirect("cadastros:servico_list")
                count_created = 0
                count_update = 0
                
                for row in reader:
                    try:
                        codsv = row['codsv'].strip()
                        descricao = row['descricao'].strip()
                        unidade = row['unidade'].strip()
                        preco_servico = row['preco_servico'].strip().replace(',', '.')
                    
                        # cria ou atualiza serviço  
                        servico, created = Servico.objects.update_or_create(
                            codsv=codsv,
                            descricao=descricao,
                            defaults={
                                "unidade": unidade,
                                "preco_servico": preco_servico
                    
                            }
                        )
                        if created:
                            count_created += 1
                        else:
                            count_update += 1
                        
                    except Exception as e:
                        messages.error(request, f"Erro ao importar linha {row}: {e}")

            messages.success(request, "Importação de serviços concluída com sucesso!")
        except Exception as e:
            messages.error(request, f"Erro ao processar arquivo: {e}")

        return redirect("cadastros:servico_list")
    return render(request, "cadastros/importar_servicos.html")

