from django.shortcuts import redirect, render

from core.permissoes import pode_acessar

#========================

# Início: quem pode ver algum bloco do Painel vai direto para ele; os demais veem a tela de boas-vindas
def home(request):
    if pode_acessar(request.user, "relatorios:painel"):
        return redirect("relatorios:painel")
    return render(request, "home.html")
