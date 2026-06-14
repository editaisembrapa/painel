#!/usr/bin/env python3
"""
Coletor de editais — Monitor de Editais Embrapa (Fase 1/2).

Pipeline diário:
  1. Consulta Perplexity Sonar por categoria de fonte (CNPq, FINEP, CAPES, FAPs,
     Embrapa interno, inovação) e extrai editais estruturados.
  2. Verifica que a URL de cada edital está no ar (mata link inventado).
  3. Deduplica contra o editais.json atual; preserva 'descobertoEm' dos que já
     existiam e marca a data de hoje nos novos.
  4. Reescreve public/editais.json (que o painel lê via fetch).

Opcional: se SUPABASE_URL/KEY estiverem no ambiente, faz upsert na tabela
'editais_embrapa' como fonte de verdade (visto_em / descoberto_em / ativo).

Variáveis de ambiente:
  PERPLEXITY_API_KEY   (obrigatório p/ coletar; sem ela roda só verificação+merge)
  SUPABASE_URL, SUPABASE_KEY   (opcional)
  EDITAIS_JSON  (default: ../public/editais.json relativo a este script)

Uso:
  python3 coletar.py                # ciclo completo
  python3 coletar.py --verifica     # só re-verifica links do json atual
  python3 coletar.py --dry-run      # coleta e mostra, não grava
"""
import os, sys, json, re, datetime, urllib.request, urllib.error, argparse

HOJE = datetime.date.today().isoformat()
BASE = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.environ.get("EDITAIS_JSON", os.path.join(BASE, "..", "public", "editais.json"))
MODEL = os.environ.get("PPLX_MODEL", "sonar-pro")  # fixo em Sonar Pro; sobrescrevível por env

CATEGORIAS = [
    ("Fomento federal", "editais e chamadas públicas ABERTAS do CNPq, FINEP/FNDCT e CAPES em 2026 para fomento à pesquisa, bolsas de produtividade, infraestrutura e PD&I relevantes a pesquisadores de agropecuária/Embrapa"),
    ("FAPs estaduais", "editais ABERTOS da FAPEAM (Amazonas) e outras Fundações de Amparo à Pesquisa em 2026 relevantes a pesquisadores, com foco Amazônia/agropecuária"),
    ("Embrapa interno", "chamadas internas de PD&I, transferência de tecnologia e parcerias da Embrapa / Sistema Embrapa de Gestão (SEG) abertas em 2026"),
    ("Inovação/internacional", "editais de inovação agro (Embrapii, BNDES, fundos setoriais) e internacionais (FAO, Horizon Europe) abertos em 2026 aplicáveis a pesquisa agropecuária brasileira"),
]

SCHEMA_HINT = (
    'Devolva APENAS um array JSON, cada item: '
    '{"id","titulo","orgao","origem","areas":[],"publico","valor",'
    '"prazo":"YYYY-MM-DD|null","desc","url"}. '
    'origem em ["Nacional","Estadual · AM","Interno","Internacional"]. '
    'Use SOMENTE editais reais com URL oficial. Sem texto fora do JSON.'
)

# ---------------------------------------------------------------- Perplexity
def perplexity(prompt):
    key = os.environ.get("PERPLEXITY_API_KEY")
    if not key:
        return None
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Você é um coletor preciso de editais de fomento. Nunca invente editais ou URLs."},
            {"role": "user", "content": prompt + "\n\n" + SCHEMA_HINT},
        ],
        "temperature": 0.1,
    }).encode()
    req = urllib.request.Request(
        "https://api.perplexity.ai/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.load(r)
        txt = data["choices"][0]["message"]["content"]
        return _extrai_json(txt)
    except Exception as e:
        print(f"  ! Perplexity falhou: {e}", file=sys.stderr)
        return None

def _extrai_json(txt):
    txt = re.sub(r"^```(json)?|```$", "", txt.strip(), flags=re.MULTILINE)
    m = re.search(r"\[.*\]", txt, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except Exception:
        return []

# ---------------------------------------------------------------- link check
def link_vivo(url, timeout=12):
    if not url or not re.match(r"^https?://", url):
        return False
    for metodo in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=metodo,
                headers={"User-Agent": "Mozilla/5.0 (EditaisBot)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status < 400:
                    return True
        except urllib.error.HTTPError as e:
            if e.code in (403, 405, 999):  # alguns portais bloqueiam bot mas existem
                return True
        except Exception:
            continue
    return False

# ---------------------------------------------------------------- merge
def slug(e):
    return e.get("id") or re.sub(r"[^a-z0-9]+", "-",
        (e.get("orgao","")+"-"+e.get("titulo","")).lower())[:60].strip("-")

def carrega_atual():
    try:
        with open(os.path.abspath(JSON_PATH), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def merge(atual, coletados):
    by_id = {slug(e): e for e in atual}
    visto = set()
    for c in coletados:
        sid = slug(c)
        visto.add(sid)
        if sid in by_id:
            # preserva descobertoEm; atualiza campos voláteis
            c["descobertoEm"] = by_id[sid].get("descobertoEm", HOJE)
            by_id[sid].update(c)
        else:
            c["descobertoEm"] = HOJE
            c["id"] = sid
            by_id[sid] = c
    return list(by_id.values())

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verifica", action="store_true", help="só re-verifica links do json atual")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    atual = carrega_atual()
    print(f"editais.json atual: {len(atual)} editais")

    if args.verifica:
        vivos = [e for e in atual if link_vivo(e.get("url"))]
        print(f"links vivos: {len(vivos)}/{len(atual)}")
        if not args.dry_run:
            _grava(vivos)
        return

    coletados = []
    for nome, prompt in CATEGORIAS:
        print(f"→ coletando: {nome}")
        itens = perplexity(prompt) or []
        print(f"  {len(itens)} candidatos")
        coletados.extend(itens)

    if not coletados:
        print("Nenhum coletado (PERPLEXITY_API_KEY ausente?). Mantendo json atual.")
        return

    # verificação de link antes de publicar
    verificados = []
    for c in coletados:
        if link_vivo(c.get("url")):
            verificados.append(c)
        else:
            print(f"  x link morto, descartado: {c.get('titulo','?')[:50]}")
    print(f"verificados: {len(verificados)}/{len(coletados)}")

    final = merge(atual, verificados)
    novos = [e for e in final if e.get("descobertoEm") == HOJE]
    print(f"resultado: {len(final)} editais ({len(novos)} novos hoje)")

    if args.dry_run:
        print(json.dumps(final, ensure_ascii=False, indent=2)[:2000])
        return
    _grava(final)

def _grava(lista):
    path = os.path.abspath(JSON_PATH)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=2)
    print(f"✓ gravado {path} ({len(lista)} editais)")
    _supabase_upsert(lista)

def _supabase_upsert(lista):
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not (url and key):
        return
    try:
        rows = [{
            "id": slug(e), "titulo": e.get("titulo"), "orgao": e.get("orgao"),
            "origem": e.get("origem"), "areas": e.get("areas"), "publico": e.get("publico"),
            "valor": e.get("valor"), "prazo": e.get("prazo"), "desc": e.get("desc"),
            "url": e.get("url"), "descoberto_em": e.get("descobertoEm"), "visto_em": HOJE,
            "ativo": True,
        } for e in lista]
        body = json.dumps(rows).encode()
        req = urllib.request.Request(
            f"{url}/rest/v1/editais_embrapa?on_conflict=id", data=body, method="POST",
            headers={"apikey": key, "Authorization": f"Bearer {key}",
                     "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"})
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"✓ Supabase upsert: HTTP {r.status}")
    except Exception as e:
        print(f"  ! Supabase upsert falhou: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
