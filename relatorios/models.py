from django.db import models


# Modelo sem tabela: existe só para guardar as permissões dos relatórios
class Relatorio(models.Model):
    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("ver_comercial", "Pode ver relatórios de compras, vendas e estoque"),
            ("ver_gerencial", "Pode ver DRE e relatório de CMV"),
            # Blocos do Painel (cada bloco só aparece para quem tem a permissão dele)
            ("painel_financeiro", "Pode ver o bloco Financeiro do Painel"),
            ("painel_vendas", "Pode ver o bloco Vendas do Painel"),
            ("painel_estoque", "Pode ver o bloco Estoque do Painel"),
            ("painel_clientes", "Pode ver o bloco Clientes do Painel"),
        ]
