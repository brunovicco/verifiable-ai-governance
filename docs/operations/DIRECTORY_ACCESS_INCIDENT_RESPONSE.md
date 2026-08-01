# Resposta a incidente de acesso de diretório

## Objetivo

Interromper imediatamente o acesso de uma identidade Entra à plataforma, coordenar as
ações do provedor e restaurar somente depois da remediação. O bloqueio local complementa
as ações de IAM; não substitui desabilitar a conta, remover associação ou revogar
sessões no Microsoft Entra ID.

## Pré-requisitos

- duas identidades administrativas de emergência controladas e monitoradas;
- `tenant_id` e `object_id` confirmados em uma fonte IAM confiável;
- tenant presente em `OIDC_ALLOWED_TENANT_IDS`;
- incidente ou mudança com referência rastreável;
- acesso operacional ao Entra para as ações externas aplicáveis.

Nunca obtenha o alvo apenas de nome, e-mail ou texto enviado pelo solicitante. Não copie
tokens, segredos, respostas Graph ou inventários de grupos para tickets e logs.

## 1. Bloquear na plataforma

Use uma identidade administrativa diferente do alvo:

```bash
curl --fail-with-body \
  --request POST "${GOVERNANCE_API_URL}/api/v1/auth/directory-access/block" \
  --header "Authorization: Bearer ${GOVERNANCE_ADMIN_TOKEN}" \
  --header "Content-Type: application/json" \
  --data '{
    "tenant_id": "11111111-1111-4111-8111-111111111111",
    "object_id": "22222222-2222-4222-8222-222222222222",
    "reason": "account_compromised",
    "reference": "INC-2026-184"
  }'
```

Motivos de bloqueio aceitos:

- `account_compromised`;
- `personnel_offboarding`;
- `incident_response`;
- `policy_violation`;
- `manual_emergency`.

Resposta esperada: `blocked=true`, ID opaco, horário e versão. A operação altera o
estado, invalida a autorização derivada e grava auditoria na mesma transação.

## 2. Confirmar contenção

1. execute uma request protegida com uma sessão de teste do alvo;
2. confirme `403` com `Directory identity access is suspended`;
3. confirme o evento `directory_access.blocked` e sua
   `authorization_cache_version` na trilha;
4. verifique que os payloads contêm digest do alvo, motivo e referência, não os UUIDs.

Falha de banco ou binding inconsistente deve produzir `503`. Não contorne esse resultado
nem mude o serviço para fail-open durante o incidente.

## 3. Coordenar ações no Microsoft Entra ID

IAM determina e executa as ações apropriadas, que podem incluir:

- desabilitar a conta para impedir novos tokens;
- revogar sessões/refresh tokens;
- remover App Roles e associações a grupos;
- desabilitar ou marcar dispositivos comprometidos;
- revogar consentimentos ou credenciais afetadas;
- aplicar ou revisar Conditional Access e Continuous Access Evaluation.

`revokeSignInSessions` exige permissão específica, pode levar alguns minutos e não
revoga sessões de usuários externos no tenant de recurso. A sessão da plataforma é
controlada pelo bloqueio local deste runbook. Registre a evidência da ação Entra sem
armazenar tokens ou segredos.

## 4. Restaurar com autorização atual

Restaure somente quando IAM, Segurança e o owner do incidente confirmarem remediação.

```bash
curl --fail-with-body \
  --request POST "${GOVERNANCE_API_URL}/api/v1/auth/directory-access/restore" \
  --header "Authorization: Bearer ${GOVERNANCE_ADMIN_TOKEN}" \
  --header "Content-Type: application/json" \
  --data '{
    "tenant_id": "11111111-1111-4111-8111-111111111111",
    "object_id": "22222222-2222-4222-8222-222222222222",
    "reason": "remediation_completed",
    "reference": "INC-2026-184"
  }'
```

Motivos de restauração aceitos: `remediation_completed`, `false_positive` e
`access_reinstated`. A restauração mantém o cache de autorização invalidado. A próxima
operação sensível deve obter uma decisão atual; associação removida não reaparece por
herança do snapshot anterior.

## 5. Encerrar e preservar evidências

- confirme `directory_access.restored` e a nova versão da restrição;
- valide login, área organizacional e capacidades efetivas com uma conta de teste;
- vincule as evidências da plataforma e do Entra à referência do incidente;
- revise causa, SLA de contenção e eventual atraso entre bloqueio local e ações Entra;
- preserve a cadeia de auditoria conforme a política de retenção.

## Recuperação operacional

Se o administrador executor for o próprio alvo, ele ficará bloqueado depois do commit.
Use outra conta de emergency access para restaurar. Se todas as contas administrativas
estiverem indisponíveis, siga o procedimento corporativo de recuperação de acesso; não
edite a tabela manualmente, pois isso quebraria a evidência e a invalidação coordenada.

## Referências oficiais

- [Revogar acesso de usuário em emergência](https://learn.microsoft.com/pt-br/entra/identity/users/users-revoke-access)
- [`revokeSignInSessions` no Microsoft Graph](https://learn.microsoft.com/en-us/graph/api/user-revokesigninsessions?view=graph-rest-1.0)
- [Continuous Access Evaluation](https://learn.microsoft.com/en-us/entra/identity/conditional-access/concept-continuous-access-evaluation)
