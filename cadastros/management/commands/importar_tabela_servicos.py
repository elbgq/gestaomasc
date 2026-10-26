# python manage.py importar_tabela_servicos tabela.pdf            -> só mostra o que mudaria
# python manage.py importar_tabela_servicos tabela.pdf --aplicar  -> grava (mesma regra da tela Reajuste de serviços)
from django.core.management.base import BaseCommand, CommandError

from cadastros.tabela_servicos import (
    TabelaInvalida, aplicar_previa, ler_tabela_pdf, moeda, montar_previa,
)


class Command(BaseCommand):
    help = "Reajusta os serviços pelo preço médio da tabela em PDF (sem --aplicar, só mostra a prévia)."

    def add_arguments(self, parser):
        parser.add_argument("pdf")
        parser.add_argument("--ano", type=int, help="Ano da tabela (padrão: o ano escrito no PDF)")
        parser.add_argument("--aplicar", action="store_true", help="Grava as mudanças")

    def handle(self, *args, **opts):
        try:
            linhas, ano_pdf = ler_tabela_pdf(opts["pdf"])
        except TabelaInvalida as e:
            raise CommandError(str(e))
        ano = opts["ano"] or ano_pdf
        previa, sem_tabela = montar_previa(linhas)

        escolhas = {}
        for item in previa:
            linha, servico = item["linha"], item["servico"]
            if item["situacao"] == "igual":
                continue
            if servico:
                destino = f"{servico.codsv} {moeda(servico.preco_servico)} -> {moeda(item['preco'])}"
                escolhas[item["indice"]] = {"destino": servico.pk}
            elif item["sugestoes"]:
                sugestao = item["sugestoes"][0]
                destino = f"vincular a {sugestao.codsv} -> {moeda(item['preco'])}"
                escolhas[item["indice"]] = {"destino": sugestao.pk, "usar_descricao": True}
            else:
                destino = f"NOVO -> {moeda(item['preco'])}"
                escolhas[item["indice"]] = {"destino": "novo"}
            self.stdout.write(f"[{item['situacao']}] {linha['descricao']}: {destino}")
            if item["aviso"]:
                self.stdout.write(self.style.WARNING(f"    {item['aviso']}"))

        for s in sem_tabela:
            self.stdout.write(f"[fora da tabela] {s.codsv} {s.descricao}")

        self.stdout.write(f"Tabela {ano}: {len(linhas)} serviço(s), {len(escolhas)} com mudança.")
        if not opts["aplicar"]:
            self.stdout.write("Nada foi gravado. Use --aplicar para gravar.")
            return
        resumo = aplicar_previa(linhas, escolhas, ano)
        self.stdout.write(self.style.SUCCESS(
            f"{resumo['reajustados']} reajustado(s), {resumo['atualizados']} atualizado(s), "
            f"{len(resumo['criados'])} criado(s), {resumo['categorias']} categoria(s) nova(s)."
        ))
