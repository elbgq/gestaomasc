from functools import wraps
from django.http import HttpResponseForbidden

def permission_required(permission_code):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user

            # Usuário não autenticado
            if not user.is_authenticated:
                return HttpResponseForbidden("Usuário não autenticado.")

            # Permissões carregadas pelo middleware
            user_permissions = getattr(user, "_permissions_cache", set())

            # Verifica permissão
            if permission_code not in user_permissions:
                return HttpResponseForbidden(f"Permissão negada: {permission_code}")

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
