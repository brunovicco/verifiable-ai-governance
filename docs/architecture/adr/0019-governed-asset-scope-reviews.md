# ADR 0019 — Revisões de escopo para modelos e agentes

## Status

Aceito.

## Data

2026-08-01.

## Contexto

Registrar provedor, versão ou ferramentas não prova que um ativo foi avaliado para um
uso específico. Uma iniciativa aprovada também não autoriza automaticamente cada
modelo ou agente associado. O inventário precisa distinguir cadastro de aprovação,
vincular a decisão ao escopo material e perder essa aprovação quando o escopo muda.

O mecanismo deve funcionar sem confiar no frontend, evitar autoaprovação pelo owner,
limitar a validade conforme o risco e preservar evidência sem copiar conteúdo sensível
para a auditoria.

## Decisão

Modelos e agentes permanecem em `draft` até uma revisão independente. Arquitetura
revisa modelos; Segurança revisa agentes. O revisor precisa possuir a área exigida e
não pode ser o owner do sistema nem, para agentes, o owner do próprio agente. O papel
administrativo não substitui essa autoridade especializada nem a segregação de funções.

Uma revisão aprovada produz a projeção corrente:

- identidade estável do revisor e instante da decisão;
- próxima revisão limitada pelo risco: 365 dias para baixo, 180 para médio, 90 para
  alto e 30 para crítico;
- referência curta da evidência;
- digest SHA-256 de JSON canônico com todo o escopo aprovado.

O modelo precisa declarar casos de uso aprovados, classes de dados autorizadas e uma
baseline de avaliação. Casos aprovados e proibidos não podem se sobrepor, e a revisão
não pode ultrapassar a data de descontinuação.

O agente precisa declarar versão, região, modelos permitidos e kill switch. Ferramentas
exigem permissões explícitas; autonomia A2 ou superior exige pontos de aprovação
humana; A3 ou superior também exige limites de custo e tempo. Todos os modelos
permitidos precisam estar aprovados e com revisão vigente; a validade do agente não
pode ultrapassar a revisão de nenhuma dessas dependências.

Qualquer alteração material limpa a projeção de revisão e devolve o ativo para
`draft`. Alterar ou aposentar um modelo também invalida agentes aprovados que dependam
dele. Trocar o owner do sistema invalida todas as revisões vinculadas. O estado atual
fica nas tabelas operacionais; decisões e invalidações permanecem no log hash-chained.

## Consequências

- aprovação da iniciativa e aprovação do ativo são decisões diferentes;
- o digest permite comparar a decisão com o escopo corrente sem registrar o conteúdo
  inteiro na auditoria;
- agentes não permanecem aprovados sobre modelos alterados, aposentados ou vencidos;
- datas vencidas não mudam fisicamente o status, mas produzem `review_state=expired`,
  deixam de satisfazer a política e impedem dependências novas até renovação;
- registros de agentes migrados recebem `unversioned` e `unspecified` apenas como
  marcadores de transição e não conseguem aprovação sem atualização explícita;
- enforcement no runtime continua fora deste adapter e será integrado em entrega
  posterior.

## Verificação

- testes de domínio cobrem autoridade, segregação, cadência, readiness e digest;
- testes de aplicação cobrem revisão, dependência entre ativos e invalidação em cascata;
- contratos HTTP validam versão esperada, data timezone-aware e referência limitada;
- o portal coleta os metadados obrigatórios e expõe as revisões especializadas;
- a migração passa por upgrade, downgrade para `0006` e novo upgrade em PostgreSQL real.

## Follow-up

- integrar decisões ao `policy-model-router` para enforcement em runtime;
- alertar antecipadamente revisões próximas do vencimento;
- incluir ativos vencidos e violações no dashboard operacional;
- substituir referências textuais por vínculos opcionais com evidências verificadas.
