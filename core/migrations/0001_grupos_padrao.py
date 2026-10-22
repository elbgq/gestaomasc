from django.contrib.auth.management import create_permissions
from django.db import migrations


def criar_grupos_padrao(apps, schema_editor):
    from core.grupos import criar_grupos

    # As permissões normalmente só são criadas no fim do migrate; aqui precisamos delas antes
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    criar_grupos(apps.get_model("auth", "Group"), apps.get_model("auth", "Permission"))


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("cadastros", "0006_permissoes"),
        ("comercial", "0010_permissoes"),
        ("financeiro", "0022_permissoes"),
        ("relatorios", "0001_permissoes"),
    ]

    operations = [
        migrations.RunPython(criar_grupos_padrao, migrations.RunPython.noop),
    ]
