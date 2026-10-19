from django.db import migrations


# Produtos criados pela importação de NF-e antes desta correção ficaram sem código de origem.
# Preenche com o código do fornecedor do item da nota que criou o produto.
def preencher_codor(apps, schema_editor):
    Produto = apps.get_model("cadastros", "Produto")
    CompraItem = apps.get_model("comercial", "CompraItem")

    for produto in Produto.objects.filter(codor=""):
        item = (
            CompraItem.objects.filter(produto=produto, status="novo_produto")
            .exclude(codigo_fornecedor="")
            .order_by("id")
            .first()
        )
        if not item:
            continue
        codor = item.codigo_fornecedor[:10]
        if Produto.objects.filter(codor=codor, descricao=produto.descricao).exists():
            continue
        produto.codor = codor
        produto.save(update_fields=["codor"])


class Migration(migrations.Migration):

    dependencies = [
        ("cadastros", "0002_produto_ean_produto_ncm"),
        ("comercial", "0007_importacao_nfe_custos_duplicatas"),
    ]

    operations = [
        migrations.RunPython(preencher_codor, migrations.RunPython.noop),
    ]
