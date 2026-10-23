from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group, User

# Grupos que só um superusuário pode atribuir
GRUPOS_RESERVADOS = ("Administrador",)


# Tela de usuários do admin com proteção contra autopromoção.
# Quem cadastra usuários sem ser superusuário (ex.: gerente com permissão delegada):
#   - não vê os campos "Superusuário" e "Permissões do usuário";
#   - só pode atribuir grupos que não estejam em GRUPOS_RESERVADOS;
#   - não vê, não altera e não troca a senha de superusuários nem de membros desses grupos.
class UsuarioAdmin(UserAdmin):
    CAMPOS_RESTRITOS = ("is_superuser", "user_permissions")
    list_display = ("username", "first_name", "last_name", "email", "funcao", "is_active", "is_staff")
    readonly_fields = ("funcao",)

    # Função do usuário = nome dos grupos dele (ex.: "Gerente, Financeiro")
    @admin.display(description="Função")
    def funcao(self, obj):
        grupos = ", ".join(g.name for g in obj.groups.all())
        if obj.is_superuser:
            return f"Superusuário ({grupos})" if grupos else "Superusuário"
        return grupos or "Sem função"

    def _restrito(self, request):
        return not request.user.is_superuser

    def get_queryset(self, request):
        qs = super().get_queryset(request).prefetch_related("groups")
        if self._restrito(request):
            qs = qs.filter(is_superuser=False).exclude(groups__name__in=GRUPOS_RESERVADOS)
        return qs

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        restrito = self._restrito(request)
        resultado = []
        for i, (nome, opcoes) in enumerate(fieldsets):
            campos = [c for c in opcoes.get("fields", ()) if not (restrito and c in self.CAMPOS_RESTRITOS)]
            # Mostra a função logo abaixo do nome de usuário (só ao editar; no cadastro novo ainda não há grupos)
            if obj is not None and i == 0:
                campos.append("funcao")
            resultado.append((nome, {**opcoes, "fields": campos}))
        return resultado

    def get_list_filter(self, request):
        filtros = super().get_list_filter(request)
        if self._restrito(request):
            filtros = [f for f in filtros if f != "is_superuser"]
        return filtros

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "groups" and self._restrito(request):
            kwargs["queryset"] = Group.objects.exclude(name__in=GRUPOS_RESERVADOS)
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def _protegido(self, request, obj):
        # Conta que um usuário restrito não pode mexer
        return (
            obj is not None and self._restrito(request)
            and (obj.is_superuser or obj.groups.filter(name__in=GRUPOS_RESERVADOS).exists())
        )

    def has_view_permission(self, request, obj=None):
        return not self._protegido(request, obj) and super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return not self._protegido(request, obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return not self._protegido(request, obj) and super().has_delete_permission(request, obj)


admin.site.unregister(User)
admin.site.register(User, UsuarioAdmin)
