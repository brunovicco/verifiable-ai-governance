# Configuração do Microsoft Graph via On-Behalf-Of

## Escopo

Este runbook habilita o enriquecimento opcional de `/api/v1/auth/me` com perfil e
`department`, além de resolver internamente os grupos transitivos. Ele pressupõe
que o login Entra, a validação tenant-specific e a identidade `(tid, oid)` já estejam
configurados conforme `MICROSOFT_ENTRA_SETUP.md`.

Esta entrega não mapeia grupos para áreas de aprovação. `department`, e-mail, nome,
`userType` e associações resolvidas são informativos. Nenhum deles concede capacidade.

## 1. Permissão delegada do Graph

Na app registration confidencial da API:

1. abrir **API permissions**;
2. adicionar a permissão delegada Microsoft Graph `User.Read`;
3. aplicar consentimento administrativo quando a política do tenant exigir;
4. confirmar que não foi adicionada `Directory.Read.All` ou permissão de aplicação;
5. registrar owner de IAM, justificativa, ambiente e evidência do consentimento.

O portal continua solicitando somente o scope delegado da API. A API usa OBO e
`https://graph.microsoft.com/.default` para receber as permissões Graph já consentidas.

## 2. Credencial confidencial

A implementação atual aceita um client secret da app registration da API. Crie o
segredo com o menor prazo compatível com a política corporativa e entregue o valor à
aplicação por secret manager. Não coloque o valor em `.env`, Compose versionado,
manifesto, imagem, log, issue ou pull request.

Certificado ou credencial de workload é preferível para ambientes produtivos, mas exige
uma evolução do adapter atual antes de habilitar essa opção.

## 3. Configuração por ambiente

O client ID é o Application (client) ID da app registration confidencial da API. O
tenant é obtido do `OIDC_ISSUER` já validado e não possui uma variável Graph separada.

```dotenv
OIDC_ENABLED=true
OIDC_IDENTITY_MODE=entra
OIDC_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0
OIDC_ALLOWED_TENANT_IDS=<tenant-id>

MICROSOFT_GRAPH_ENABLED=true
MICROSOFT_GRAPH_CLIENT_ID=<api-client-id>
MICROSOFT_GRAPH_CLIENT_SECRET=<valor-injetado-pelo-secret-manager>
MICROSOFT_GRAPH_TIMEOUT_SECONDS=5
MICROSOFT_GRAPH_MAX_PAGES=20
MICROSOFT_GRAPH_MAX_RETRY_AFTER_SECONDS=300
MICROSOFT_GRAPH_MAX_RESPONSE_BYTES=1048576
```

A API falha no startup se Graph estiver habilitado fora do modo Entra, se client ID não
for UUID ou se o segredo estiver ausente. Os endpoints de login, token e Graph são fixos
para o Azure público; URLs recebidas em token ou resposta não controlam o destino.

## 4. Contrato de dados

O adapter executa:

- `POST /{tenant}/oauth2/v2.0/token` com o token da API como `assertion` OBO;
- `GET https://graph.microsoft.com/v1.0/me` com `$select` mínimo;
- `GET https://graph.microsoft.com/v1.0/me/transitiveMemberOf/microsoft.graph.group`
  com `$select=id`, paginação e limite local.

O payload devolvido ao próprio usuário possui:

```json
{
  "directory_profile": {
    "display_name": "Pessoa Usuária",
    "email_or_upn": "pessoa@example.com",
    "department": "Segurança da Informação",
    "user_type": "Member",
    "source": "microsoft_graph"
  }
}
```

Quantidade e object IDs de grupos permanecem somente em memória e alimentam o catálogo
governado descrito em `DIRECTORY_AUTHORIZATION_CATALOG.md`.
Bearer tokens, segredo, resposta completa e lista integral de grupos não devem aparecer
em logs, traces ou respostas HTTP.

## 5. Validação em tenant não produtivo

1. habilitar as variáveis no ambiente de teste;
2. autenticar um member que possua `department` e grupo aninhado conhecido;
3. chamar `/api/v1/auth/me` e validar nome, e-mail/UPN, `department` e `userType`;
4. confirmar por teste controlado do adapter que o grupo aninhado é resolvido, sem
   expor quantidade ou object IDs ao portal;
5. remover temporariamente o consentimento e confirmar resposta `503`, sem detalhes do
   token ou do Graph;
6. simular segredo inválido e confirmar comportamento seguro;
7. testar usuário guest e garantir que o enriquecimento não concede aprovação;
8. revisar logs, traces e error tracker buscando token, segredo, corpo Graph, UPN e IDs
   integrais de grupos;
9. registrar evidência do teste, tenant, app registration, permissão e data, sem copiar
   credenciais ou tokens.

A validação real de Conditional Access pode exigir interação e não é substituída pelos
testes determinísticos do adapter.

## 6. Rotação, revogação e falhas

- criar uma segunda credencial antes de revogar a atual;
- atualizar o secret manager, reiniciar o deployment e validar OBO;
- revogar a credencial anterior e registrar a evidência da rotação;
- em comprometimento, revogar segredo, sessões e consentimentos conforme o playbook de
  IAM, então revisar logs sem copiar material secreto;
- respostas `429` expõem somente um `Retry-After` numérico limitado; retry automático,
  jitter, cache e stale identity pertencem à próxima etapa;
- indisponibilidade ou resposta inconsistente falha de forma fechada e nunca adiciona
  capacidades de aprovação.

## Referências oficiais

- [OAuth 2.0 On-Behalf-Of](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow)
- [Scope `.default`](https://learn.microsoft.com/en-us/entra/identity-platform/scopes-oidc#the-default-scope)
- [Obter o usuário autenticado](https://learn.microsoft.com/en-us/graph/api/user-get?view=graph-rest-1.0)
- [Associações transitivas do usuário](https://learn.microsoft.com/en-us/graph/api/user-list-transitivememberof?view=graph-rest-1.0)
- [Throttling no Microsoft Graph](https://learn.microsoft.com/en-us/graph/throttling)
