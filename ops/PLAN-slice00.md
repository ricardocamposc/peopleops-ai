# Runbook — Slice 00: Repository Foundation & Guardrails

Este runbook implementa y verifica únicamente Slice 00. Requiere que la raíz Git y la rama base hayan sido confirmadas. No inicializa Git, no crea migraciones de negocio y no adelanta slices posteriores.

```bash
set -eu

# 1. Inspección inicial. La falta de .git bloquea solo operaciones Git,
# no la implementación ni las validaciones no-Git.
if [ -d .git ]; then
  git status
  git branch --show-current
  git remote -v
else
  echo "BLOQUEADO: no existe .git; continuar sin crear rama, commit, push o PR."
fi
find . -maxdepth 3 -type f | sort | sed -n '1,240p'

# 2. Validación previa obligatoria.
test -f AGENTS.md
test -f prompts/design-slice-00.md
test -f docs/slice-00-repository-foundation-guardrails.md

# 3. Relectura mínima antes de editar.
sed -n '1,260p' AGENTS.md
sed -n '1,220p' docs/08-SLICES-PLAN.md
sed -n '1,220p' docs/slice-00-repository-foundation-guardrails.md

# 4. Inspección de infraestructura actual.
find . -maxdepth 3 \( -name 'docker-compose*.yml' -o -name 'compose*.yml' -o -name '.env.example' -o -name '.gitignore' -o -name 'pyproject.toml' -o -name 'package.json' -o -name 'Makefile' \) -print

# 5. Después de implementar COMPLETAMENTE el foundation con el stack confirmado:
#    - tres apps y áreas de soporte;
#    - .gitignore/.env.example por ownership;
#    - Compose con exactamente cinco servicios;
#    - PostgreSQL separado, sin migraciones de negocio;
#    - health endpoints, CORS, Makefile, tests y README;
#    - ningún código de slices posteriores.
docker compose config
docker compose build
docker compose up -d
docker compose ps

# 6. Health checks de los dos backends.
curl --fail --silent --show-error http://localhost:8000/api/v1/health
curl --fail --silent --show-error http://localhost:8001/health

# 7. Verificaciones canónicas del repo. Si algún comando no existe,
#    reportarlo como BLOQUEADO; no sustituir el stack confirmado.
make lint
make test

# 8. Alcance y calidad.
git status
git diff --check
git diff --stat
git diff

# 9. Ownership y secretos: los comandos no deben encontrar credenciales cruzadas.
if command -v rg >/dev/null 2>&1; then
  rg -n 'SYNTHETIC_HRIS|HRIS_DATABASE|password|secret|token' apps/peopleops-api .env.example || true
  rg -n 'PEOPLEOPS_DATABASE|password|secret|token' apps/reference-mcp-server .env.example || true
  rg -n 'AnalysisInteraction|EmployeePayroll|LangGraph|LlamaIndex|HumanReview|setupWorker|mockServiceWorker|fake-api|@db|@api-utils' apps packages synthetic-hris || true
fi

# 10. No hay persistencia funcional en Slice 00: no ejecutar migraciones ni seeders.
# Si una prueba de conectividad a BD se añade, debe ser PostgreSQL, nunca SQLite,
# y debe verificarse la conexión antes de cualquier operación.

# 11. Detener el entorno.
docker compose down

# 12. Solo si la checklist está verde y el usuario autorizó Git:
# git switch -c codex/slice00
# git add <archivos-autorizados>
# git commit -m "chore(slice00): scaffold repository foundation"
# git push --set-upstream origin codex/slice00
# gh pr create --base <rama-base-real> --head codex/slice00 --title "Slice 00: Repository Foundation & Guardrails" --body-file ops/PLAN-slice00.md
```
