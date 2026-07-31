# ADR 0002 — Gates condicionais e fail-closed

- Status: aceito
- Data: 2026-07-31

## Contexto

Exigir as mesmas aprovações para todo caso gera burocracia; omitir áreas com base em
regras implícitas cria risco de promoção indevida.

## Decisão

O policy engine avalia todas as áreas e registra cada uma como `pending` ou
`not_required`, com justificativa. Estado incompleto, regra inconsistente, versão
conflitante, papel ausente ou gate não aprovado bloqueia a promoção.

O owner não pode aprovar a própria iniciativa. Para risco alto ou crítico, a mesma
pessoa não pode aprovar mais de uma área obrigatória.

## Consequências

- a ausência de gate passa a ser explicável e auditável;
- políticas mais rigorosas podem aumentar tempo de aprovação;
- exceções futuras precisarão de entidade própria, prazo, compensating controls e
  aprovação do comitê, sem bypass direto do status.
