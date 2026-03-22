from django.shortcuts import redirect
from django.conf import settings

# Este middleware exige login para qualquer página, exceto para a página de login e o admin
class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        #Teste
        print("Middleware rodando:", request.path)
        # Permite acesso ao login e ao admin
        if request.path.startswith(settings.LOGIN_URL) or request.path.startswith('/admin/'):
            return self.get_response(request)

        # Bloqueia tudo que não estiver autenticado
        if not request.user.is_authenticated:
            return redirect(settings.LOGIN_URL)
        
        return self.get_response(request)
    