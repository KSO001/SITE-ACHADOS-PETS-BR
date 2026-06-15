"""
╔══════════════════════════════════════════════════════════════╗
║  ACHADOS PETS BR — Atualizador automático Mercado Livre      ║
║  Busca produtos de gato em promoção e atualiza o index.html  ║
╚══════════════════════════════════════════════════════════════╝

COMO USAR:
  1. pip install requests
  2. python atualizar_ml.py

PARA RODAR TODO DIA AUTOMATICAMENTE:
  • No celular (Termux): crontab -e
    0 9 * * * cd /caminho/do/site && python atualizar_ml.py
  • No PC (Linux/Mac): mesmo crontab acima
  • No GitHub Actions: ver ml_scheduler.yml (arquivo separado)
"""

import requests
import json
import re
import os
from datetime import datetime

# ═══════════════════════════════════════════════
#  CONFIGURAÇÕES — edite aqui
# ═══════════════════════════════════════════════

HTML_FILE = "index.html"   # caminho para o seu index.html
MAX_PRODUTOS = 12          # quantos produtos manter no site
MIN_DESCONTO = 10          # % mínimo de desconto para considerar "promo"

# Palavras-chave por categoria — busca no título do produto
CATEGORIAS = {
    "caminha":    ["caminha gato", "cama gato", "ninho gato", "hammock gato", "cama pet gato"],
    "brinquedo":  ["brinquedo gato", "varinha gato", "bolinha gato", "arranha gato brinquedo"],
    "comedouro":  ["comedouro gato", "bebedouro gato", "fonte gato", "tigela gato", "pote gato"],
    "higiene":    ["shampoo gato", "escova gato", "areia gato", "caixa areia", "tapete higiênico gato"],
    "arranhador": ["arranhador gato", "torre arranhadora", "poste sisal gato"],
    "passeio":    ["mochila gato", "caixa transporte gato", "coleira gato", "guia gato"],
    "roupa":      ["roupa gato", "roupinha gato", "fantasia gato", "blusa gato"],
    "saude":      ["suplemento gato", "vermífugo gato", "antipulgas gato", "vitamina gato"],
    "decor":      ["tigela decorativa gato", "comedouro decorativo gato", "plaquinha gato"],
}

# Emojis padrão por categoria (caso o ML não traga imagem)
EMOJI_CAT = {
    "caminha": "☁️", "brinquedo": "🪶", "comedouro": "🍽️",
    "higiene": "🧴", "arranhador": "🪵", "passeio": "🚀",
    "roupa": "👗", "saude": "💊", "decor": "🏡",
}


# ═══════════════════════════════════════════════
#  FUNÇÕES DA API DO MERCADO LIVRE
# ═══════════════════════════════════════════════

BASE_URL = "https://api.mercadolibre.com"

def buscar_produtos_ml(query: str, limite: int = 5) -> list:
    """
    Busca produtos no ML com filtro de promoção.
    API pública — sem precisar de token para leitura básica.
    """
    url = f"{BASE_URL}/sites/MLB/search"
    params = {
        "q": query,
        "limit": limite,
        "sort": "relevance",
        "category": "MLB1700",   # categoria Animais > Gatos no ML
        "tag": "good_quality_thumbnail",
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get("results", [])
    except Exception as e:
        print(f"  ⚠️  Erro ao buscar '{query}': {e}")
        return []


def calcular_desconto(item: dict) -> int:
    """Retorna o % de desconto do item (0 se não houver)."""
    preco_atual = item.get("price", 0)
    preco_original = item.get("original_price") or 0
    if preco_original and preco_original > preco_atual:
        return int((1 - preco_atual / preco_original) * 100)
    return 0


def formatar_preco(valor: float) -> str:
    """Converte float para string no formato R$ 00,00"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def detectar_badge(item: dict, desconto: int) -> str | None:
    """Define o badge do card: promo, novo ou hot."""
    tags = item.get("tags", [])
    if desconto >= 30 or "good_quality_picture" in tags:
        return "hot"
    if desconto >= MIN_DESCONTO:
        return "promo"
    if "new" in tags or item.get("condition") == "new":
        return "novo"
    return None


def item_para_produto(item: dict, categoria: str, idx: int) -> dict:
    """Converte um resultado da API ML no formato do PRODUCTS do site."""
    preco_atual   = item.get("price", 0)
    preco_original = item.get("original_price")
    desconto      = calcular_desconto(item)
    badge         = detectar_badge(item, desconto)

    nome = item.get("title", "Produto sem nome")
    # Limitar nome a ~45 caracteres para caber no card
    if len(nome) > 45:
        nome = nome[:42] + "..."

    return {
        "id":        idx,
        "name":      nome,
        "category":  categoria,
        "emoji":     EMOJI_CAT.get(categoria, "🐾"),
        "desc":      f"Encontrado no Mercado Livre com {desconto}% de desconto. Clique para ver detalhes e comprar!" if desconto else "Achado incrível no Mercado Livre. Clique para ver detalhes!",
        "price":     formatar_preco(preco_atual),
        "priceFrom": formatar_preco(preco_original) if preco_original else None,
        "store":     "ml",
        "badge":     badge,
        "link":      item.get("permalink", "#"),
    }


# ═══════════════════════════════════════════════
#  COLETA TODOS OS PRODUTOS
# ═══════════════════════════════════════════════

def coletar_produtos() -> list:
    """Busca produtos em todas as categorias e retorna lista formatada."""
    todos = []
    idx   = 1

    print("\n🔍 Buscando produtos no Mercado Livre...\n")

    for categoria, queries in CATEGORIAS.items():
        encontrados = []

        for query in queries:
            print(f"  🐾 [{categoria}] Buscando: {query}")
            resultados = buscar_produtos_ml(query, limite=3)

            for item in resultados:
                desconto = calcular_desconto(item)
                # Só inclui se tiver desconto mínimo OU for bem avaliado
                estrelas = item.get("seller", {}).get("seller_reputation", {}).get("transactions", {}).get("ratings", {}).get("positive", 0)
                if desconto >= MIN_DESCONTO or estrelas >= 0.9:
                    encontrados.append((desconto, item))

            if encontrados:
                break  # Achou produto bom nessa query, pula para próxima categoria

        if encontrados:
            # Pega o com maior desconto
            encontrados.sort(key=lambda x: x[0], reverse=True)
            _, melhor = encontrados[0]
            produto = item_para_produto(melhor, categoria, idx)
            todos.append(produto)
            print(f"  ✅ {categoria}: {produto['name']} — {produto['price']}")
            idx += 1
        else:
            print(f"  ⚠️  {categoria}: nenhum produto com desconto encontrado")

    return todos[:MAX_PRODUTOS]


# ═══════════════════════════════════════════════
#  ATUALIZA O HTML
# ═══════════════════════════════════════════════

def gerar_js_produtos(produtos: list) -> str:
    """Converte lista de produtos para string JavaScript."""
    linhas = []
    for p in produtos:
        price_from = f'"{p["priceFrom"]}"' if p["priceFrom"] else "null"
        badge      = f'"{p["badge"]}"'      if p["badge"]     else "null"
        linha = (
            f'  {{ id:{p["id"]}, name:"{p["name"]}", category:"{p["category"]}", '
            f'emoji:"{p["emoji"]}", desc:"{p["desc"]}", '
            f'price:"{p["price"]}", priceFrom:{price_from}, '
            f'store:"{p["store"]}", badge:{badge}, link:"{p["link"]}" }}'
        )
        linhas.append(linha)
    return "const PRODUCTS = [\n" + ",\n".join(linhas) + "\n];"


def atualizar_html(produtos: list):
    """Substitui o bloco PRODUCTS no index.html."""
    if not os.path.exists(HTML_FILE):
        print(f"\n❌ Arquivo '{HTML_FILE}' não encontrado!")
        print(f"   Execute o script na mesma pasta do index.html.\n")
        return False

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    # Regex que captura o bloco inteiro do PRODUCTS
    padrao = r"const PRODUCTS = \[[\s\S]*?\];"
    novo_js = gerar_js_produtos(produtos)

    if not re.search(padrao, html):
        print("\n❌ Bloco 'const PRODUCTS' não encontrado no HTML!")
        return False

    html_novo = re.sub(padrao, novo_js, html)

    # Backup do arquivo anterior
    backup = HTML_FILE.replace(".html", f"_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.html")
    with open(backup, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n💾 Backup salvo: {backup}")

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html_novo)

    print(f"✅ {HTML_FILE} atualizado com {len(produtos)} produtos!\n")
    return True


# ═══════════════════════════════════════════════
#  EXECUÇÃO
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print("╔══════════════════════════════════════════╗")
    print("║   ACHADOS PETS BR — Atualização ML       ║")
    print(f"║   {datetime.now().strftime('%d/%m/%Y %H:%M')}                        ║")
    print("╚══════════════════════════════════════════╝")

    produtos = coletar_produtos()

    if not produtos:
        print("\n⚠️  Nenhum produto encontrado. HTML não foi alterado.")
    else:
        print(f"\n📦 {len(produtos)} produtos coletados. Atualizando HTML...")
        atualizar_html(produtos)

    print("✨ Concluído!\n")
