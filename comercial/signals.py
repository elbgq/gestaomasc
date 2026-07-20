
# Signal para atualização de estoques após uma venda

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from comercial.models import Estoque
from cadastros.models import Produto


@receiver(post_save, sender=Produto)
def criar_estoque_para_produto(sender, instance, created, **kwargs):
    if created:
        Estoque.objects.get_or_create(
            produto=instance,
            defaults={"quantidade": 0, "preco_medio": 0}
        )

# Criar estoque automaticamente quando um Produto é criado
@receiver(post_save, sender=Produto)
def criar_estoque_para_produto(sender, instance, created, **kwargs):
    if created:
        Estoque.objects.get_or_create(
            produto=instance,
            defaults={"quantidade": 0, "preco_medio": 0}
        )

