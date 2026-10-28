from django.contrib.auth.management import create_permissions
from django.db import migrations

NOVAS = ("_posvenda", "_metafaturamento")


def dar_permissoes_novas(apps, schema_editor):
    from core.grupos import GRUPOS_PADRAO, permissoes_do_grupo

    # As permissões dos modelos novos só seriam criadas no fim do migrate; aqui precisamos delas antes
    app_config = apps.get_app_config("comercial")
    app_config.models_module = True
    create_permissions(app_config, apps=apps, verbosity=0)
    app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    # Só acrescenta as permissões de pós-venda e metas; o resto dos grupos fica como está
    for nome, regras in GRUPOS_PADRAO.items():
        grupo = Group.objects.filter(name=nome).first()
        if not grupo:
            continue
        novas = [p for p in permissoes_do_grupo(Permission, regras)
                 if p.content_type.app_label == "comercial" and p.codename.endswith(NOVAS)]
        grupo.permissions.add(*novas)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_permissoes_painel"),
        ("comercial", "0012_meta_posvenda"),
    ]

    operations = [
        migrations.RunPython(dar_permissoes_novas, migrations.RunPython.noop),
    ]
