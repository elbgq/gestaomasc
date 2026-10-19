# comercial/services/xml_importer.py
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from cadastros.models import Contato, Produto, UNIDADES_CHOICES

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}

# cStat de NF-e autorizada (100) e autorizada fora do prazo (150)
STATUS_AUTORIZADA = {"100", "150"}

UNIDADES_VALIDAS = {codigo for codigo, _ in UNIDADES_CHOICES}


def somente_digitos(valor):
    return "".join(c for c in (valor or "") if c.isdigit())


def formatar_documento(doc):
    if len(doc) == 14:
        return f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}"
    if len(doc) == 11:
        return f"{doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:]}"
    return doc


def buscar_fornecedor(documento):
    """Procura o contato pelo CPF/CNPJ, gravado com ou sem pontuação."""
    return Contato.objects.filter(
        documento__in=[documento, formatar_documento(documento)]
    ).first()


def unidade_do_cadastro(unidade_nota):
    unidade = (unidade_nota or "").strip().upper()
    return unidade if unidade in UNIDADES_VALIDAS else "UN"


def ean_valido(valor):
    ean = somente_digitos(valor)
    return ean if len(ean) in (8, 12, 13, 14) else ""


def sugerir_vinculo(fornecedor, codigo, ean):
    """Devolve (produto, fator) para um item da nota, ou (None, 1).

    1. Vínculo já gravado para este fornecedor e código.
    2. Código de barras igual ao de um produto do cadastro.
    3. Código de barras já vinculado em nota de outro fornecedor.
    """
    from comercial.models import ProdutoFornecedor

    if codigo:
        vinculo = ProdutoFornecedor.objects.filter(
            fornecedor=fornecedor, codigo_fornecedor=codigo
        ).select_related("produto").first()
        if vinculo:
            return vinculo.produto, vinculo.fator_conversao

    if ean:
        produtos = list(Produto.objects.filter(ean=ean)[:2])
        if len(produtos) == 1:
            return produtos[0], Decimal("1")
        vinculo = ProdutoFornecedor.objects.filter(ean=ean).select_related("produto").first()
        if vinculo:
            return vinculo.produto, vinculo.fator_conversao

    return None, Decimal("1")


class XmlCompraImporter:
    def _texto(self, elemento, caminho):
        if elemento is None:
            return ""
        achado = elemento.find(caminho, NS)
        return (achado.text or "").strip() if achado is not None else ""

    def __init__(self, xml_file):
        self.xml_file = xml_file
        self.avisos = []

    def _decimal(self, elemento, caminho):
        valor = self._texto(elemento, caminho).replace(",", ".")
        try:
            return Decimal(valor)
        except InvalidOperation:
            raise ValidationError("Um ou mais itens da NF-e estão incompletos ou inválidos.")

    def _valor(self, elemento, caminho):
        # Campo de valor opcional: ausente vale zero
        if not self._texto(elemento, caminho):
            return Decimal("0")
        return self._decimal(elemento, caminho)

    def _tributos(self, det):
        imposto = det.find("nfe:imposto", NS)
        icms = imposto.find("nfe:ICMS/*", NS) if imposto is not None else None
        ipi = imposto.find("nfe:IPI/nfe:IPITrib", NS) if imposto is not None else None
        pis = imposto.find("nfe:PIS/*", NS) if imposto is not None else None
        cofins = imposto.find("nfe:COFINS/*", NS) if imposto is not None else None
        return {
            "valor_icms": self._valor(icms, "nfe:vICMS"),
            "valor_icms_st": self._valor(icms, "nfe:vICMSST") + self._valor(icms, "nfe:vFCPST"),
            "valor_ipi": self._valor(ipi, "nfe:vIPI"),
            "valor_pis": self._valor(pis, "nfe:vPIS"),
            "valor_cofins": self._valor(cofins, "nfe:vCOFINS"),
        }

    def _valores_item(self, det):
        prod = det.find("nfe:prod", NS)
        return {
            "valor_frete": self._valor(prod, "nfe:vFrete"),
            "valor_seguro": self._valor(prod, "nfe:vSeg"),
            "valor_outras": self._valor(prod, "nfe:vOutro"),
            "valor_desconto": self._valor(prod, "nfe:vDesc"),
            **self._tributos(det),
        }

    def _usar_total_da_nota(self, item, det):
        # Usa o valor dos produtos informado na nota (vProd), para o total da compra
        # bater centavo a centavo com a NF-e e com as duplicatas
        valor_produtos = self._valor(det.find("nfe:prod", NS), "nfe:vProd")
        if valor_produtos and valor_produtos != item.total:
            type(item).objects.filter(pk=item.pk).update(total=valor_produtos)
            item.total = valor_produtos

    def _dados_fiscais(self, det):
        prod = det.find("nfe:prod", NS)
        imposto = det.find("nfe:imposto", NS)
        icms = imposto.find("nfe:ICMS/*", NS) if imposto is not None else None
        ipi = imposto.find("nfe:IPI/nfe:IPITrib", NS) if imposto is not None else None
        pis = imposto.find("nfe:PIS/*", NS) if imposto is not None else None
        cofins = imposto.find("nfe:COFINS/*", NS) if imposto is not None else None
        return {
            "cfop": somente_digitos(self._texto(prod, "nfe:CFOP"))[:4],
            "cest": somente_digitos(self._texto(prod, "nfe:CEST"))[:7],
            "origem": self._texto(icms, "nfe:orig")[:1],
            "cst_icms": (self._texto(icms, "nfe:CST") or self._texto(icms, "nfe:CSOSN"))[:3],
            "base_icms": self._valor(icms, "nfe:vBC"),
            "aliquota_icms": self._valor(icms, "nfe:pICMS"),
            "base_icms_st": self._valor(icms, "nfe:vBCST"),
            "aliquota_ipi": self._valor(ipi, "nfe:pIPI"),
            "cst_pis": self._texto(pis, "nfe:CST")[:2],
            "cst_cofins": self._texto(cofins, "nfe:CST")[:2],
        }

    def _duplicatas(self, root):
        duplicatas = []
        for dup in root.findall(".//nfe:cobr/nfe:dup", NS):
            vencimento = self._texto(dup, "nfe:dVenc")
            if not vencimento:
                continue
            duplicatas.append({
                "numero": self._texto(dup, "nfe:nDup")[:60],
                "vencimento": vencimento[:10],
                "valor": self._valor(dup, "nfe:vDup"),
            })
        return duplicatas

    def _ler(self):
        try:
            conteudo = self.xml_file.read()
        except AttributeError:
            with open(self.xml_file, "rb") as arquivo:
                conteudo = arquivo.read()
        if isinstance(conteudo, str):
            conteudo = conteudo.encode("utf-8")
        try:
            root = ET.fromstring(conteudo)
        except ET.ParseError:
            raise ValidationError("O arquivo enviado não é um XML válido ou está corrompido.")
        return root, conteudo.decode("utf-8", errors="replace")

    def importar(self):
        from comercial.models import Compra, CompraDuplicata, CompraItem

        root, conteudo = self._ler()

        inf = root.find(".//nfe:infNFe", NS)
        emit = root.find(".//nfe:emit", NS)
        ide = root.find(".//nfe:ide", NS)
        itens = root.findall(".//nfe:det", NS)

        if inf is None or emit is None or ide is None:
            raise ValidationError("O XML não parece ser uma NF-e válida (tags essenciais ausentes).")
        if not itens:
            raise ValidationError("A NF-e não contém itens de produto.")

        # Só aceita a nota autorizada (XML de distribuição, com o protocolo da SEFAZ)
        prot = root.find(".//nfe:protNFe/nfe:infProt", NS)
        if prot is None:
            raise ValidationError(
                "O XML não tem o protocolo de autorização da SEFAZ. "
                "Peça ao fornecedor o XML da nota autorizada (nfeProc)."
            )
        cstat = self._texto(prot, "nfe:cStat")
        if cstat not in STATUS_AUTORIZADA:
            motivo = self._texto(prot, "nfe:xMotivo")
            raise ValidationError(f"A NF-e não está autorizada (situação {cstat}: {motivo}).")

        chave = somente_digitos(self._texto(prot, "nfe:chNFe")) or somente_digitos(inf.get("Id"))
        if len(chave) != 44:
            raise ValidationError("Não foi possível ler a chave de acesso da NF-e.")

        if self._texto(ide, "nfe:tpAmb") == "2":
            raise ValidationError("Esta NF-e foi emitida em ambiente de homologação (teste) e não tem valor fiscal.")

        documento = somente_digitos(self._texto(emit, "nfe:CNPJ") or self._texto(emit, "nfe:CPF"))
        nome_fornecedor = self._texto(emit, "nfe:xNome")
        numero_nota = self._texto(ide, "nfe:nNF")
        data_emissao = (self._texto(ide, "nfe:dhEmi") or self._texto(ide, "nfe:dEmi"))[:10]
        if not (documento and nome_fornecedor and numero_nota and data_emissao):
            raise ValidationError("A NF-e está incompleta: CNPJ, Nome, Número da Nota ou Data não foram encontrados.")

        empresa = getattr(settings, "EMPRESA_CNPJ", "")
        if empresa:
            dest = root.find(".//nfe:dest", NS)
            destinatario = somente_digitos(self._texto(dest, "nfe:CNPJ") or self._texto(dest, "nfe:CPF"))
            if destinatario != empresa:
                raise ValidationError(
                    f"Esta NF-e foi emitida para outro destinatário ({formatar_documento(destinatario)})."
                )

        fornecedor = buscar_fornecedor(documento)

        if Compra.objects.filter(chave_acesso=chave).exists() or (
            fornecedor and Compra.objects.filter(
                numero_nota=numero_nota, fornecedor=fornecedor, importada=True
            ).exists()
        ):
            raise ValidationError(f"A nota {numero_nota} deste fornecedor já foi importada anteriormente.")

        with transaction.atomic():
            if fornecedor is None:
                fornecedor = Contato.objects.create(
                    nome=nome_fornecedor, tipo="FORNECEDOR", documento=documento,
                )

            compra = Compra.objects.create(
                fornecedor=fornecedor,
                data=data_emissao,
                numero_nota=numero_nota,
                valor_total=0,
                importada=True,
                chave_acesso=chave,
                xml_nfe=conteudo,
            )

            total_compra = Decimal("0.00")

            for det in itens:
                prod = det.find("nfe:prod", NS)
                descricao = self._texto(prod, "nfe:xProd")
                if not descricao:
                    raise ValidationError("Um ou mais itens da NF-e estão incompletos ou inválidos.")
                quantidade = self._decimal(prod, "nfe:qCom")
                preco = self._decimal(prod, "nfe:vUnCom").quantize(Decimal("0.0001"))
                unidade_nota = self._texto(prod, "nfe:uCom").upper()[:6]
                codigo = self._texto(prod, "nfe:cProd")[:60]
                ean = ean_valido(self._texto(prod, "nfe:cEAN"))
                ncm = somente_digitos(self._texto(prod, "nfe:NCM"))[:8]

                produto, fator = sugerir_vinculo(fornecedor, codigo, ean)

                item = CompraItem.objects.create(
                    compra=compra,
                    produto=produto,
                    descricao_importada=descricao[:200],
                    quantidade=quantidade,
                    preco_unitario=preco,
                    total=0,
                    unidade=unidade_do_cadastro(unidade_nota),
                    unidade_fornecedor=unidade_nota,
                    codigo_fornecedor=codigo,
                    ean=ean,
                    ncm=ncm,
                    fator_conversao=fator,
                    status="vinculado" if produto else "pendente",
                    **self._valores_item(det),
                    **self._dados_fiscais(det),
                )
                self._usar_total_da_nota(item, det)
                total_compra += item.valor_nota

            compra.valor_total = total_compra
            compra.save()

            for dup in self._duplicatas(root):
                CompraDuplicata.objects.create(compra=compra, **dup)

        total_nota = self._texto(root, ".//nfe:total/nfe:ICMSTot/nfe:vNF")
        if total_nota and Decimal(total_nota) != compra.valor_total:
            self.avisos.append(
                f"O total da nota (R$ {Decimal(total_nota):.2f}) é diferente da soma dos itens "
                f"(R$ {compra.valor_total:.2f}). Confira a nota antes de confirmar."
            )
        if compra.duplicatas.exists() and not compra.duplicatas_conferem:
            self.avisos.append(
                "As duplicatas da nota não somam o total da compra; informe o parcelamento manualmente."
            )

        return compra
