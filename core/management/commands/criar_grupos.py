from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

from core.grupos import criar_grupos


class Command(BaseCommand):
    help = "Cria os grupos padrão (Administrador, Gerente, Vendedor, Compras/Estoque, Financeiro)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--redefinir", action="store_true",
            help="Volta também os grupos que já existem às permissões padrão (desfaz ajustes feitos no admin).",
        )

    def handle(self, *args, **options):
        for nome, criado in criar_grupos(Group, Permission, redefinir=options["redefinir"]):
            if criado:
                situacao = "criado"
            elif options["redefinir"]:
                situacao = "redefinido"
            else:
                situacao = "já existia (mantido)"
            self.stdout.write(f"{nome}: {situacao}")
