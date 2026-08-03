# ADR 0013 - Enriquecimento de identidade com Microsoft Graph via OBO

## Status

Aceito.

## Date

2026-08-01.

## Context

A API já valida access tokens destinados à própria audience e forma a identidade
corporativa estável por `(tid, oid)`. O portal também precisa exibir nome e área
organizacional sem solicitar esses dados manualmente. O futuro catálogo de autorização
precisará receber os object IDs dos grupos transitivos, sem confiar em nomes de grupos
ou no texto livre de `department`.

O access token enviado pelo portal foi emitido para a API e não pode ser reutilizado
diretamente no Microsoft Graph. A integração acrescenta uma credencial confidencial,
tratamento de dados pessoais e uma nova dependência de rede no caminho de identidade.

## Decision

A aplicação define a porta assíncrona `CorporateDirectoryPort` e o caso de uso
`ResolveCorporateDirectory`. O adapter Microsoft implementa OAuth 2.0 On-Behalf-Of
(OBO): troca o token validado da API por um token delegado destinado ao Graph usando o
scope `https://graph.microsoft.com/.default`.

O adapter:

- usa endpoint de token tenant-specific derivado somente do tenant configurado e já
  validado pelo boundary Entra;
- chama os endpoints fixos do Azure público `GET /v1.0/me` e
  `GET /v1.0/me/transitiveMemberOf/microsoft.graph.group`;
- solicita de `/me` apenas `id`, `displayName`, `mail`, `userPrincipalName`,
  `department` e `userType`;
- coleta somente o `id` dos grupos e deduplica os valores em memória;
- usa paginação limitada e segue `@odata.nextLink` apenas quando o esquema, host e
  caminho permanecem na coleção Graph permitida;
- aplica timeout explícito, não segue redirects e converte respostas inválidas,
  falhas de rede e throttling em erros tipados sem conteúdo remoto;
- limita o `Retry-After` numérico antes de encaminhá-lo ao cliente;
- verifica o tenant antes da troca e o object ID retornado antes de consultar grupos;
- lê respostas em streaming com limite de bytes configurável.

A integração é opt-in por ambiente. Quando desabilitada, `/api/v1/auth/me` mantém o
comportamento anterior e retorna `directory_profile=null`. Quando habilitada, o
endpoint inclui somente perfil mínimo, `department` e tipo do usuário. A quantidade e
a lista de object IDs não são expostas ao portal e, nesta etapa, não alteram
`ApprovalArea`, administração ou qualquer decisão de autorização.

## Alternatives considered

- Chamar o Graph diretamente do portal: rejeitado porque ampliaria permissões e
  exposição de dados no navegador e duplicaria regras de confiança no cliente.
- Encaminhar ao Graph o token destinado à API: rejeitado por violar a separação de
  audiences e o fluxo delegado suportado.
- Inferir área por `department` ou nome de grupo: rejeitado porque são valores mutáveis,
  textuais e não governados para autorização.
- Usar somente claims de grupos do token: adiado para a etapa de group overage e cache;
  não substitui a resolução transitiva consistente nem o catálogo versionado.
- Adicionar o SDK Microsoft Graph ou MSAL ao núcleo: rejeitado nesta etapa. O contrato
  HTTP OBO é pequeno e permanece isolado no adapter, preservando o núcleo
  vendor-neutral e assíncrono.
- Persistir o perfil e os grupos no primeiro acesso: adiado até existir política de
  cache, retenção, revogação e auditoria de stale identity.

## Consequences

O endpoint identifica automaticamente nome, e-mail/UPN e departamento quando Graph
está habilitado. O próximo catálogo pode consumir object IDs transitivos já
normalizados, mas precisa continuar sendo a única fonte de mapeamento para áreas de
aprovação.

Cada leitura de `/auth/me` enriquecida faz uma troca OBO e chamadas ao Graph. Cache,
retry com jitter e invalidação não pertencem a esta entrega; indisponibilidade resulta
em falha segura e não promove privilégios.

`httpx` passa a ser dependência de runtime da API para manter o adapter assíncrono e
testável com transporte injetável.

## Security and privacy impact

O segredo do confidential client vem do ambiente e é excluído da representação de
configuração. Em produção, ele deve ser injetado por secret manager. Bearer tokens,
segredo, respostas completas do Graph e inventário de grupos não são persistidos,
retornados ao portal nem incluídos em mensagens de erro.

A validação rígida de destinos reduz risco de SSRF por paginação controlada por resposta
remota. UUIDs ausentes, nulos ou malformados, identidade divergente, corpo remoto além
do limite e paginação excessiva falham de forma fechada. `department` é dado pessoal
organizacional e permanece informativo, sem conceder autorização.

O tratamento deve constar no inventário de privacidade, RIPD quando aplicável e análise
de processamento internacional do deployment.

## Operational impact

IAM deve conceder à app registration da API a permissão delegada mínima do Graph,
configurar a credencial confidencial e aplicar o consentimento exigido pela organização.
Os deployments precisam definir `MICROSOFT_GRAPH_ENABLED`, client ID, segredo, timeout
e limites. O segredo deve ser rotacionado sem commit e a rotação precisa ser testada em
ambiente não produtivo.

Esta implementação suporta somente endpoints do Azure público e autenticação por client
secret. Certificados, managed identity e clouds soberanas exigem adapter ou decisão
adicional.

## Follow-up

- Validar OBO, consentimento e Conditional Access contra tenant Entra real.
- Implementar catálogo versionado App Role/object ID para `ApprovalArea`.
- Tratar group overage usando somente endpoints Graph construídos pela aplicação.
- Adicionar cache curto, revogação, stale identity fail-closed e auditoria minimizada.
- Implementar retry limitado com jitter e métricas de latência, falhas e throttling.
- Substituir client secret por certificado ou credencial de workload quando o ambiente
  de implantação suportar.
