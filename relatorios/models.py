from django.db import models


# Modelo sem tabela: existe só para guardar as permissões dos relatórios
class Relatorio(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("ver_comercial", "Pode ver relatórios de compras, vendas e estoque"),
            ("ver_gerencial", "Pode ver DRE e relatório de CMV"),
        ]
