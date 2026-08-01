# Stage gates

| Gate | Entrada | Saída obrigatória | Bloqueios típicos |
|---|---|---|---|
| G0 Intake | objetivo e owner | registro e ID | owner/finalidade ausente |
| G1 Triage | questionário completo | risk tier, documentos e gates | respostas incompatíveis |
| G2 Assessment | system card e AIA | riscos e tratamentos propostos | RIPD/transferência ausente |
| G3 Design | arquitetura e fornecedores | aprovações técnicas condicionais | ameaça, região ou acesso sem controle |
| G4 Validation | versão candidata e plano de testes | relatório de avaliação e limites | métrica abaixo do threshold |
| G5 Go-live | gates aprovados e evidências | decisão versionada, rollback e owner operacional | qualquer gate pendente/rejeitado |
| G6 Operation | telemetria e baseline | revisões, alertas e incidentes tratados | drift, violação ou modelo não aprovado |
| G7 Change/Retire | change assessment ou plano de saída | nova decisão ou evidência de descontinuação | mudança material sem reavaliação |

## Mudanças materiais

Troca de modelo/versão, novo país, nova categoria de dados, ferramenta ou permissão,
aumento de autonomia, mudança de finalidade, novo público afetado e alteração de
threshold devem reabrir assessment. O sistema não reaproveitará aprovação anterior por
similaridade implícita.

Uma solicitação de ajuste em G2–G5 encerra a rodada corrente, preserva o snapshot
avaliado e reabre os assessments existentes como rascunhos versionados. Depois das
correções, o owner fornece um resumo, reenvia os assessments e cria uma nova rodada com
política e gates recalculados. Rejeição definitiva não pode ser convertida em
ressubmissão sem um novo processo formal.
