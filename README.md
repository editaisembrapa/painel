# Monitor de Editais — Pesquisa Embrapa

Painel que coleta diariamente editais de fomento relevantes a pesquisadores da
Embrapa (CNPq, FINEP, CAPES, FAPs, chamadas internas, inovação), destaca os
**novos** e deixa cada pesquisador filtrar pela sua área. Sem login no MVP.

## Estrutura

    public/
      index.html      painel (busca, filtros, status por prazo, selo NOVO)
      editais.json    camada de dados — lida pelo painel via fetch()
    scripts/
      coletar.py      cron diário: Perplexity -> verifica link -> merge -> json
    docs/superpowers/specs/
      2026-06-13-monitor-editais-embrapa-design.md

## Como o painel funciona

- `index.html` faz `fetch('editais.json')` e renderiza no cliente.
- **Status** ("Aberto / Encerra em breve / Encerrado / A confirmar") e **dias
  restantes** são calculados do campo `prazo` vs. hoje — o painel se atualiza
  sozinho com o tempo.
- **Selo NOVO** aparece em editais com `descobertoEm` nos últimos 7 dias.
  Vem com chip de filtro "Novidades" e stat "Novos esta semana".
- Filtro por **área**: dropdown + clique na tag do card.

### Schema de um edital (`editais.json`)

    {
      "id": "cnpq-universal-2026",
      "titulo": "...",
      "orgao": "CNPq",
      "origem": "Nacional",            // Nacional | Estadual · AM | Interno | Internacional
      "areas": ["Biodiversidade", "..."],
      "publico": "...",
      "valor": "R$ ...",
      "prazo": "2026-08-31",            // ou null
      "desc": "1-2 frases",
      "url": "https://...",            // oficial, verificada no ar
      "descobertoEm": "2026-06-14"      // controla o selo NOVO
    }

## O coletor (`scripts/coletar.py`)

Pipeline: consulta Perplexity Sonar por categoria → verifica que cada URL está
no ar (descarta link morto) → deduplica contra o `editais.json` atual
(preserva `descobertoEm` dos existentes, marca hoje nos novos) → reescreve o
JSON. Opcionalmente faz upsert no Supabase.

    # ciclo completo (precisa da chave)
    PERPLEXITY_API_KEY=xxx python3 scripts/coletar.py

    # só re-verificar links do json atual (sem chave)
    python3 scripts/coletar.py --verifica

    # coletar e inspecionar sem gravar
    PERPLEXITY_API_KEY=xxx python3 scripts/coletar.py --dry-run

Variáveis: `PERPLEXITY_API_KEY` (coleta), `SUPABASE_URL`/`SUPABASE_KEY`
(upsert opcional), `EDITAIS_JSON` (caminho do json).

## Rodar localmente

    cd public && python3 -m http.server 8777
    # abrir http://127.0.0.1:8777/index.html

(Precisa ser via http — `fetch` não funciona em `file://`.)

## Agendamento (cron) — produção

Coleta **1×/dia às 08h (horário de Manaus)** com **Sonar Pro**.

Arquivos:
- `scripts/run-coletor.sh` — wrapper: carrega `.env`, roda o coletor, grava `coletor.log`.
- `scripts/crontab.txt` — linha de cron pronta (usa `CRON_TZ=America/Manaus`).
- `.env.example` — modelo das variáveis (copie para `.env` e preencha a chave).

Subir na VPS:

    cp .env.example .env          # e preencha PERPLEXITY_API_KEY
    # ajuste o caminho em scripts/crontab.txt e instale:
    crontab -l > /tmp/c 2>/dev/null; cat scripts/crontab.txt >> /tmp/c; crontab /tmp/c

Custo estimado nesse ritmo: **~US$ 5/mês (~R$ 27)** — 4 chamadas/execução, 30 execuções/mês.
Para reduzir, troque `PPLX_MODEL=sonar` no `.env` (~R$ 7/mês).

## Roadmap

- [x] **Fase 1** — painel vivo (fetch externo), selo NOVO, filtro de área,
      coletor com verificação de link, dados-semente reais.
- [ ] **Fase 1b** — substituir semente pela coleta Perplexity real + cron diário.
- [ ] **Fase 2** — Supabase como fonte de verdade; deploy VPS (Cloudflare Tunnel
      + basic auth) em `editais.rafaelbarroso.com`.
- [ ] **Fase 3** — digest por e-mail quando aparecer edital novo.
- [ ] **Fase C** — feeds estruturados por portal (CNPq/FAPs) somando à busca IA.

## Notas

- Prazos/valores são snapshot — confirmar sempre no portal oficial antes de submeter.
- Defesa anti-alucinação: todo edital guarda a URL-fonte e passa por verificação
  HTTP antes de entrar no painel.
