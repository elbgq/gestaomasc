import xml.etree.ElementTree as ET

from django.core.management.base import BaseCommand

from comercial.models import Compra
from comercial.services.xml_importer import NS, XmlCompraImporter


class Command(BaseCommand):
    help = (
        "Relê o XML guardado das compras importadas e preenche a classificação fiscal dos itens "
        "(CFOP, CEST, origem, CST, bases e alíquotas, ICMS, PIS e COFINS). "
        "Não altera quantidades, valores da compra, estoque nem contas a pagar."
    )

    CAMPOS_TRIBUTOS = ("valor_icms", "valor_pis", "valor_cofins")

    def handle(self, *args, **options):
        leitor = XmlCompraImporter(None)
        atualizados = 0

        for compra in Compra.objects.filter(importada=True).exclude(xml_nfe=""):
            dets = ET.fromstring(compra.xml_nfe.encode("utf-8")).findall(".//nfe:det", NS)
            itens = list(compra.itens.order_by("id"))
            if len(dets) != len(itens):
                self.stdout.write(self.style.WARNING(
                    f"Compra {compra.id}: a nota tem {len(dets)} itens e a compra {len(itens)}; ignorada."
                ))
                continue

            for det, item in zip(dets, itens):
                dados = leitor._dados_fiscais(det)
                tributos = leitor._tributos(det)
                dados.update({campo: tributos[campo] for campo in self.CAMPOS_TRIBUTOS})
                for campo, valor in dados.items():
                    setattr(item, campo, valor)
                item.save(update_fields=list(dados))

                produto = item.produto
                if produto and item.status == "novo_produto" and item.cest and not produto.cest:
                    produto.cest = item.cest
                    produto.save(update_fields=["cest"])
                atualizados += 1

        self.stdout.write(self.style.SUCCESS(f"{atualizados} itens atualizados."))
