from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import URLResolver, get_resolver, reverse

from cadastros.models import Contato, Produto
from comercial.models import Estoque
from core.grupos import GRUPOS_PADRAO
from core.permissoes import MODULOS_PROTEGIDOS, PERMISSOES, pode_acessar
from financeiro.models import FinanceiroCategoria, FinanceiroPagar


def rotas_protegidas():
    # Todas as rotas nomeadas dos módulos protegidos, como "financeiro:titulo_list"
    rotas = set()
    for item in get_resolver().url_patterns:
        if isinstance(item, URLResolver) and item.namespace in MODULOS_PROTEGIDOS:
            for p in item.url_patterns:
                if p.name:
                    rotas.add(f"{item.namespace}:{p.name}")
    return rotas


def usuario(nome, *grupos):
    user = get_user_model().objects.create_user(nome, password="x")
    for g in grupos:
        user.groups.add(Group.objects.get(name=g))
    return user


class MapaDePermissoesTest(TestCase):
    def test_toda_rota_tem_permissao_no_mapa(self):
        faltando = sorted(rotas_protegidas() - set(PERMISSOES))
        self.assertEqual(faltando, [], "Rotas sem permissão em core/permissoes.py (ficam bloqueadas)")

    def test_mapa_nao_tem_rota_inexistente(self):
        sobrando = sorted(set(PERMISSOES) - rotas_protegidas())
        self.assertEqual(sobrando, [])

    def test_permissoes_do_mapa_existem(self):
        existentes = {
            f"{p.content_type.app_label}.{p.codename}"
            for p in Permission.objects.select_related("content_type")
        }
        usadas = set()
        for regra in PERMISSOES.values():
            if callable(regra):
                regras = [regra({"tipo": "D"}), regra({"tipo": "R"})]
            else:
                regras = [regra]
            for r in regras:
                usadas.update([r] if isinstance(r, str) else r)
        self.assertEqual(sorted(usadas - existentes), [])

    def test_grupos_padrao_criados_pela_migracao(self):
        for nome in GRUPOS_PADRAO:
            grupo = Group.objects.get(name=nome)
            self.assertTrue(grupo.permissions.exists(), nome)

    def test_gerente_nao_exclui_no_financeiro(self):
        gerente = usuario("gerente", "Gerente")
        self.assertTrue(gerente.has_perm("financeiro.change_financeiropagar"))
        self.assertFalse(gerente.has_perm("financeiro.delete_financeiropagar"))
        self.assertTrue(gerente.has_perm("comercial.delete_venda"))


class AcessoPorPerfilTest(TestCase):
    def test_anonimo_vai_para_login(self):
        resp = self.client.get(reverse("comercial:venda_list"))
        self.assertRedirects(resp, "/login/", fetch_redirect_response=False)

    def test_usuario_sem_grupo_so_ve_inicio(self):
        self.client.force_login(usuario("novo"))
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        resp = self.client.get(reverse("cadastros:contato_list"))
        self.assertEqual(resp.status_code, 403)
        self.assertContains(resp, "Você não tem acesso a esta tela", status_code=403)

    def test_superusuario_acessa_tudo(self):
        admin = get_user_model().objects.create_superuser("admin", password="x")
        for rota in rotas_protegidas():
            self.assertTrue(pode_acessar(admin, rota, {"tipo": "D"}), rota)

    def test_vendedor(self):
        self.client.force_login(usuario("vendedor", "Vendedor"))
        self.assertEqual(self.client.get(reverse("comercial:venda_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("comercial:venda_create")).status_code, 200)
        self.assertEqual(self.client.get(reverse("cadastros:contato_list")).status_code, 200)
        for rota in ("financeiro:titulo_list", "financeiro:caixa_historico", "comercial:cmv_lista",
                     "comercial:compra_list", "relatorios:dre", "cadastros:produto_create"):
            self.assertEqual(self.client.get(reverse(rota)).status_code, 403, rota)

    def test_menu_do_vendedor(self):
        self.client.force_login(usuario("vendedor", "Vendedor"))
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn(reverse("comercial:venda_list"), html)
        self.assertIn(reverse("cadastros:contato_list"), html)
        self.assertNotIn("menuFinanceiro", html)
        self.assertNotIn("menuRelatorios", html)
        self.assertNotIn(reverse("comercial:compra_list"), html)
        self.assertNotIn(reverse("comercial:cmv_lista"), html)

    def test_menu_do_superusuario_mostra_tudo(self):
        self.client.force_login(get_user_model().objects.create_superuser("admin", password="x"))
        html = self.client.get(reverse("home")).content.decode()
        for menu in ("menuCadastros", "menuComercial", "menuFinanceiro", "menuRelatorios"):
            self.assertIn(menu, html)
        self.assertIn(reverse("admin:index"), html)

    def test_botoes_escondidos_sem_permissao(self):
        contato = Contato.objects.create(nome="Cliente", tipo="CLIENTE")
        self.client.force_login(usuario("vendedor", "Vendedor"))
        html = self.client.get(reverse("cadastros:contato_list")).content.decode()
        self.assertIn(reverse("cadastros:contato_update", args=[contato.pk]), html)
        self.assertNotIn(reverse("cadastros:contato_delete", args=[contato.pk]), html)

    def test_vendedor_nao_ve_custo_no_estoque(self):
        produto = Produto.objects.create(codor="P1", descricao="Produto")
        Estoque.objects.get_or_create(produto=produto)
        self.client.force_login(usuario("vendedor", "Vendedor"))
        html = self.client.get(reverse("comercial:estoque_list")).content.decode()
        self.assertNotIn("Preço Médio", html)
        resp = self.client.get(reverse("comercial:ajax_estoque", args=[produto.pk])).json()
        self.assertNotIn("preco_medio", resp)

    def test_titulo_respeita_o_tipo(self):
        categoria = FinanceiroCategoria.objects.create(nome="Despesas", tipo="D")
        titulo = FinanceiroPagar.objects.create(
            data_lancamento=date.today(), data_vencimento=date.today(), descricao="Conta",
            valor=Decimal("10.00"), categoria=categoria, origem="MANUAL",
        )
        user = usuario("receber")
        user.user_permissions.add(Permission.objects.get(codename="view_financeiroreceber"))
        self.client.force_login(user)
        resp = self.client.get(reverse("financeiro:titulo_detalhe", args=["D", titulo.pk]))
        self.assertEqual(resp.status_code, 403)
        user = get_user_model().objects.get(pk=user.pk)
        self.assertTrue(pode_acessar(user, "financeiro:titulo_detalhe", {"tipo": "R"}))

    def test_financeiro(self):
        self.client.force_login(usuario("fin", "Financeiro"))
        for rota in ("financeiro:titulo_list", "financeiro:caixa_historico", "relatorios:dre",
                     "comercial:venda_list"):
            self.assertEqual(self.client.get(reverse(rota)).status_code, 200, rota)
        for rota in ("comercial:venda_create", "cadastros:contato_create"):
            self.assertEqual(self.client.get(reverse(rota)).status_code, 403, rota)

    def test_telas_sem_parametro_abrem_para_cada_perfil(self):
        # Nenhuma tela pode dar erro 500 por causa do menu ou dos botões condicionados
        rotas = []
        for rota in sorted(rotas_protegidas()):
            try:
                rotas.append(reverse(rota))
            except Exception:
                pass  # rota com parâmetro
        for grupo in GRUPOS_PADRAO:
            self.client.force_login(usuario(f"u_{len(grupo)}_{grupo[:3]}", grupo))
            for url in rotas:
                status = self.client.get(url).status_code
                self.assertLess(status, 500, f"{grupo} {url}")


class CadastroDeUsuariosDelegadoTest(TestCase):
    # Gerente com permissão delegada para cadastrar usuários não pode se promover
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", password="x")
        self.dono = usuario("dono", "Administrador")
        self.vendedor = usuario("vendedor", "Vendedor")
        self.gerente = usuario("gerente", "Gerente")
        self.gerente.is_staff = True
        self.gerente.save()
        for codigo in ("view_user", "add_user", "change_user", "view_group"):
            self.gerente.user_permissions.add(Permission.objects.get(codename=codigo))
        self.gerente = User.objects.get(pk=self.gerente.pk)

    def _form(self, quem, obj):
        from django.contrib import admin
        from django.test import RequestFactory
        request = RequestFactory().get("/")
        request.user = quem
        return admin.site._registry[get_user_model()].get_form(request, obj)

    def test_lista_esconde_superusuario_e_administradores(self):
        self.client.force_login(self.gerente)
        html = self.client.get(reverse("admin:auth_user_changelist")).content.decode()
        self.assertIn(reverse("admin:auth_user_change", args=[self.vendedor.pk]), html)
        self.assertNotIn(reverse("admin:auth_user_change", args=[self.admin.pk]), html)
        self.assertNotIn(reverse("admin:auth_user_change", args=[self.dono.pk]), html)

    def test_nao_abre_nem_troca_senha_de_superusuario(self):
        self.client.force_login(self.gerente)
        for alvo in (self.admin, self.dono):
            for rota in ("admin:auth_user_change", "admin:auth_user_password_change"):
                resp = self.client.get(reverse(rota, args=[alvo.pk]))
                self.assertNotEqual(resp.status_code, 200, f"{rota} {alvo}")

    def test_formulario_sem_superusuario_e_sem_grupo_administrador(self):
        self.client.force_login(self.gerente)
        resp = self.client.get(reverse("admin:auth_user_change", args=[self.vendedor.pk]))
        self.assertEqual(resp.status_code, 200)
        form = self._form(self.gerente, self.vendedor)
        self.assertNotIn("is_superuser", form.base_fields)
        self.assertNotIn("user_permissions", form.base_fields)
        grupos = set(form.base_fields["groups"].queryset.values_list("name", flat=True))
        self.assertNotIn("Administrador", grupos)
        self.assertIn("Vendedor", grupos)

    def test_grupo_administrador_recusado_ao_salvar(self):
        form_class = self._form(self.gerente, self.vendedor)
        admin_grupo = Group.objects.get(name="Administrador")
        form = form_class(instance=self.vendedor, data={"groups": [admin_grupo.pk]})
        form.is_valid()
        self.assertIn("groups", form.errors)

    def test_superusuario_continua_vendo_tudo(self):
        form = self._form(self.admin, self.vendedor)
        self.assertIn("is_superuser", form.base_fields)
        self.assertIn("user_permissions", form.base_fields)
        self.assertIn("Administrador", form.base_fields["groups"].queryset.values_list("name", flat=True))

    def test_funcao_aparece_na_lista_e_no_cadastro(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse("admin:auth_user_changelist")).content.decode()
        self.assertIn("Função", html)
        self.assertIn("Vendedor", html)
        self.assertIn("Superusuário", html)
        html = self.client.get(reverse("admin:auth_user_change", args=[self.vendedor.pk])).content.decode()
        self.assertIn("Função", html)
        self.assertEqual(self.client.get(reverse("admin:auth_user_add")).status_code, 200)

    def test_gerente_tambem_ve_a_funcao(self):
        self.client.force_login(self.gerente)
        html = self.client.get(reverse("admin:auth_user_change", args=[self.vendedor.pk])).content.decode()
        self.assertIn("Função", html)
        self.assertNotIn('name="is_superuser"', html)
