from django.shortcuts import redirect
from django.conf import settings
from django.core.exceptions import PermissionDenied

from core.permissoes import pode_acessar

# Este middleware exige login para qualquer página, exceto para a página de login e o admin
class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Permite acesso ao login e ao admin
        if request.path.startswith(settings.LOGIN_URL) or request.path.startswith('/admin/'):
            return self.get_response(request)

        # Bloqueia tudo que não estiver autenticado
        if not request.user.is_authenticated:
            return redirect(settings.LOGIN_URL)
        
        return self.get_response(request)
    

# Este middleware confere se o usuário tem a permissão exigida pela tela (mapa em core/permissoes.py).
# Sem permissão, o Django mostra a página core/templates/403.html.
class PermissaoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        if not match or not request.user.is_authenticated:
            return None
        if not pode_acessar(request.user, match.view_name, view_kwargs):
            raise PermissionDenied
        return None
