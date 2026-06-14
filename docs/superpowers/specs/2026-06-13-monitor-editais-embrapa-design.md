# Monitor de Editais — Pesquisa Embrapa

**Data:** 2026-06-13
**Dono:** Rafael Barroso
**Status:** Design aprovado

## Problema

Pesquisadores de uma unidade da Embrapa precisam acompanhar editais de fomento à
pesquisa espalhados por dezenas de portais (CNPq, FINEP, CAPES, FAPs estaduais,
chamadas internas Embrapa/SEG, inovação/internacional). Hoje isso é manual,
disperso e perde-se prazo. Queremos um painel que rode sozinho diariamente,
destaque editais novos e deixe cada pesquisador filtrar pela sua área.

## Escopo

### Fontes monitoradas
- Fomento federal: CNPq, FINEP, CAPES
- Fundações estaduais de amparo à pesquisa (FAPs) — foco inicial AM/Norte
- Chamadas internas Embrapa / SEG
- Inovação e internacionais (Embrapii, BNDES, fundos setoriais, etc.)

### Público
Vários pesquisadores de uma unidade, cada um com sua linha de pesquisa.
Filtro por área (tags), sem login no MVP.

### Entrega (faseada)
- Fase 1 (este projeto): painel web vivo + destaque de editais novos.
  Sem e-mail. Objetivo: validar a fonte de dados com dados reais.
- Fase 2 (depois): digest por e-mail quando a fonte provar confiança.

## Decisão-chave: de onde vêm os dados

Não existe API única para esses editais. Estratégia escolhida: B->C.

- B (ponto de partida): busca por IA diária (Perplexity Sonar — já pago)
  consulta as fontes, extrai registros estruturados no schema do painel, e
  verifica que o link está no ar antes de publicar (mata alucinação).
- C (evolução): plugar feeds estruturados incrementais (página de chamadas
  CNPq, RSS de FAPs) onde a fonte é limpa e de alto valor, aumentando a
  confiabilidade sem refazer nada.

Risco principal (IA inventar edital) mitigado por: (1) sempre armazenar a
URL-fonte; (2) passo de verificação HTTP do link antes de entrar no painel;
(3) badge "snapshot — confirmar no portal oficial" já presente no rodapé.

## Arquitetura

O protótipo HTML do Rafael (public/index.html) já resolve a UI: tema
agro/topográfico, busca, filtro por órgão/status, barra de janela de prazo,
stats, status calculado automaticamente a partir do campo prazo. Ponto de
integração limpo: array EDITAIS no topo do arquivo.

### Componentes

1. Camada de dados (public/editais.json)
   Extrair o array EDITAIS inline para um arquivo JSON separado que a página
   busca via fetch(). O cron só reescreve este arquivo; o HTML nunca muda.

2. Banco (Supabase: editais_embrapa)
   Schema do painel + campos de controle:
   descoberto_em (1a vez visto), visto_em (última confirmação), ativo.
   Fonte de verdade; o editais.json é gerado a partir daqui.

3. Coletor (scripts/coletar.*) — o cron
   - Consulta Perplexity Sonar por categoria de fonte
   - Extrai registros no schema
   - Deduplica contra o banco (por id / título+órgão+url)
   - Verifica link vivo (HTTP HEAD/GET)
   - Upsert no Supabase (set descoberto_em se novo, atualiza visto_em)
   - Regenera public/editais.json

4. Painel (public/index.html) — upgrades cirúrgicos:
   - Fetch do editais.json em vez de array inline
   - Selo NOVO: card mostra "NOVO" se descobertoEm <= 7 dias; chip de
     filtro "Novidades"; stat "X novos esta semana"
   - Chips de área: filtro por areas, pra cada pesquisador clicar a sua

5. Hospedagem
   VPS atrás do Cloudflare Tunnel + basic auth (mesmo padrão do dashboard do
   Stark / manual do Concierge). Ex.: editais.rafaelbarroso.com.

### Schema do edital (contrato entre coletor e painel)

    {
      id, titulo, orgao, origem, areas: [], publico, valor,
      prazo (YYYY-MM-DD | null), statusFixo (opcional),
      desc, url,
      descobertoEm (YYYY-MM-DD)   // NOVO — controla o selo NOVO
    }

## Fluxo de dados

    cron diário (VPS)
      -> coletar.* consulta Perplexity por fonte
      -> extrai + deduplica + verifica link
      -> upsert Supabase (descoberto_em / visto_em)
      -> gera public/editais.json
    painel (browser)
      -> fetch editais.json
      -> calcula status/prazo + NOVO no cliente
      -> busca / filtros (órgão, status, área, novidades)

## Tratamento de erro
- Link morto -> edital não entra (ou entra marcado "link a confirmar"), nunca
  publica URL quebrada.
- Falha da busca IA -> mantém o editais.json anterior (painel nunca fica vazio).
- IA sem resultados novos -> no-op, visto_em dos existentes não muda; nada quebra.

## Fora de escopo (YAGNI no MVP)
- Login por pesquisador / multi-tenant formal
- E-mail (fase 2)
- Scrapers dedicados por portal (entram na fase C, incremental)
- App mobile

## Plano de validação faseado
1. Upgrades de UI + dados reais coletados agora (1 passo manual de pesquisa)
   -> prova que a fonte funciona, painel vivo hoje.
2. Script coletor + Supabase.
3. Deploy VPS + cron diário.
4. (Fase 2) e-mail.
