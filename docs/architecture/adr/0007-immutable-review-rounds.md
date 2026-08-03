# ADR 0007 - Rodadas imutáveis de revisão e resubmissão

- Status: aceito
- Data: 2026-08-01

## Contexto

Uma iniciativa pode precisar de correções solicitadas por Negócio, Arquitetura,
Segurança, Infraestrutura, DevOps, Privacidade, Jurídico, Compliance ou Dados. Alterar
a proposta, assessments e gates da submissão original apagaria a base da decisão e
impediria explicar qual conteúdo cada área revisou.

Também é necessário impedir que dois revisores decidam sobre uma projeção obsoleta ou
que uma resubmissão simultânea crie rodadas concorrentes.

## Decisão

Cada submissão cria um `ReviewSubmission` com:

- número sequencial da rodada e resumo da revisão;
- snapshot da proposta e dos assessments naquele instante;
- política, versão, score e tier usados na avaliação;
- conjunto novo de gates vinculado exclusivamente à rodada.

`changes_requested` encerra a rodada atual, marca gates ainda pendentes como
`superseded` e reabre os assessments submetidos como novos rascunhos versionados. O
owner salva primeiro os fatos corrigidos, permitindo que a política recalcule novos
documentos obrigatórios. Depois, corrige ou cria e envia todos os assessments
estruturados aplicáveis antes de resubmeter a iniciativa. A resubmissão reavalia a
política e cria uma rodada; aprovações anteriores nunca são reutilizadas implicitamente.
`rejected` continua terminal.

As regras de estado, autorização e segregação de funções vivem em domínio Python puro.
Comandos bloqueiam a linha da iniciativa na transação, exigem `expected_version` e
convertem colisões de unicidade em conflito explícito. O frontend apresenta apenas os
gates da rodada atual e uma visão minimizada do histórico.

## Segurança e privacidade

- somente owner, administrador ou revisor participante consulta o histórico;
- snapshots completos não são retornados pelo endpoint de histórico;
- comentários e conteúdo dos snapshots não são copiados para o audit log;
- snapshots ficam no PostgreSQL e herdam criptografia, backup, retenção e controle de
  acesso do banco;
- decisões sobre gates antigos falham de forma fechada;
- em risco alto ou crítico, uma pessoa não decide por mais de uma área na mesma rodada.

## Consequências

A trilha permite reconstruir a proposta avaliada em cada decisão e oferece base para
auditoria e contestação. O custo é armazenamento duplicado e a necessidade de política
explícita de retenção. Downgrade da migração é recusado quando existem rodadas maiores
que um para evitar destruição silenciosa do histórico.
