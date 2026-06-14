#!/usr/bin/env bash
# Wrapper do cron — Monitor de Editais Embrapa.
# Carrega o .env, roda o coletor (Sonar Pro 1x/dia) e loga a saída com data.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ="$(cd "$DIR/.." && pwd)"
LOG="$PROJ/coletor.log"

# carrega variáveis (.env ao lado do projeto): PERPLEXITY_API_KEY, etc.
if [ -f "$PROJ/.env" ]; then
  set -a; . "$PROJ/.env"; set +a
fi

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') — coletor iniciado (modelo: ${PPLX_MODEL:-sonar-pro}) ====="
  python3 "$DIR/coletar.py"
  echo "----- fim -----"
} >> "$LOG" 2>&1
