from django.db import migrations


# Contatos com CPF/CNPJ gravado só com números (os criados pela importação da NF-e)
# passam a ter a pontuação, como os cadastrados na tela
def formatar(apps, schema_editor):
    Contato = apps.get_model("cadastros", "Contato")
    for contato in Contato.objects.exclude(documento__isnull=True).exclude(documento=""):
        digitos = "".join(c for c in contato.documento if c.isdigit())
        if digitos != contato.documento:
            continue
        if len(digitos) == 14:
            novo = f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
        elif len(digitos) == 11:
            novo = f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
        else:
            continue
        contato.documento = novo
        contato.save(update_fields=["documento"])


class Migration(migrations.Migration):
    dependencies = [("cadastros", "0004_contato_categoria_padrao")]
    operations = [migrations.RunPython(formatar, migrations.RunPython.noop)]
