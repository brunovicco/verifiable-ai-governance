# ADR 0015 - Retry limitado para leituras do Microsoft Graph

## Status

Aceito.

## Date

2026-08-01.

## Context

O adapter Microsoft Graph via OBO já limitava timeout, paginação, tamanho de resposta e
`Retry-After`, mas devolvia a primeira ocorrência de `429` ou falha `5xx` ao chamador.
Falhas transitórias podiam interromper a resolução de grupos usada em aprovações, ao
mesmo tempo em que um retry irrestrito poderia manter requests interativas abertas,
agravar throttling e aumentar a carga sobre o Graph.

A orientação oficial do Microsoft Graph recomenda respeitar `Retry-After` em `429` e
usar backoff quando o header não existir. A integração também precisa produzir sinal
operacional suficiente para detectar throttling sem registrar token, usuário ou
conteúdo do diretório.

## Decision

O adapter repetirá somente leituras idempotentes de perfil e grupos para os status
`429`, `500`, `502`, `503` e `504`, além de timeout e erro de transporte. O total de
tentativas é configurado por `MICROSOFT_GRAPH_MAX_ATTEMPTS` e inclui a primeira chamada.

Quando houver `Retry-After` numérico, o adapter respeitará o valor somente se estiver
dentro de `MICROSOFT_GRAPH_MAX_RETRY_DELAY_SECONDS`. Um atraso maior falha rápido e
preserva um valor limitado para o chamador. Sem header válido, o adapter usa backoff
exponencial com jitter injetável e limite local.

A troca OBO não será repetida automaticamente. Ela é uma operação `POST` no provedor de
identidade e não pertence ao conjunto explicitamente idempotente desta política.

O adapter emitirá eventos de log `microsoft_graph_retry`,
`microsoft_graph_retry_deferred` e `microsoft_graph_retry_exhausted` com operação,
status, tentativa e atraso. Os eventos não conterão URL, token, tenant, object ID,
perfil, grupos nem corpo remoto.

## Alternatives considered

- Não repetir nenhuma chamada: rejeitado porque transforma throttling curto e falha
  transitória em indisponibilidade imediata.
- Repetir toda operação HTTP, inclusive OBO: rejeitado porque amplia o escopo além de
  operações reconhecidamente idempotentes.
- Repetir indefinidamente conforme `Retry-After`: rejeitado por bloquear requests
  interativas e aumentar risco de cascata.
- Ignorar `Retry-After` e usar somente backoff local: rejeitado por contrariar o sinal
  explícito de throttling do serviço.
- Adotar SDK Microsoft Graph apenas para obter retry automático: rejeitado nesta etapa
  porque o adapter HTTP atual já mantém superfície e contrato reduzidos.

## Consequences

Falhas transitórias curtas podem ser absorvidas sem alterar o contrato da aplicação.
O tempo máximo da operação aumenta de forma limitada pelo número de tentativas,
timeouts e orçamento de atraso configurados. A política permanece testável porque
sleep e jitter são colaboradores injetáveis.

Não há migração de banco nem persistência nova. Cache e revogação não são resolvidos por
esta decisão.

## Security and privacy impact

Retry não pode promover um usuário: se o orçamento terminar, a resolução continua
falhando fechada. Respostas inválidas, identidade divergente e paginação não confiável
não são repetidas como falhas transitórias válidas.

Os logs são minimizados e usam somente uma operação definida pela aplicação, status,
tentativa e atraso. Bearer token da API, token delegado, segredo, IDs e conteúdo remoto
permanecem fora da telemetria.

## Operational impact

Operações devem monitorar volume de retries, retries adiados e esgotamento por operação
e status. Valores de tentativas e atraso devem considerar o orçamento de latência do
endpoint; aumentar `MICROSOFT_GRAPH_MAX_RETRY_AFTER_SECONDS` não aumenta o atraso
interno permitido.

Alterações são fornecidas por ambiente, em linha com Twelve-Factor. Rollback restaura
os valores anteriores ou define uma única tentativa, sem mudança de esquema.

## Follow-up

- Definir cache com freshness explícita e consistência entre réplicas.
- Implementar invalidação auditável e revogação emergencial.
- Tratar group overage sem seguir URLs fornecidas por claims.
- Exportar métricas agregadas de latência, throttling e stale identity.
- Validar a política contra um tenant Entra não produtivo e Conditional Access.
