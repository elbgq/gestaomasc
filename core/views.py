from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render

from core.permissoes import pode_acessar

#========================

# Início: quem pode ver algum bloco do Painel vai direto para ele; os demais veem a tela de boas-vindas
def home(request):
    if pode_acessar(request.user, "relatorios:painel"):
        return redirect("relatorios:painel")
    return render(request, "home.html")


# Tela mostrada quando a proteção CSRF recusa um formulário (ligada em settings.CSRF_FAILURE_VIEW).
# Acontece quando a página ficou aberta muito tempo, foi restaurada pelo navegador do celular
# ou o botão foi tocado duas vezes. No login, volta para a tela de entrada com um aviso.
def csrf_falhou(request, reason=""):
    if request.path.startswith(settings.LOGIN_URL):
        if request.user.is_authenticated:
            return redirect(settings.LOGIN_REDIRECT_URL)
        messages.warning(request, "A tela de entrada tinha expirado. Digite usuário e senha de novo.")
        return redirect(settings.LOGIN_URL)
    return render(request, "403_csrf.html", status=403)
