# Catálogo de controles

O catálogo baseline conecta características da iniciativa a controles verificáveis. Ele
é uma referência operacional e não constitui certificação ou declaração automática de
conformidade.

## Estrutura de um controle

| Campo | Finalidade |
|---|---|
| `control_id` | Identificador estável usado em evidências e integrações |
| `domain` | Domínio responsável pela organização do catálogo |
| `objective` | Risco ou resultado que o controle pretende tratar |
| `control_type` | Preventivo, detectivo ou corretivo |
| `owner` | Função responsável pelo desenho e acompanhamento |
| `review_frequency` | Cadência mínima ou evento de revisão |
| `requirements` | Condições verificáveis da implementação |
| `evidence` | Evidências esperadas para assurance |
| `implementation_reference` | Implementação técnica opcional do portfólio |
| `applicability` | Regra declarativa avaliada contra a iniciativa |

## Semântica de aplicabilidade

`always: true` identifica controles baseline. Os demais podem selecionar tiers de risco,
flags, impactos, classificações de dados, autonomia e hospedagem. `match: any` aplica o
controle quando qualquer grupo configurado corresponde; `match: all` exige todos os
grupos. Uma regra vazia ou que combine `always` com seletores é rejeitada.

O relatório registra tanto correspondências quanto condições não atendidas. A interface
mostra controles aplicáveis por padrão e permite consultar o catálogo completo.

## Governança do arquivo

- qualquer alteração deve atualizar a versão semântica do catálogo;
- IDs existentes não devem ser reutilizados para objetivos diferentes;
- requisitos e evidências devem ser testáveis e compreensíveis;
- mudanças de regra devem incluir cenários positivos e negativos;
- overlays setoriais serão adicionados sem alterar silenciosamente a baseline.
