# Modelo de governança

## Posicionamento

Este projeto traduz princípios e requisitos de governança em um modelo operacional de
riscos, controles, stage gates, decisões e evidências. Ele complementa referenciais e
obrigações aplicáveis; não os substitui nem declara conformidade automaticamente.

## Cinco camadas

1. **Governança organizacional:** princípios, accountability, comitês, exceções e RACI.
2. **Risco e impacto:** inventário, taxonomia, pessoas afetadas, dados, autonomia,
   escala, reversibilidade e dependência.
3. **Ciclo de vida:** intake, assessment, approval, build, validation, production,
   monitoring, change e retirement.
4. **Controles técnicos:** modelos, dados, RAG, agentes, ferramentas, MCP, segurança,
   observabilidade e avaliações.
5. **Evidência e assurance:** testes, approvals, provenance, auditoria, revisões,
   incidentes e controles compensatórios.

## Princípios

- accountability humana identificável;
- finalidade legítima, necessidade e proporcionalidade;
- segurança e privacidade desde o desenho;
- transparência adequada às pessoas afetadas;
- supervisão humana efetiva, com autoridade e tempo para intervir;
- contestabilidade e remediação quando houver impacto material;
- menor privilégio para modelos, agentes, ferramentas e integrações;
- decisões versionadas, explicáveis e apoiadas por evidência;
- promoção fail-closed e reversão segura;
- monitoramento proporcional ao risco durante todo o ciclo de vida.

## Classificação preliminar

O score de 0 a 100 considera impacto (30), dados (25), autonomia (25), exposição (10)
e contexto regulatório (10). Regras de elevação garantem que direitos/segurança e alta
autonomia não sejam diluídos por uma soma baixa em outras dimensões.

| Tier | Tratamento mínimo |
|---|---|
| Baixo | owner, system card, revisão periódica simples |
| Médio | gates técnicos aplicáveis, testes e monitoramento definido |
| Alto | assurance independente, threat model, monitoramento e revisões frequentes |
| Crítico | decisão de comitê, supervisão reforçada, limites de autonomia e stop criteria |

O score é triagem, não decisão final. Revisores podem elevar o risco com justificativa;
redução futura exigirá evidência e aprovação de Governança de IA.

## Inventário operacional

Somente uma iniciativa aprovada pode originar um sistema de IA. O owner da iniciativa
atribui um responsável identificável ao sistema; esse responsável controla o registro
de modelos e agentes. Modelos e agentes novos começam em `draft`, pois a aprovação da
iniciativa não substitui avaliação, escopo aprovado ou baseline técnico do ativo.

A exclusão física não faz parte do fluxo normal. Aposentar um sistema muda seu estado,
desativa a indicação de produção, aposenta os ativos vinculados e registra evidência
auditável. Alterações posteriores ficam bloqueadas.

## Cadeia de controle

Cada controle deverá declarar identificador, objetivo, tipo, aplicabilidade, owner,
requisitos, evidências, frequência de revisão, implementação e limitações. O catálogo
completo é item P0 do backlog seguinte ao scaffold.

```text
Risco identificado
  → controle aplicável
    → gate e owner
      → evidência versionada
        → decisão
          → monitoramento e revisão
```
