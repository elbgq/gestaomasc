"""
URL configuration for gestaomasc project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""


# gestaomasc/urls.py

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls', namespace='core')),  # Página inicial do sistema
    
    # Rotas dos apps
    path('cadastros/', include('cadastros.urls', namespace='cadastros')),
    path('comercial/', include('comercial.urls', namespace='comercial')),
    path('financeiro/', include('financeiro.urls', namespace='financeiro')),
    path('relatorios/', include('relatorios.urls', namespace='relatorios')),
]



'''
Como ficam as rotas finais
- http://localhost:8000/cadastros/ → página inicial do app Cadastros
- http://localhost:8000/cadastros/novo/ → criar novo cadastro
- http://localhost:8000/comercial/ → página inicial do app Comercial
- http://localhost:8000/comercial/pedido/ → criar pedido
- http://localhost:8000/financeiro/ → página inicial do app Financeiro
- http://localhost:8000/financeiro/relatorio/ → relatório financeiro

🔹 Boas práticas
- Organização modular: cada app cuida das suas próprias rotas.
- Nomear rotas (name='...') para facilitar uso em templates com {% url 'nome_da_rota' %}.
- Namespaces: se quiser evitar conflitos entre apps, pode usar app_name = 'cadastros' dentro
de urls.py do app e depois chamar com {% url 'cadastros:cadastros_novo' %}.

'''