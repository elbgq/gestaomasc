# Unificação de contatos duplicados: tudo o que aponta para o contato removido
# (compras, vendas, contas, lançamentos, códigos de produto do fornecedor...) passa
# para o contato mantido, e o removido é apagado.
from django.db import transaction

from .models import Contato

CAMPOS_COMPLETAVEIS = ("documento", "telefone", "email", "categoria_padrao")


# Quantos registros de cada tipo estão ligados ao contato, ex.: {"Compras": 1, "Contas a pagar": 6}
def vinculos_do_contato(contato):
    vinculos = {}
    for rel in Contato._meta.related_objects:
        if not (rel.one_to_many or rel.one_to_one):
            continue
        total = rel.related_model._default_manager.filter(**{rel.field.name: contato}).count()
        if total:
            nome = str(rel.related_model._meta.verbose_name_plural).capitalize()
            vinculos[nome] = vinculos.get(nome, 0) + total
    return vinculos


def unificar_contatos(manter, remover):
    if manter.pk == remover.pk:
        raise ValueError("Escolha um contato diferente para manter.")

    with transaction.atomic():
        for rel in Contato._meta.related_objects:
            if not (rel.one_to_many or rel.one_to_one):
                continue
            modelo, campo = rel.related_model, rel.field.name
            registros = modelo._default_manager.filter(**{campo: remover})

            # Registro que ficaria repetido no contato mantido (ex.: o mesmo código de produto
            # do fornecedor nos dois cadastros): fica o que o contato mantido já tem
            for grupo in modelo._meta.unique_together:
                if campo not in grupo:
                    continue
                outros = [c for c in grupo if c != campo]
                existentes = set(modelo._default_manager.filter(**{campo: manter}).values_list(*outros))
                for registro in registros:
                    if tuple(getattr(registro, c) for c in outros) in existentes:
                        registro.delete()
                registros = modelo._default_manager.filter(**{campo: remover})

            registros.update(**{campo: manter})

        # Dados que o contato mantido não tem são copiados do removido
        alterados = []
        for campo in CAMPOS_COMPLETAVEIS:
            if not getattr(manter, campo) and getattr(remover, campo):
                setattr(manter, campo, getattr(remover, campo))
                alterados.append(campo)
        if alterados:
            manter.save(update_fields=alterados)

        remover.delete()
    return manter
