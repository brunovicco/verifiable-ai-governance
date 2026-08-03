# ADR 0009 - Migrações bloqueantes no startup do Compose

## Status

Aceito.

## Date

2026-08-01.

## Context

O ambiente local usava `AUTO_CREATE_SCHEMA=true` no processo da API. O SQLAlchemy
`create_all` cria tabelas ausentes, mas não transforma tabelas existentes. Depois que a
migração `0004` adicionou `initiatives.current_review_round`, um volume persistente em
`0003` continuou incompleto. A API iniciou normalmente e só revelou a incompatibilidade
ao consultar iniciativas, retornando `500 UndefinedColumnError`.

O banco afetado continha uma iniciativa, nove aprovações e uma evidência. Recriar o
volume apagaria dados e ocultaria o defeito do processo de atualização.

## Decision

- adicionar ao Compose um serviço one-shot `migrate` que executa
  `alembic upgrade head` usando a mesma imagem e configuração da API;
- iniciar esse serviço somente depois que PostgreSQL estiver saudável;
- iniciar a API somente quando `migrate` terminar com código zero;
- definir `AUTO_CREATE_SCHEMA=false` no Compose e no `.env.example`;
- manter `create_all` somente como conveniência local explicitamente opt-in, não como
  mecanismo de upgrade;
- preservar volumes durante atualizações e documentar que `down -v` não é procedimento
  de migração;
- manter execução manual por `make migrate` quando API e banco forem iniciados fora do
  fluxo completo do Compose.

## Alternatives considered

- Continuar com `create_all`: rejeitado porque não aplica alterações em objetos
  existentes e permite que a API sirva tráfego com schema incompatível.
- Apagar o volume PostgreSQL: rejeitado porque perde dados e não representa uma
  atualização real.
- Executar Alembic no lifespan de cada processo da API: rejeitado porque mistura
  migração com serving, dificulta distinguir falhas e cria concorrência ao escalar
  réplicas.
- Depender apenas de execução manual: rejeitado no Compose porque o esquecimento só
  seria descoberto em runtime.
- Executar migração no `CMD` da API: rejeitado porque acopla o processo web a uma tarefa
  administrativa e repetiria a operação em cada réplica.

## Consequences

- o primeiro startup após uma revisão de schema pode demorar mais;
- falha de migração impede a API de iniciar, tornando o problema visível antes do
  tráfego;
- o Compose passa a mostrar um container `migrate` concluído com status zero;
- migrations precisam permanecer idempotentes quando já aplicadas e seguras para dados
  existentes;
- o ambiente sem Compose exige `make migrate` antes de `make dev-api`.

## Security and privacy impact

Preservar o volume evita perda acidental de evidências e registros de auditoria. A
migração usa a conta de banco já configurada para a API no ambiente local; ambientes
compartilhados deverão separar a identidade com privilégios de DDL da identidade de
runtime. Logs do processo registram revisão e resultado, não conteúdo de iniciativas ou
evidências. Backups e transformações de dados continuam sujeitos às mesmas regras de
proteção, retenção e acesso do banco original.

## Operational impact

`docker compose up --build` agora constrói a imagem, espera PostgreSQL, executa Alembic
e só então inicia API e portal. O operador pode inspecionar o resultado com
`docker compose logs migrate`. Uma nova tentativa segura é feita repetindo o startup
após corrigir a causa; a API não recebe fallback para um schema parcial.

A validação desta decisão atualizou um volume real de `0003` para `0004`, preservou as
contagens existentes, criou a projeção e o histórico de revisão e restaurou o endpoint
de iniciativas para `200`.

## Follow-up

- testar e documentar backup e restauração completos;
- definir uma identidade exclusiva de migração em ambientes compartilhados;
- adicionar lock operacional para impedir dois jobs de migração simultâneos fora do
  Compose local;
- adicionar smoke test de schema e endpoint ao pipeline de entrega;
- definir política de rollback por revisão, incluindo migrations não reversíveis.
