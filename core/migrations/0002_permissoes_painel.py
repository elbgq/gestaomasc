from django.contrib.auth.management import create_permissions
from django.db import migrations


def dar_permissoes_do_painel(apps, schema_editor):
    from core.grupos import GRUPOS_PADRAO, permissoes_do_grupo

    # As permissões novas só seriam criadas no fim do migrate; aqui precisamos delas antes
    app_config = apps.get_app_config("relatorios")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    # Só acrescenta as permissões do Painel; o resto dos grupos fica como está (inclusive ajustes feitos no admin)
    for nome, regras in GRUPOS_PADRAO.items():
        grupo = Group.objects.filter(name=nome).first()
        if not grupo:
            continue
        do_painel = [p for p in permissoes_do_grupo(Permission, regras)
                     if p.content_type.app_label == "relatorios" and p.codename.startswith("painel_")]
        grupo.permissions.add(*do_painel)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_grupos_padrao"),
        ("relatorios", "0002_permissoes_painel"),
    ]

    operations = [
        migrations.RunPython(dar_permissoes_do_painel, migrations.RunPython.noop),
    ]
