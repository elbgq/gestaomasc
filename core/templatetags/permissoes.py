# Consulta o mapa de core/permissoes.py nos templates, para mostrar só os links e botões que o usuário pode usar.
#
#   {% load permissoes %}
#   {% pode "financeiro:caixa_delete" as pode_excluir %}
#   {% if pode_excluir %} ... {% endif %}
#
# Para títulos, informe o tipo: {% pode "financeiro:titulo_detalhe" tipo=titulo.tipo as pode_ver %}
from django import template

from core.permissoes import pode_acessar

register = template.Library()


@register.simple_tag(takes_context=True)
def pode(context, rota, **kwargs):
    user = context.get("user")
    return bool(user) and pode_acessar(user, rota, kwargs)
