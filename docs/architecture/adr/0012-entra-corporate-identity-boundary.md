# ADR 0012 — Identidade corporativa Entra por tenant e object ID

## Status

Aceito.

## Date

2026-08-01.

## Context

O adapter OIDC existente usava somente `sub` como identidade do principal. Esse claim
continua adequado ao contrato genérico porque é imutável e pairwise para uma aplicação,
mas não oferece a chave corporativa estável necessária para correlacionar a mesma conta
entre API, Microsoft Graph, auditoria e futuros catálogos de autorização.

No Microsoft Entra ID, `oid` identifica o objeto dentro de um diretório e precisa ser
combinado com `tid`, pois uma pessoa pode possuir objetos distintos em tenants
diferentes. A aplicação também precisa evitar que tokens de tenants não autorizados ou
contas guest obtenham capacidades de aprovação por ambiguidade de claims.

## Decision

O mapeamento OIDC passa a oferecer dois modos configuráveis:

- `subject`, compatível com provedores OIDC gerais e com a validação local Keycloak;
- `entra`, que exige `tid` e `oid` como UUIDs não nulos e forma `user_id` como
  `{tenant_id}:{object_id}`.

No modo Entra:

- `OIDC_ALLOWED_TENANT_IDS` é obrigatório;
- o issuer deve ser `https://login.microsoftonline.com/{tenant_id}/v2.0`;
- o UUID presente no issuer e no claim `tid` deve estar na allowlist;
- o claim opcional `acct` classifica `0` como member e `1` como guest;
- claim `acct` ausente ou inválido produz a classificação `unknown`;
- member pode receber capacidades provenientes dos claims configurados;
- guest perde áreas de aprovação e administração por padrão;
- `unknown` sempre perde essas capacidades;
- guest só pode receber áreas de aprovação quando
  `OIDC_GUEST_APPROVALS_ENABLED=true` for definido explicitamente.
- administração permanece exclusiva de member classificado, independentemente da
  política de aprovação para guest.

A validação criptográfica de assinatura, issuer, audience e tempo continua pertencendo
ao adapter PyJWT. O domínio recebe somente claims já verificados e aplica identidade,
allowlist e least privilege sem depender de FastAPI, Pydantic ou bibliotecas Microsoft.

## Alternatives considered

- Continuar usando somente `sub`: rejeitado para o modo corporativo porque é pairwise
  por aplicação e não é a chave usada pelo Microsoft Graph.
- Usar e-mail, UPN ou nome exibido: rejeitado porque são mutáveis e inadequados para
  autorização ou ownership.
- Usar somente `oid`: rejeitado porque object IDs são únicos apenas dentro do tenant.
- Inferir guest pelo e-mail, UPN ou `idp`: rejeitado por não representar de forma
  determinística o tipo do objeto no tenant de recurso.
- Rejeitar qualquer token sem `acct`: rejeitado nesta etapa porque `acct` é opcional;
  a conta pode autenticar para jornadas sem aprovação, mas permanece sem capacidades.
- Conceder capacidades quando `acct` estiver ausente: rejeitado por violar o princípio
  fail-closed.

## Consequences

Auditoria e ownership passam a receber uma chave estável por tenant no modo Entra. O
endpoint `/api/v1/auth/me` expõe também tenant ID, object ID e classificação da conta
para o próprio usuário.

Deployments OIDC genéricos continuam usando `subject` sem mudança de identidade.
Deployments Entra precisam configurar a allowlist e emitir o claim opcional `acct` para
que membros possam receber áreas de aprovação.

## Security and privacy impact

Tokens de outro tenant são rejeitados mesmo que tenham assinatura válida para uma
configuração indevida. UUIDs inválidos, ausentes ou nulos não produzem identidade. Guest
e classificações ambíguas não recebem privilégios por padrão, incluindo administração.

Tenant ID e object ID são identificadores pessoais pseudônimos e podem correlacionar
atividade corporativa. Eles são expostos apenas ao próprio principal e usados na trilha
de auditoria necessária; bearer tokens e inventários completos de grupos continuam
proibidos em logs.

## Operational impact

IAM deve configurar `acct` como optional claim no access token da API, manter issuer e
tenant allowlist coerentes e testar member, guest, claim ausente e tenant incorreto.
Mudanças na allowlist ou na política de guest exigem revisão, redeploy e evidência de
validação. Esta implementação cobre o Azure público; clouds soberanas exigirão decisão
e configuração específicas.

## Follow-up

- Validar tokens reais de member e guest em tenant Entra não produtivo.
- Implementar Microsoft Graph via OBO com seleção mínima de atributos.
- Implementar catálogo versionado de App Roles e object IDs.
- Tratar groups overage, paginação, throttling, cache e stale identity.
- Registrar provenance do catálogo aplicado sem persistir inventários integrais.
