from django.utils.deprecation import MiddlewareMixin

class PermissionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        user = request.user

        # Usuário não autenticado → sem permissões
        if not user.is_authenticated:
            request.user._permissions_cache = set()
            return

        # Carrega permissões dos papéis do usuário
        perms = (
            user.roles
                .values_list("permissions__code", flat=True)
        )

        # Remove valores None e converte para set
        request.user._permissions_cache = set(filter(None, perms))
    