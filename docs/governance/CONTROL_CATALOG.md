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

## Crosswalk de apoio com frameworks externos

`packages/policy-engine/src/policy_engine/control_crosswalk.yaml` mapeia cada
controle a referências do NIST AI RMF (NIST AI 100-1), do NIST AI 600-1 (perfil de IA
generativa), do OWASP Top 10 for LLM Applications & Generative AI, do OWASP Top 10 for
Agentic Applications e do MITRE ATLAS. É um arquivo próprio, versionado separadamente
do catálogo baseline - não altera `applicability` nem qualquer decisão de política.

As citações foram construídas a partir da leitura direta dos textos-fonte oficiais:
NIST AI 100-1 (AI RMF 1.0, jan/2023), NIST AI 600-1 (Generative AI Profile, jul/2024),
OWASP Top 10 for LLM Applications & Generative AI 2025 (nov/2024), OWASP Top 10 for
Agentic Applications 2026 (dez/2025) e MITRE ATLAS, conferido contra o relatório MITRE
SAFE-AI (abr/2025) e as referências cruzadas que o próprio OWASP Top 10 faz para IDs
de técnica do ATLAS. Mesmo assim, o crosswalk não constitui parecer jurídico,
certificação ou declaração de conformidade - deve ser revisado por jurídico/compliance
antes de uso formal, e cada referência pode ser reconferida contra o texto oficial do
framework correspondente. Os controles de domínio `agent` (GOV-AGT-*) usam o OWASP
Agentic Top 10 (códigos ASI01-ASI10) como referência principal para riscos
específicos de sistemas multiagente, complementar ao OWASP LLM Top 10.

Citações do NIST AI RMF usam função/categoria nomeada (ex.: "GOVERN 2") como
granularidade padrão; subcategoria numerada (ex.: "GOVERN 1.6") só aparece nos
poucos casos em que corresponde de forma direta e inequívoca ao controle - escolha
editorial deliberada, não uma limitação de acesso à fonte. O concept note "NIST AI
RMF: Trustworthy Use of AI in Critical Infrastructure Profile" (abr/2026) ainda não
define categorias de risco citáveis (é um documento de planejamento, não um perfil
publicado) e por isso não está referenciado; será avaliado quando um perfil completo
for publicado.

ISO/IEC 42001 está listado como pendente (`frameworks_pending`) por ser norma
licenciada; nenhuma referência é citada contra ela até haver acesso ao texto oficial.
O carregador (`GovernanceControlCrosswalk`) falha de forma fechada se uma entrada
referenciar um `control_id` que não existe no catálogo carregado, e pode ser
substituído por `CONTROL_CROSSWALK_PATH`, no mesmo padrão de
`CONTROL_CATALOG_PATH`.
