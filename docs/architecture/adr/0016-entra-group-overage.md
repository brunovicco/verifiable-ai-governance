# ADR 0016 - Claims de grupos Entra e group overage

## Status

Aceito.

## Date

2026-08-01.

## Context

O catálogo de autorização já aceita object IDs de grupos obtidos pelo Microsoft Graph,
mas a fronteira de identidade ainda não distinguia um claim `groups` completo de um
token em situação de overage. O Microsoft Entra ID limita JWTs a 200 object IDs; acima
desse limite, omite a lista e sinaliza que a aplicação deve consultar o Graph.

Tokens com overage podem incluir `_claim_sources` com um endpoint. A documentação atual
alerta que esse endereço ainda pode apontar para Azure AD Graph legado. Permitir que um
claim determine o destino da chamada também criaria uma superfície de SSRF e contorno
dos endpoints fixos já definidos pelo adapter.

## Decision

O modo Entra terá um claim de grupos explícito, configurado por
`OIDC_ENTRA_GROUPS_CLAIM` e com default `groups`. O domínio representará três estados:
ausente, completo e overage.

Um claim completo deve ser um array de até 200 UUIDs não nulos. Os valores são
canonicalizados e duplicidades são removidas. Tipo, quantidade ou object ID inválido
rejeita o token.

`hasgroups=true` ou `_claim_names.groups` não vazio sinaliza overage. Nesse estado,
qualquer lista `groups` presente é ignorada. `_claim_sources` não é lido nem seguido; a
aplicação usa exclusivamente os endpoints Microsoft Graph construídos pelo adapter.

Quando existe um snapshot Graph confiável, seus grupos transitivos prevalecem sobre o
claim. Sem snapshot, um claim completo pode alimentar o catálogo diretamente. Overage
sem Graph usa lista vazia: mappings de grupo não concedem capacidade, enquanto App
Roles exatas e independentes continuam sendo avaliadas.

A provenance registrará apenas `token`, `microsoft_graph`, `none` ou
`overage_unresolved` como fonte da resolução. Object IDs, quantidade de grupos e URLs
de claims não serão expostos nem persistidos no evento de decisão.

## Alternatives considered

- Consultar sempre o Graph e ignorar o claim completo: rejeitado como única estratégia,
  pois aumenta dependência remota quando o token já contém object IDs completos.
- Seguir o endpoint de `_claim_sources`: rejeitado por SSRF, dependência de Azure AD
  Graph legado e perda do controle de egress.
- Aceitar nomes de grupos ou valores não UUID: rejeitado por mutabilidade e colisão.
- Bloquear também App Roles quando overage não puder ser resolvido: rejeitado porque
  App Roles assinadas e mapeadas são uma fonte independente de autorização.
- Tratar ausência de `groups` como grupo vazio completo: rejeitado porque ausência não
  prova que a configuração do tenant emitiu todas as associações.

## Consequences

Deployments sem enriquecimento Graph podem resolver autorização baseada em grupos a
partir de um access token completo. Quando o Graph está habilitado e já é consultado
para perfil e associações transitivas, seu snapshot continua sendo a fonte preferencial.

Clientes de `/api/v1/auth/me` passam a receber uma fonte de resolução minimizada dentro
da provenance. Não há migração de banco nem persistência dos object IDs do token.

## Security and privacy impact

O limite de itens, validação estrita de UUID e descarte de listas contraditórias evitam
uso de claims ambíguos. Overage não promove acesso: na ausência do Graph, grupos são
avaliados como indisponíveis e não geram áreas.

Nenhum endpoint fornecido pelo token influencia rede. A auditoria contém somente a
fonte abstrata e os mapping IDs já aprovados, sem inventário de associações ou dados do
claim distribuído.

## Operational impact

IAM deve configurar `groupMembershipClaims` para emitir object IDs destinados à API e
validar cenários abaixo e acima de 200 grupos. Alertas devem distinguir
`overage_unresolved` de ausência legítima de mapping.

Se a organização depende de grupos e usuários podem exceder o limite, Graph OBO deve
estar habilitado. O cache compartilhado posterior está definido pelo ADR 0017;
revogação definitiva de sessão e acesso permanece uma responsabilidade separada.

## Follow-up

- Cache curto com freshness explícita e invalidação entre réplicas: concluído no ADR
  0017.
- Integrar a restrição emergencial do ADR 0018 à revogação de sessão no provedor.
- Validar group overage em tenant Entra não produtivo.
- Exportar métricas agregadas por fonte de resolução, sem IDs de grupos.
