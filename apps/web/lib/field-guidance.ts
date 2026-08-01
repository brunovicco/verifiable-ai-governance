export const proposalFieldGuidance = {
  name: "Use um nome curto e reconhecível, que diferencie esta proposta de outros projetos ou sistemas.",
  description:
    "Explique o problema atual, o resultado esperado e por que IA é necessária. Evite descrever apenas a tecnologia.",
  business_area:
    "Informe a área que responderá pela finalidade, pelos riscos e pela operação da iniciativa.",
  intended_users:
    "Liste os perfis que usarão ou receberão resultados da IA, incluindo usuários internos e externos.",
  decision_impact:
    "Considere a consequência plausível mais grave de uma saída incorreta, mesmo quando houver revisão humana.",
  autonomy_level:
    "Selecione o maior nível de autonomia permitido: informar, recomendar, preparar ou executar uma ação.",
  data_classification:
    "Escolha a classificação mais restritiva entre todos os dados enviados, inferidos, armazenados ou registrados.",
  hosting_model:
    "Indique onde o modelo e seus dados serão processados. Considere provedor SaaS, nuvem, ambiente próprio ou combinação.",
  inference_countries:
    "Liste todos os países envolvidos em inferência, armazenamento, logs, backup, suporte ou acesso administrativo.",
  change_reason:
    "Resuma o fato novo ou a correção realizada e relacione-a ao pedido do revisor. Não inclua dados sensíveis.",
  revision_summary:
    "Descreva as correções concluídas, os assessments atualizados e as evidências adicionadas para a nova rodada.",
} as const;

export const initiativeCheckGuidance = {
  affects_rights:
    "Marque quando a IA puder influenciar acesso, elegibilidade, benefícios, emprego, crédito ou outro direito ou oportunidade.",
  executes_actions:
    "Marque quando a IA puder alterar dados, enviar mensagens, acionar ferramentas ou executar etapas de um processo.",
  personal_data:
    "Inclua dados identificados ou identificáveis usados em prompts, bases, respostas, logs ou avaliações.",
  sensitive_data:
    "Marque para dados como saúde, biometria, origem racial, religião, opinião política, vida sexual ou filiação sindical.",
  children_data:
    "Marque se crianças ou adolescentes forem usuários, afetados ou titulares dos dados tratados.",
  external_facing:
    "Marque se clientes, cidadãos, parceiros ou o público interagirem com a IA ou receberem suas saídas.",
  regulated_context:
    "Marque quando a iniciativa operar em setor, atividade ou processo sujeito a obrigação regulatória específica.",
  international_processing:
    "Marque se dados puderem ser processados, armazenados ou acessados fora do Brasil, inclusive por suporte ou subprocessadores.",
  uses_rag:
    "Marque quando a solução consultar documentos ou bases externas ao modelo para compor suas respostas.",
  uses_agents:
    "Marque quando a IA planejar múltiplas etapas, escolher ferramentas ou agir com alguma autonomia para concluir uma tarefa.",
  uses_mcp:
    "Marque quando houver conexão a servidores MCP para acessar dados, ferramentas ou recursos externos.",
  uses_custom_model:
    "Marque para treinamento, fine-tuning, adaptação ou hospedagem de modelo sob responsabilidade da organização.",
} as const;

export const assessmentFieldGuidance = {
  affected_groups:
    "Liste pessoas e grupos direta ou indiretamente afetados, incluindo quem não usa o sistema, mas recebe suas consequências.",
  intended_benefits:
    "Descreva benefícios verificáveis para cada grupo e, quando possível, a métrica que demonstrará o resultado.",
  potential_harms:
    "Inclua cenários de erro, discriminação, perda de privacidade, automação indevida e uso fora da finalidade.",
  human_oversight:
    "Informe quem revisa, em que momento, com quais informações e qual autoridade possui para interromper ou corrigir a IA.",
  contestability:
    "Explique o canal, o prazo e o responsável por receber contestação, revisar o resultado e oferecer remediação.",
  mitigation_measures:
    "Liste controles existentes ou planejados, seus responsáveis e como a efetividade será demonstrada.",
  controller_area:
    "Informe a área que define a finalidade e os meios do tratamento de dados pessoais nesta iniciativa.",
  legal_basis:
    "Registre a hipótese aplicável validada por Privacidade ou Jurídico; não presuma uma base apenas por conveniência operacional.",
  processing_purpose:
    "Descreva uma finalidade específica, legítima e compatível com o que foi informado aos titulares.",
  personal_data_categories:
    "Liste as categorias efetivamente necessárias, incluindo dados inferidos, prompts, respostas, logs e identificadores.",
  data_subjects:
    "Liste os grupos de titulares e destaque crianças, adolescentes ou outras pessoas em situação de vulnerabilidade.",
  necessity_assessment:
    "Explique por que cada categoria de dado é necessária, quais alternativas foram consideradas e como o uso foi minimizado.",
  risk_scenarios:
    "Descreva eventos que possam causar dano aos titulares, indicando fonte, probabilidade, impacto e pessoas afetadas.",
  safeguards:
    "Liste medidas técnicas, organizacionais e contratuais, com responsável e evidência de que funcionam.",
  data_categories:
    "Liste tudo o que cruza fronteiras ou pode ser acessado do exterior: prompts, documentos, saídas, logs e metadados.",
  source_country:
    "Informe o país onde os dados são coletados ou de onde partem antes do processamento internacional.",
  inference_countries:
    "Liste os países onde o modelo poderá executar inferências, incluindo rotas de contingência do provedor.",
  storage_regions:
    "Inclua regiões de armazenamento primário, réplicas, backups, caches e bancos vetoriais.",
  log_regions:
    "Inclua onde logs, traces, telemetria, avaliações e dados de suporte são armazenados ou acessados.",
  subprocessor_name:
    "Informe o fornecedor que recebe ou acessa dados em nome do provedor principal. Deixe vazio somente se não houver.",
  subprocessor_countries:
    "Liste os países de processamento, armazenamento ou suporte do suboperador informado.",
  subprocessor_purpose:
    "Explique qual serviço o suboperador presta e por que o acesso aos dados é necessário.",
  transfer_mechanism:
    "Informe o mecanismo aplicável à transferência internacional conforme validação de Privacidade ou Jurídico.",
  residual_risk:
    "Classifique o risco que permanece depois dos controles. Considere probabilidade, severidade e reversibilidade do dano.",
} as const;

export const reviewFieldGuidance = {
  reviewer:
    "No modo local, informe uma identificação rastreável do revisor. Em produção, a identidade corporativa será usada automaticamente.",
  decision:
    "Aprove somente quando os requisitos da sua área estiverem atendidos; solicite ajustes quando houver correção possível e rejeite quando o impedimento for definitivo.",
  comments:
    "Registre os requisitos avaliados, as limitações encontradas, as condições da decisão e o risco aceito ou bloqueante.",
  evidence_uri:
    "Aponte para a evidência que sustenta a decisão, como ticket, documento versionado ou URN. Evite links pessoais ou temporários.",
  evidence_kind:
    "Classifique o arquivo pelo propósito principal para que revisores e auditoria encontrem a evidência correta.",
  evidence_file:
    "Anexe um artefato final, legível e sem credenciais. Prefira formatos estáveis e preserve a versão usada na decisão.",
} as const;
