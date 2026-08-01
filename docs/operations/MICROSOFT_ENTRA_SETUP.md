# Configuração do Microsoft Entra ID para o portal

## Escopo

Este runbook configura o login interativo do portal e a emissão de access token para a
API. Microsoft Graph, OBO, grupos transitivos e `department` são configurados
separadamente em `MICROSOFT_GRAPH_OBO_SETUP.md`.

Use duas app registrations. O portal é um public client SPA sem segredo. A API é um
resource server separado e continua validando cada token.

## 1. App registration da API

1. Criar uma registration single-tenant para a API de governança.
2. Em **Expose an API**, definir um Application ID URI aprovado pela organização.
3. Expor um scope delegado, por exemplo `access_as_user`.
4. Registrar os owners de IAM e da plataforma.
5. Confirmar que os access tokens são v2 e anotar client ID, tenant ID, issuer,
   audience e endpoint JWKS a partir do metadata oficial do tenant.
6. Em **Token configuration**, adicionar o claim opcional `acct` ao access token da
   API. O valor `0` classifica membro e `1` classifica guest.

Configuração de referência da API:

```dotenv
APP_ENV=production
DEV_AUTH_ENABLED=false
OIDC_ENABLED=true
OIDC_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0
OIDC_JWKS_URL=https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys
OIDC_AUDIENCE=<api-client-id>
OIDC_ALGORITHMS=RS256
OIDC_IDENTITY_MODE=entra
OIDC_ALLOWED_TENANT_IDS=<tenant-id>
OIDC_GUEST_APPROVALS_ENABLED=false
```

Não derive issuer, audience ou JWKS de claims recebidos. Confirme os valores no
documento `openid-configuration` do tenant antes do deploy. O modo Entra aceita somente
issuer v2 tenant-specific do Azure público e exige que o mesmo UUID esteja na allowlist.

## 2. App registration do portal

1. Criar uma registration single-tenant separada.
2. Em **Authentication**, adicionar plataforma **Single-page application**.
3. Registrar redirect URIs exatas, por exemplo `http://localhost:3000` para
   desenvolvimento e a origem HTTPS corporativa para produção.
4. Não criar client secret para o portal.
5. Em **API permissions**, adicionar o scope delegado da API.
6. Aplicar consentimento administrativo quando a política organizacional exigir.
7. Desabilitar fluxos implícitos de access token e ID token.

## 3. Build do portal

As configurações são públicas e incorporadas ao bundle. Elas não devem conter segredo:

```dotenv
NEXT_PUBLIC_AUTH_MODE=entra
NEXT_PUBLIC_ENTRA_CLIENT_ID=<portal-client-id>
NEXT_PUBLIC_ENTRA_TENANT_ID=<tenant-id>
NEXT_PUBLIC_ENTRA_API_SCOPE=api://<api-client-id>/access_as_user
NEXT_PUBLIC_API_URL=https://api-governance.example.com
```

IDs precisam ser UUIDs explícitos e o scope precisa começar com `api://` ou `https://`.
Configuração ausente ou inválida interrompe o build. Alterações exigem rebuild; trocar
somente variáveis no container já construído não altera os valores `NEXT_PUBLIC_*`.

O CORS da API deve aceitar apenas a origem exata do portal. Como o portal usa bearer
token e `credentials: omit`, cookies não são necessários nessa integração.

## 4. App Roles e catálogo de autorização

Em modo Entra, App Roles não viram áreas de aprovação diretamente. Configure o claim
dedicado e publique um mapping tenant-specific no catálogo governado:

```dotenv
OIDC_ENTRA_APP_ROLES_CLAIM=roles
DIRECTORY_AUTHORIZATION_CATALOG_PATH=/run/governance/entra-authorization.yaml
```

O catálogo liga o valor exato da App Role ou object ID do grupo a `ApprovalArea` e
registra ID, versão e owner do mapping. Consulte
`DIRECTORY_AUTHORIZATION_CATALOG.md`. `department`, e-mail, nome exibido ou texto de
grupo nunca concedem autorização. Guest perde áreas de aprovação e administração por
padrão. Se `acct` estiver ausente ou for inválido, a conta será classificada como
`unknown` e também não receberá capacidades. Habilitar
`OIDC_GUEST_APPROVALS_ENABLED=true` exige decisão formal de risco; essa opção não
concede nada a contas `unknown` nem concede administração a guest.

## 5. Validação

Executar em ambiente não produtivo:

1. acessar o portal e confirmar redirect tenant-specific;
2. concluir MFA/Conditional Access quando exigido;
3. verificar que `/api/v1/auth/me` responde com `tenant_id`, `object_id`,
   `account_type` e a chave composta em `user_id`;
4. confirmar ausência de `X-User-Id` e `X-User-Areas` nas requests do navegador;
5. confirmar `Authorization: Bearer` destinado à audience da API;
6. testar token expirado, logout, nova autenticação e fechamento da aba;
7. testar usuário sem App Role e confirmar que não consegue aprovar;
8. testar guest e token sem `acct`, confirmando ausência de capacidades de aprovação;
9. testar `tid` fora da allowlist, issuer ou audience incorretos e confirmar rejeição;
10. revisar logs e confirmar que token, code, claims integrais e PII não aparecem.

O cache padrão é `sessionStorage`. Fechar a aba encerra esse cache, embora a sessão do
Entra no navegador possa permitir novo SSO conforme a política corporativa.

## 6. Rotação, revogação e incidente

- Rotacionar a credencial da API confidential client conforme
  `MICROSOFT_GRAPH_OBO_SETUP.md`; o portal SPA não possui segredo.
- Remover redirect URIs antigas imediatamente após migração.
- Revogar sessões e consentimentos pelo Entra quando houver comprometimento.
- Publicar novo build se client ID, tenant ou scope mudar.
- Tratar suspeita de XSS como potencial exposição dos tokens da sessão atual.
- Registrar falhas e correlation IDs minimizados, nunca os próprios tokens.

## Referências oficiais

- [Authorization Code com PKCE](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [MSAL React](https://learn.microsoft.com/en-us/entra/msal/javascript/react/getting-started)
- [Token para Web API em SPA](https://learn.microsoft.com/en-us/entra/identity-platform/scenario-spa-acquire-token)
- [Aquisição e renovação de tokens](https://learn.microsoft.com/en-us/entra/msal/javascript/browser/token-lifetimes)
- [Configuração de cache do MSAL](https://learn.microsoft.com/en-us/entra/msal/javascript/browser/configuration)
- [Claims de access token](https://learn.microsoft.com/en-us/entra/identity-platform/access-token-claims-reference)
- [Claims opcionais, incluindo acct](https://learn.microsoft.com/en-us/entra/identity-platform/optional-claims-reference)
