# Verifiable AI Governance

Plataforma de referência, independente de fornecedor, para cadastrar, avaliar, aprovar,
documentar e monitorar iniciativas e sistemas de IA. O MVP transforma requisitos de
governança em controles verificáveis, aprovações condicionais e evidências auditáveis.

## O que já está disponível

- portal Next.js voltado a solicitantes e aprovadores não técnicos;
- API FastAPI com autenticação preparada para OIDC;
- inventário navegável de iniciativas, sistemas, modelos e agentes, com ownership,
  versão, região, escopo de uso, autonomia, ferramentas e limites operacionais;
- estruturas persistentes preparadas para avaliações, evidências, incidentes e
  processamento internacional;
- classificação preliminar de risco e workflow condicional para Negócio, Arquitetura,
  Segurança, Infra, DevOps, Privacidade, Jurídico, Compliance e Dados;
- segregação de funções, versionamento otimista e trilha de auditoria encadeada por hash;
- PostgreSQL local, migração inicial, testes e CI.

## Início rápido com Docker

Pré-requisito: Docker Desktop.

```bash
cp .env.example .env
docker compose up --build
```

Se a porta local do PostgreSQL já estiver ocupada, use por exemplo
`POSTGRES_PORT=55432 docker compose up --build`; a comunicação interna entre os
containers continua automática.

Abra o portal em <http://localhost:3000> e a documentação da API em
<http://localhost:8000/docs>.

O ambiente local exige identidade explícita, mesmo com OIDC desligado. O portal envia
um usuário de demonstração; chamadas manuais à API devem incluir `X-User-Id` e, para
aprovações, `X-User-Areas`.

## Desenvolvimento sem Docker para as aplicações

Pré-requisitos: Python 3.12+, `uv`, Node.js 20.9+ e PostgreSQL.

```bash
make setup
docker compose up -d postgres
make dev-api
```

Em outro terminal:

```bash
make dev-web
```

## Qualidade

```bash
make test
make lint
make build
```

## Fluxo do MVP

1. O solicitante cadastra uma proposta em linguagem de negócio.
2. O motor calcula risco preliminar e explica quais áreas precisam aprovar.
3. A submissão cria um gate para cada área; gates não aplicáveis ficam registrados.
4. Um aprovador autorizado, diferente do owner, registra decisão e justificativa.
5. Uma rejeição bloqueia a iniciativa. A aprovação só ocorre quando todos os gates
   obrigatórios forem aprovados.
6. O owner vincula sistemas de IA à iniciativa aprovada e registra seus modelos e
   agentes; ativos novos permanecem em rascunho até assurance posterior.
7. Alterações usam concorrência otimista, e aposentadorias preservam o histórico.
8. Toda mudança material gera evento de auditoria com versão e cadeia de hashes.

## Autenticação OIDC

Em ambientes compartilhados, defina `APP_ENV` diferente de `local`, habilite
`OIDC_ENABLED=true` e informe `OIDC_ISSUER` e `OIDC_AUDIENCE`. A aplicação se recusa a
iniciar fora do ambiente local se OIDC estiver desabilitado. O claim configurado em
`OIDC_GROUPS_CLAIM` deve conter as áreas que o usuário pode aprovar.

## Organização

```text
apps/web                     Portal Next.js
apps/api                     API FastAPI e persistência
packages/governance-schemas Contratos e taxonomias compartilhadas
packages/policy-engine       Classificação e aprovações condicionais
packages/document-templates Templates versionados de documentos
docs                         Produto, governança, arquitetura, ADRs e backlog
```

As integrações com `policy-model-router`, `a2a-otel-kit`,
`engineering-loop-schemas`, `alicerce` e `ragforge` estão definidas como portas futuras,
sem acoplar o núcleo do MVP a esses projetos.

## Aviso

Os templates e workflows apoiam governança, privacidade e compliance, mas não
constituem parecer jurídico nem alegação de conformidade ou certificação.
