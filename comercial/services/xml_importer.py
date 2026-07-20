# comercial/services/xml_importer.py
import xml.etree.ElementTree as ET
from decimal import Decimal
from django.utils import timezone
from cadastros.models import Contato
from comercial.models import Compra, CompraItem
import xml.etree.ElementTree as ET
from decimal import Decimal
from django.core.exceptions import ValidationError


import xml.etree.ElementTree as ET
from decimal import Decimal
from django.core.exceptions import ValidationError

class XmlCompraImporter:
    def __init__(self, xml_file):
        self.xml_file = xml_file

    def importar(self):
        # 1. Validar XML bem-formado
        try:
            tree = ET.parse(self.xml_file)
            root = tree.getroot()
        except ET.ParseError:
            raise ValidationError("O arquivo enviado não é um XML válido ou está corrompido.")
        except Exception:
            raise ValidationError("Não foi possível ler o arquivo XML.")

        # 2. Detectar namespace
        try:
            ns_uri = root.tag.split("}")[0].strip("{")
            ns = {"nfe": ns_uri}
        except Exception:
            raise ValidationError("Não foi possível identificar o namespace da NF-e.")

        # 3. Validar estrutura mínima
        emit = root.find(".//nfe:emit", ns)
        ide = root.find(".//nfe:ide", ns)
        itens = root.findall(".//nfe:det", ns)

        if emit is None or ide is None:
            raise ValidationError("O XML não parece ser uma NF-e válida (tags essenciais ausentes).")

        if not itens:
            raise ValidationError("A NF-e não contém itens de produto.")

        # 4. Validar campos essenciais
        try:
            cnpj = emit.find("nfe:CNPJ", ns).text.strip()
            nome_fornecedor = emit.find("nfe:xNome", ns).text.strip()
            numero_nota = ide.find("nfe:nNF", ns).text.strip()
            data_emissao = ide.find("nfe:dhEmi", ns).text[:10]
        except Exception:
            raise ValidationError("A NF-e está incompleta: CNPJ, Nome, Número da Nota ou Data não foram encontrados.")

        # 5. Validar duplicidade
        from comercial.models import Compra, CompraItem
        from cadastros.models import Contato

        if Compra.objects.filter(numero_nota=numero_nota, fornecedor__cnpj=cnpj).exists():
            raise ValidationError(f"A nota {numero_nota} deste fornecedor já foi importada anteriormente.")

        # 6. Criar fornecedor
        fornecedor, _ = Contato.objects.get_or_create(
            cnpj=cnpj,
            defaults={"nome": nome_fornecedor}
        )

        # 7. Criar compra
        compra = Compra.objects.create(
            fornecedor=fornecedor,
            data=data_emissao,
            numero_nota=numero_nota,
            valor_total=0,
            importada=True
        )

        total_compra = Decimal("0.00")

        # 8. Importar itens
        for det in itens:
            try:
                prod = det.find("nfe:prod", ns)
                descricao = prod.find("nfe:xProd", ns).text.strip()
                quantidade = Decimal(prod.find("nfe:qCom", ns).text.replace(",", "."))
                preco = Decimal(prod.find("nfe:vUnCom", ns).text.replace(",", "."))
                unidade = prod.find("nfe:uCom", ns)
                unidade = unidade.text if unidade is not None else "UN"
            except Exception:
                raise ValidationError("Um ou mais itens da NF-e estão incompletos ou inválidos.")

            total = quantidade * preco
            total_compra += total

            CompraItem.objects.create(
                compra=compra,
                descricao_importada=descricao,
                quantidade=quantidade,
                preco_unitario=preco,
                total=total,
                unidade=unidade,
                status="pendente"
            )

        compra.valor_total = total_compra
        compra.save()

        return compra
