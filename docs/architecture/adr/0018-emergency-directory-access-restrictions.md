# ADR 0018 - Restrição emergencial de acesso de identidades Entra

## Status

Aceito.

## Data

2026-08-01.

## Contexto

Invalidar o cache de autorização força uma nova consulta, mas não impede que uma
identidade ainda válida volte a obter capacidades. Revogar sessões no Microsoft Entra
ID também não encerra diretamente a sessão emitida pela própria aplicação e pode levar
alguns minutos para produzir efeito. A plataforma precisa de um mecanismo sob seu
controle que interrompa imediatamente todas as rotas autenticadas durante desligamento,
comprometimento ou resposta a incidente.

O controle não pode depender da disponibilidade do Graph, manter uma lista apenas em
memória, reutilizar um resultado stale ou transformar o cache de autorização em fonte
de bloqueio.

## Decisão

O PostgreSQL manterá o estado corrente de restrição por identidade estável
`(tenant_id, object_id)`. A tabela `directory_access_restrictions` contém somente os
IDs necessários ao binding, estado booleano, instante da mudança, versão e timestamps
operacionais. O histórico permanece nos eventos hash-chained; nome, e-mail, perfil,
token e grupos não são copiados.

Depois da autenticação e antes de qualquer rota protegida, a API consulta esse estado
em uma sessão curta. Uma identidade bloqueada recebe `403`; erro, binding inconsistente
ou estado inválido recebe `503`. A consulta não usa cache positivo em memória, de modo
que todas as réplicas observam o bloqueio persistido na próxima request. Identidades
locais, sem vínculo de diretório, continuam fora desse controle corporativo.

Dois comandos administrativos formam a borda operacional:

- `POST /api/v1/auth/directory-access/block` suspende o acesso;
- `POST /api/v1/auth/directory-access/restore` restaura o acesso.

Ambos exigem `is_admin`, limitam o alvo a `OIDC_ALLOWED_TENANT_IDS`, aceitam motivo
enumerado e referência curta de incidente. A transição usa upsert condicionado pelo
instante para não sobrescrever evento concorrente mais recente.

Na mesma transação, o comando:

1. altera o estado persistente;
2. invalida o snapshot de autorização da identidade;
3. grava evento de auditoria com digest SHA-256 do alvo;
4. efetiva o commit.

Restaurar não recupera capacidades anteriores: a invalidação obriga uma resolução
atual do catálogo, token e Graph quando a próxima operação exigir autorização.

## Limite com Microsoft Entra ID

Este controle encerra acesso à plataforma, não altera a conta no tenant nem chama
`revokeSignInSessions`. IAM ainda deve desabilitar a conta, remover App Roles/grupos,
revogar sessões e aplicar Conditional Access conforme o incidente. A futura integração
com essas ações será outro adapter e exigirá permissões, consentimento, threat model e
validação em tenant não produtivo.

A documentação Microsoft informa que a aplicação controla sua própria sessão e que o
Entra não a revoga diretamente. Também informa que `revokeSignInSessions` invalida
refresh tokens e cookies do Entra, pode ter pequeno atraso e não atende sessões de
usuários externos autenticados no tenant de origem.

## Consequências

- toda request Entra protegida adiciona uma leitura curta no PostgreSQL;
- indisponibilidade do store bloqueia o acesso corporativo em vez de ignorar o controle;
- um administrador bloqueado não consegue restaurar a si mesmo; operação exige outra
  identidade administrativa controlada conforme o procedimento de emergency access;
- a restrição é global para a plataforma, não limitada a uma área de aprovação;
- a trilha de auditoria prova cada transição sem expor os UUIDs do alvo no payload.

## Verificação

- testes de domínio validam UUID, digest, tempo e versão;
- testes de aplicação cobrem bloqueio, restauração, tenant boundary e falha atômica;
- testes do adapter cobrem round-trip, concorrência e binding persistente;
- teste HTTP demonstra que o bloqueio alcança uma rota de negócio em outra request;
- a migração passa por upgrade, downgrade para `0005` e novo upgrade em PostgreSQL real.

## Follow-up

- implementar adapter separado para revogação de sessões no Microsoft Graph;
- validar conta desabilitada, remoção de grupo/App Role, guest e Conditional Access em
  tenant não produtivo;
- adicionar métricas agregadas de bloqueio, restauração e falha de leitura;
- integrar alertas e processo de emergency access sem registrar identidade do alvo.

## Referências oficiais

- [Revogar acesso de usuário em emergência](https://learn.microsoft.com/pt-br/entra/identity/users/users-revoke-access)
- [`revokeSignInSessions` no Microsoft Graph](https://learn.microsoft.com/en-us/graph/api/user-revokesigninsessions?view=graph-rest-1.0)
- [Continuous Access Evaluation](https://learn.microsoft.com/en-us/entra/identity/conditional-access/concept-continuous-access-evaluation)
- [Contas administrativas de acesso de emergência](https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/security-emergency-access)
