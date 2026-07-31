# Orientação para Work e Codex

## Work

Use para visão de produto, personas, jornadas, linguagem da interface, políticas,
templates, critérios de risco, controles, RACI, stage gates e revisão funcional. Toda
regra aceita deve resultar em artefato versionado neste repositório, não apenas em uma
conversa.

Entregáveis típicos:

- contexto, problema e decisão proposta;
- usuários afetados e jornada;
- regra de negócio e exemplos de fronteira;
- áreas consultadas e aprovadoras;
- critérios de aceite e evidências esperadas;
- texto não técnico e documento correspondente.

## Codex

Use para transformar artefatos aceitos em contratos, migrations, endpoints, telas,
testes, segurança, CI, integrações e ADRs. Trabalhe em fatias verticais verificáveis e
preserve comportamento fail-closed.

Antes de concluir uma mudança, verifique:

- autorização no backend e segregação de funções;
- migration e versionamento para alterações persistidas;
- audit event sem conteúdo sensível;
- testes de caminho positivo, negação e conflito;
- documentação e contrato atualizados;
- rollback ou tratamento para integração indisponível.

## Participação de outras áreas

Segurança, Infra, DevOps, Arquitetura, Privacidade, Jurídico, Compliance, Dados e
Negócio não são revisores “fixos” em toda proposta. O policy engine determina
aplicabilidade e registra a razão. Alterar um gatilho requer revisão do owner da
política, exemplos, testes de regressão e nova versão de policy.

## Formato de handoff

```text
Objetivo e usuário
Estado atual e decisão aceita
Regras e casos de fronteira
Áreas obrigatórias e evidências
Critérios de aceite
Arquivos/contratos impactados
Riscos e itens explicitamente fora do escopo
```
