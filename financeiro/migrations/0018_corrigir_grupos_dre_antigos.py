from django.db import migrations

# Categorias gravadas com códigos de grupo do DRE que não existem mais na lista e por isso
# ficavam fora do DRE. Cada código antigo vai para o grupo equivalente.
def corrigir(apps, schema_editor):
    Categoria = apps.get_model("financeiro", "FinanceiroCategoria")
    Categoria.objects.filter(grupo_dre="RECEITAS_FIN").update(grupo_dre="RECEITAS_FINANCEIRAS")
    Categoria.objects.filter(grupo_dre="DESPESAS_FIN").update(grupo_dre="DESPESAS_FINANCEIRAS")
    Categoria.objects.filter(grupo_dre="IMPOSTOS_VENDAS").update(grupo_dre="ICMS")
    for categoria in Categoria.objects.filter(grupo_dre="IMPOSTOS_LUCROS"):
        nome = categoria.nome.upper()
        categoria.grupo_dre = "PIS_COFINS" if "PIS" in nome or "COFINS" in nome else "IRPJ_CSLL"
        categoria.save(update_fields=["grupo_dre"])


class Migration(migrations.Migration):
    dependencies = [("financeiro", "0017_grupos_dre_juntos")]
    operations = [migrations.RunPython(corrigir, migrations.RunPython.noop)]
