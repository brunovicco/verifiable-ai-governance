# ADR 0011 - Autenticação SPA com Microsoft Entra ID e MSAL

## Status

Aceito.

## Date

2026-08-01.

## Context

O portal Next.js é composto por páginas cliente que acessam diretamente a API FastAPI.
Até esta decisão, todas as chamadas usavam headers explícitos de desenvolvimento para
simular identidade e áreas. Esses headers são adequados somente ao Compose local e não
podem atravessar o limite de confiança de um ambiente compartilhado.

A API já funciona como resource server OIDC e valida assinatura, issuer, audience,
expiração e subject. Faltava ao portal obter um access token destinado à API sem
coletar senha, persistir segredo de cliente ou permitir que o usuário digite sua
identidade.

## Decision

O portal corporativo será registrado no Entra como Single-Page Application pública e
usará `@azure/msal-browser` e `@azure/msal-react`. O MSAL executará Authorization Code
com PKCE e solicitará o scope delegado exposto pela app registration da API.

A implementação adota:

- authority construída exclusivamente como tenant específico em
  `https://login.microsoftonline.com/{tenant_id}`;
- client ID, tenant ID, auth mode e scope delegado como configuração pública de build;
- redirect e post-logout redirect limitados à origem atual do portal;
- cache do MSAL em `sessionStorage`, sem `localStorage` ou cookie adicional;
- logging de PII desabilitado e platform broker desabilitado nesta implementação web;
- aquisição silenciosa antes de qualquer fallback interativo;
- redirect interativo quando o Entra ou Conditional Access exigir reautenticação;
- envio do access token somente em `Authorization: Bearer` para a API;
- `credentials: omit` nas chamadas do portal;
- remoção defensiva de `X-User-Id` e `X-User-Areas` no modo Entra;
- headers simulados preservados somente quando `NEXT_PUBLIC_AUTH_MODE=local`.

O frontend nunca recebe client secret. A API continua responsável pela validação
criptográfica e autorização; informações de tela ou claims de ID token não substituem
o access token destinado à audience da API.

## Alternatives considered

- Manter headers digitáveis no ambiente corporativo: rejeitado por permitir
  impersonação no cliente.
- Fluxo implícito: rejeitado; Authorization Code com PKCE é o fluxo recomendado para
  SPAs modernas.
- Resource Owner Password Credentials: rejeitado por coletar senha e não atender
  adequadamente MFA ou Conditional Access.
- Guardar tokens em `localStorage`: rejeitado por aumentar a persistência entre
  sessões do navegador.
- Introduzir agora um BFF confidential client com sessão HttpOnly: adiado. Ele reduz a
  exposição de tokens ao JavaScript, mas altera o modelo de deploy, exige sessão
  server-side e credencial protegida. Pode ser adotado futuramente se o threat model
  corporativo exigir esse boundary.

## Consequences

Usuários do modo Entra entram e saem pelo provedor corporativo, e decisões deixam de
aceitar identidade manual no portal. O modo local continua rápido e reproduzível.

As variáveis `NEXT_PUBLIC_*` são incorporadas no build e não são segredos; mudar tenant,
cliente ou scope exige novo build do portal. React foi atualizado de 19.2.0 para 19.2.8
para atender o peer suportado pelo MSAL React sem ignorar a resolução do npm.

Como esta é uma SPA, access e refresh tokens são processados pelo JavaScript do MSAL.
O projeto passa a depender ainda mais de prevenção de XSS, atualização de dependências
e revisão de supply chain.

## Security and privacy impact

`sessionStorage` reduz persistência, mas não protege tokens contra JavaScript malicioso
executando na mesma origem. Conteúdo não confiável não deve virar HTML executável;
dependências e CSP precisam de assurance contínuo. Tokens, authorization codes e erros
com claims não podem ser registrados em telemetria.

A authority tenant-specific reduz autenticação acidental em outro diretório. A API
deve continuar configurada com issuer e audience do mesmo tenant. Guest, App Roles,
grupos e `department` ainda pertencem às fases posteriores e não são inferidos pela UI.

O nome e username exibidos vêm do cache de conta do MSAL e são dados pessoais usados
somente para contexto de sessão. O portal não os persiste nesta fase.

## Operational impact

IAM deve manter app registrations separadas para portal e API, redirect URIs exatas,
scope delegado, consentimento e ownership. Mudanças exigem rebuild, smoke test de login,
logout, renovação silenciosa e Conditional Access.

Falha de configuração Entra interrompe o build. Falha de aquisição silenciosa não
degrada para headers locais; inicia interação ou bloqueia a chamada.

## Follow-up

- Validar o fluxo contra um tenant Entra real e políticas de Conditional Access.
- Identidade corporativa `(tid, oid)`, tenant allowlist e política de guest: concluída
  no ADR 0012.
- Implementar OBO e enriquecimento mínimo via Microsoft Graph.
- Criar catálogo versionado de App Roles/object IDs para `ApprovalArea`.
- Definir CSP compatível com Next.js/MSAL e executar testes de XSS.
- Avaliar BFF com sessão HttpOnly se o threat model de produção exigir.
