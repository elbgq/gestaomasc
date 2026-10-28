from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("relatorios", "0001_permissoes"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="relatorio",
            options={
                "default_permissions": (),
                "managed": False,
                "permissions": [
                    ("ver_comercial", "Pode ver relatórios de compras, vendas e estoque"),
                    ("ver_gerencial", "Pode ver DRE e relatório de CMV"),
                    ("painel_financeiro", "Pode ver o bloco Financeiro do Painel"),
                    ("painel_vendas", "Pode ver o bloco Vendas do Painel"),
                    ("painel_estoque", "Pode ver o bloco Estoque do Painel"),
                    ("painel_clientes", "Pode ver o bloco Clientes do Painel"),
                ],
            },
        ),
    ]
