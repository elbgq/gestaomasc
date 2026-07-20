# cadastros/views.py
from django.views.generic import ListView, DetailView
from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.http import JsonResponse
from .models import Produto, Servico, Contato
from .forms import ProdutoForm, ServicoForm, ContatoForm
from comercial.models import CompraItem

# Adicional imports para importação via CSV
import csv
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
        return Produto.objects.all().order_by("descricao")

class ProdutoDetailView(DetailView):
    model = Produto
    template_name = "cadastros/produto_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        produto = self.object

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
            return redirect("cadastros:produto_detail", pk=obj.pk)
    else:
        form = ProdutoForm(instance=obj)
    return render(request, "cadastros/produto_form.html", {"form": form, "obj": obj})

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
    
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Contato excluído com sucesso.")
        return redirect("cadastros:contato_list")
    return render(request, "cadastros/confirm_delete.html", {"obj": obj})

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

