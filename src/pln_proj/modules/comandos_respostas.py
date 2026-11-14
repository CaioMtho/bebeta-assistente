# Anchor phrases used by the semantic intent classifier
comandos_funcoes = [
    'o que você pode fazer', 'o que você faz', 'funcionalidades',
    'o que você sabe fazer', 'o que mais você sabe fazer', 'quais são suas funções',
    'quais são seus comandos', 'o que sabe fazer', 'o que faz', 'como funciona',
    'me diga suas funções', 'quais funcionalidades você tem', 'lista de comandos',
    'comandos disponíveis', 'o que você consegue fazer',
]

comandos_anotar = [
    'anotação', 'anotar', 'lembre', 'nova anotação', 'novo lembrete',
    'lembrar', 'lembrete', 'anote', 'mais uma anotação', 'anotar novamente',
    'anote novamente', 'nota', 'adicionar lembrete', 'criar lembrete',
    'fazer anotação', 'fazer uma anotação', 'salvar lembrete', 'guardar lembrete',
    'registrar lembrete', 'escrever lembrete', 'anote isso', 'me lembre de',
    'preciso anotar', 'quero anotar', 'adicionar nota', 'nova nota',
    'não me deixe esquecer de', 'preciso lembrar de comprar',
    'preciso não esquecer de comprar algo', 'me lembre de pagar a conta amanhã',
    'anotar para fazer compras no mercado',
]

comandos_ler_anotacoes = [
    'ler lembretes', 'quais são os lembretes', 'meus lembretes',
    'ler anotações', 'o que eu anotei', 'mostrar lembretes', 'ouvir lembretes',
    'quais são minhas anotações', 'minhas anotações', 'ver lembretes',
    'ver anotações', 'listar lembretes', 'listar anotações', 'ler notas',
    'quais notas eu tenho', 'o que tem anotado', 'tem algum lembrete',
    'ler meus lembretes', 'falar lembretes', 'exibir notas salvas',
]

comandos_atualizar_anotacao = [
    'editar lembrete', 'editar anotação', 'editar nota',
    'alterar lembrete', 'alterar anotação', 'atualizar lembrete',
    'atualizar anotação', 'mudar lembrete', 'mudar o lembrete',
    'mudar texto da nota', 'corrigir anotação', 'modificar lembrete',
    'substituir nota', 'trocar o texto do lembrete', 'renomear anotação',
    'muda a anotação para outro texto', 'alterar o lembrete de algo para outra coisa',
    'editar a nota de um assunto para outro', 'trocar a anotação de algo para outro texto',
]

comandos_concluir_anotacao = [
    'concluir lembrete', 'concluir anotação', 'concluir tarefa',
    'marcar lembrete como concluído', 'marcar nota como feita',
    'finalizar lembrete', 'já fiz esse lembrete', 'completar tarefa',
    'riscar lembrete', 'dar baixa na anotação',
    'já comprei o que estava no lembrete', 'marcar a tarefa de hoje como concluída',
]

comandos_excluir_anotacao = [
    'apagar lembrete', 'apagar um lembrete', 'excluir lembrete',
    'remover lembrete', 'deletar lembrete', 'apagar anotação',
    'excluir anotação', 'remover nota', 'deletar nota',
    'tirar lembrete da lista', 'limpar lembretes',
    'apagar todas as anotações', 'descartar nota',
    'remover o lembrete de comprar algo', 'apagar a anotação da lista',
]

comandos_pesquisar = [
    'pesquisar', 'preciso de ajuda', 'ajuda', 'pode me ajudar',
    'estou com uma dúvida', 'tenho uma dúvida', 'buscar no google', 'pesquisa',
    'pesquisar no google', 'fazer uma pesquisa', 'quero pesquisar', 'buscar',
    'procurar no google', 'procurar', 'google', 'me ajude a pesquisar',
    'tira uma dúvida', 'tirar uma dúvida', 'pesquise na internet sobre',
]

comandos_horas = [
    'que horas são', 'hora', 'hora agora', 'que horas são agora',
    'qual é a hora', 'me diga as horas', 'horas', 'qual o horário',
    'que horário é', 'que horas tem', 'sabe as horas', 'fala as horas',
    'pode me dizer as horas', 'horário atual', 'hora atual',
]

comandos_data = [
    'que dia é hoje', 'que dia é', 'que dia hoje',
    'qual a data de hoje', 'data de hoje', 'data', 'que data é hoje',
    'qual é a data', 'me diga a data', 'hoje é que dia', 'dia de hoje',
    'qual o dia de hoje', 'data atual', 'que dia estamos',
]

comandos_emocao = [
    'modo de emoção', 'ativar emoção', 'ativar modo de emoção',
    'analisar emoção', 'análise de emoção', 'reconhecimento de emoção',
    'prever emoção', 'detectar emoção', 'como estou me sentindo',
]

comandos_identidade = [
    'qual é o seu nome', 'qual seu nome', 'como você se chama',
    'quem é você', 'quem está falando', 'quem fala',
    'me diga seu nome', 'você tem nome', 'seu nome',
    'se apresente', 'qual o nome da assistente',
]

comandos_saudacao = [
    'oi', 'olá', 'ola', 'opa', 'e aí', 'eaí', 'salve',
    'bom dia', 'boa tarde', 'boa noite',
    'tudo bem', 'tudo bom', 'como vai', 'como você está', 'beleza',
]

comandos_agradecimento = [
    'obrigado', 'obrigada', 'valeu', 'muito obrigado', 'muito obrigada',
    'agradeço', 'brigadão', 'grato', 'grata',
]

comandos_encerrar = [
    'encerrar', 'sair', 'tchau', 'fechar', 'parar', 'desligar', 'finalizar',
    'até mais', 'até logo', 'adeus', 'pode parar', 'encerrar assistente',
    'fechar assistente', 'chega por hoje', 'fim',
]

comandos = [
    comandos_funcoes,
    comandos_anotar,
    comandos_ler_anotacoes,
    comandos_atualizar_anotacao,
    comandos_concluir_anotacao,
    comandos_excluir_anotacao,
    comandos_pesquisar,
    comandos_horas,
    comandos_data,
    comandos_emocao,
    comandos_identidade,
    comandos_saudacao,
    comandos_agradecimento,
    comandos_encerrar,
]

# Assistant response templates
texto_funcionalidades = (
    'Posso criar, listar, editar, concluir e excluir lembretes e anotações, '
    'fazer pesquisas no Google, falar as horas e informar a data por extenso.'
)
respostas_identidade = [
    'Eu sou a Bebeta, sua assistente pessoal!',
    'Meu nome é Bebeta! Estou aqui para ajudar com suas anotações, pesquisas, horas e datas.',
    'Prazer, eu sou a Bebeta!',
]
respostas_saudacao = [
    'Olá! Tudo bem? Como posso ajudar?',
    'Oi! Em que posso ajudar hoje?',
    'Olá! Estou por aqui, pode falar!',
]
respostas_conclusao = [
    'Ok!', 'Feito!', 'Concluído!', 'Tudo certo!', 'Terminado!',
    'Pronto!', 'Anotado com sucesso!',
]
respostas_boas_vindas = [
    'Como posso ajudar?', 'Ok, vamos lá!', 'Certo, é só falar!',
    'Em que posso ajudar hoje?', 'Estou ouvindo, pode falar!',
]
respostas_agradecimento = [
    'Se precisar é só chamar!', 'Qualquer coisa estou aqui!',
    'De nada! Estou à disposição.', 'Por nada! Sempre que precisar.',
]
respostas_despedida = [
    'Até mais!', 'Até breve!', 'Até logo!', 'Até a próxima!',
    'Tchau! Tenha um ótimo dia!',
]
respostas_nao_entendi = [
    'Desculpe, não entendi o comando.',
    'Não compreendi. Pode repetir de outra forma?',
    'Desculpe, não reconheci esse comando. Pergunte o que posso fazer para ver as opções.',
]
respostas_ambiguo = [
    f'Não tenho certeza do que você precisa. Pode ser mais específico? {texto_funcionalidades}',
    f'Seu pedido ficou um pouco ambíguo. Pode reformular de forma mais específica? {texto_funcionalidades}',
]

respostas = [
    texto_funcionalidades,
    respostas_identidade,
    respostas_saudacao,
    respostas_conclusao,
    respostas_boas_vindas,
    respostas_agradecimento,
    respostas_despedida,
    respostas_nao_entendi,
    respostas_ambiguo,
]
