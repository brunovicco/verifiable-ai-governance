# RACI

Legenda: **R** executa, **A** responde pelo resultado, **C** é consultado, **I** é
informado. Um único processo pode ter vários responsáveis técnicos, mas apenas um
accountable business owner por iniciativa.

| Atividade | Negócio | Gov. IA | Arquitetura | Segurança | Infra | DevOps | Privacidade | Jurídico | Compliance | Dados |
|---|---|---|---|---|---|---|---|---|---|---|
| Propor caso de uso | A/R | C | I | I | I | I | I | I | I | C |
| Classificar risco preliminar | C | A/R | C | C | I | I | C | C | C | C |
| Validar arquitetura | C | C | A/R | C | C | C | I | I | I | C |
| Threat model e controles de segurança | I | C | C | A/R | C | C | C | I | C | I |
| Validar capacidade, região e resiliência | I | C | C | C | A/R | C | C | I | I | C |
| Validar entrega, rollback e observabilidade | I | C | C | C | C | A/R | I | I | I | I |
| RIPD e tratamento de dados pessoais | C | C | I | C | I | I | A/R | C | C | C |
| Base contratual e transferência internacional | I | C | I | C | C | I | R | A | C | I |
| Obrigações setoriais | C | C | I | C | I | I | C | C | A/R | I |
| Qualidade, lineage e acesso a dados | C | C | C | C | I | I | C | I | C | A/R |
| Aceitar risco residual e go-live | A | R | C | C | C | C | C | C | C | C |
| Monitorar produção | A | C | I | C | C | R | C | I | C | R |
| Gerir incidente | A | C | C | R | C | R | C | C | C | C |
| Auditar evidências | I | R | I | I | I | I | I | I | C | I |

## Segregação mínima

- owner/solicitante não decide gates da própria iniciativa;
- quem desenvolve ou opera não emite sozinho o veredito de assurance;
- alto/crítico exige pessoas independentes entre áreas aprovadoras;
- administrador da plataforma não recebe automaticamente autoridade de aprovação;
- exceção não é aprovada pelo mesmo papel que solicita ou implementa a exceção.

## Identidade corporativa

- IAM administra app registrations, consentimentos, grupos e ciclo de vida no Entra;
- Segurança aprova trust boundaries, Conditional Access, credenciais e scopes;
- Governança de IA responde pelo mapeamento App Role/grupo → área de aprovação;
- Privacidade valida atributos coletados do Graph, finalidade, retenção e localização;
- Infra/DevOps operam configuração, secret manager, disponibilidade e observabilidade;
- nenhuma dessas funções pode alterar sozinha um mapeamento e aprovar usando a
  capacidade que acabou de conceder.
