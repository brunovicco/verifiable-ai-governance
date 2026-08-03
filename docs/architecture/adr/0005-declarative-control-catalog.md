# ADR 0005 - Catálogo declarativo de controles

- Status: aceito
- Data: 2026-07-31

## Contexto

O framework precisa ligar risco, controle, implementação e evidência sem codificar cada
controle em routers ou componentes do portal. Também precisa explicar por que um
controle se aplica e identificar a versão usada na decisão.

## Decisão

- manter um catálogo baseline de 25 controles em YAML dentro do `policy-engine`;
- validar o arquivo com contratos Pydantic imutáveis e `extra=forbid`;
- exigir IDs únicos, requisitos, evidências e regras de aplicabilidade não ambíguas;
- avaliar seletores de risco, flags, impacto, dados, autonomia e hospedagem por funções
  determinísticas sem I/O;
- retornar resultado e razões para todos os controles, inclusive não aplicáveis;
- derivar o relatório sob consulta em vez de persistir uma cópia;
- expor catálogo e avaliação por portas definidas na camada de aplicação;
- carregar o catálogo uma vez por processo e permitir override por
  `CONTROL_CATALOG_PATH`;
- falhar de forma fechada para arquivo ausente, YAML inválido, schema incompatível,
  IDs duplicados ou quantidade diferente da baseline esperada.

O desenho aplica Open/Closed para inclusão ou ajuste de controles que utilizem os
seletores existentes, Single Responsibility entre schema, loader, evaluator, caso de
uso e UI, e Dependency Inversion na integração da API.

## Twelve-Factor

O catálogo padrão é política versionada junto ao código. Organizações podem anexar uma
configuração externa por variável de ambiente, sem alterar a imagem. A avaliação é
stateless, a dependência YAML é declarada no lockfile e o relatório identifica a versão
da política que produziu o resultado.

## Consequências

- uma mudança de catálogo pode ser revisada como código e testada isoladamente;
- novos tipos de seletor exigem evolução explícita do contrato e do evaluator;
- aplicabilidade não equivale a implementação nem conformidade do controle;
- o relatório atual usa fatos declarados da iniciativa e deverá incorporar evidências
  e status de efetividade em uma etapa posterior.
