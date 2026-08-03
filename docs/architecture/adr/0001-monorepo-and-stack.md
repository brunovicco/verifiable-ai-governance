# ADR 0001 - Monorepo e stack inicial

- Status: aceito
- Data: 2026-07-31

## Contexto

O MVP precisa evoluir contratos, regras, API, portal, templates e documentação de forma
coordenada, com execução local simples.

## Decisão

Usar monorepo com Next.js no portal, FastAPI no backend, pacotes Python independentes
para schemas e políticas, PostgreSQL como banco transacional, `uv` para o workspace
Python e npm workspaces para o frontend.

## Consequências

- mudanças de contrato podem ser testadas no mesmo pull request;
- CI e setup ficam centralizados;
- releases independentes ainda não são prioridade;
- integrações externas ficam atrás de adapters para evitar acoplamento ao monorepo.
