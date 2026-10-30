# Roteiro de estudo

Marque cada etapa ao concluir. Em cada uma: conceito, código feito junto e um exercício sozinho.

- [x] **1. Fundação** — ambiente Python, estrutura do projeto, primeira chamada à API do Claude;
      tokens, janela de contexto, temperatura, system prompt.
- [x] **2. MVP sem IA** — cadastro de produtos, upload, prazo de garantia, busca simples (SQLite).
- [x] **3. Extração da nota fiscal** — LLM com visão, saída estruturada (JSON validado), tratamento de erro.
- [x] **4. Embeddings e busca semântica** — o que é um embedding, similaridade, busca por significado.
- [x] **5. RAG em manuais e termos de garantia** — chunking, banco vetorial (Chroma), respostas com fonte.
- [x] **6. Agente de garantia** — tool use: consultar produtos, calcular prazo, montar alerta de vencimento.
- [x] **7. Avaliação** — conjunto de testes, medir acerto, custo e latência, melhorar.
- [x] **8. Usuários e experiência** — login (e-mail e senha), perfil PF/PJ com CPF/CNPJ validado,
      dados separados por usuário, cadastro de várias notas, foto pela câmera do celular, painel
      com gasto por categoria e linha do tempo, tema escuro, estado vazio e primeiro acesso.
      - [x] Data vazia na leitura da nota (a IA devolvia a data com hora; agora lê e avisa)
      - [x] Login e dados por usuário (e-mail e senha com hash scrypt; produtos de antes do login
            ficam sem dono e invisíveis; backup em `data/backup-antes-do-login/`)
      - [x] Perfil PF/PJ (CPF/CNPJ validado pelo dígito verificador; tela Editar perfil no menu do
            usuário, que fica fixo no rodapé da barra lateral)
      - [x] Manter conectado (token aleatório em cookie, só o hash no banco, 30 dias)
      - [x] Várias notas de uma vez (cada arquivo é uma nota; a IA lê todas e você confere e salva
            uma por vez, ou pula)
      - [x] Painel (total investido, gasto por categoria, vencimentos nos próximos 12 meses e o que
            perde a garantia em 90 dias)
      - [x] Primeiro acesso (boas-vindas com 3 passos) e estados vazios (lista filtrada, painel e
            chat com perguntas de exemplo clicáveis)
      - [x] Tema escuro (claro e escuro no config.toml; o usuário troca no menu ⋮; nossas cores
            seguem o tema ativo)
      - [x] Foto do produto pela câmera (ou arquivo), no cadastro e nos detalhes do produto
- [x] **9. O app trabalha por você** — avisos de vencimento (e-mail/WhatsApp), garantia do
      fabricante somada à legal, termo em PDF sugerindo o prazo.
      - [x] Termo em PDF sugerindo o prazo (a IA lê o prazo, converte para meses e só aceita se a
            frase existir no texto; o usuário confirma com "Usar N meses")
      - [x] Garantia do fabricante somada à legal (decisão de 30/10: os prazos se somam, CDC art. 50;
            90 dias da legal depois do fim do prazo do fabricante, para produto durável). Sem coluna nova.
            Não trata o termo que declara já incluir a legal: se for preciso, vira caixa por produto.
      - [x] Avisos de vencimento no app (faixa em Meus produtos e aviso ao entrar; cada usuário
            escolhe a antecedência em Preferências). E-mail fica para a etapa 11, com o app sempre
            no ar.
- [ ] **10. Chat mais esperto** — chat que age (lembretes, cadastro com confirmação), testar tirar o
      classificador, conjunto de teste separado, servidor MCP próprio.
      - [x] Conjunto de teste separado (30 casos novos; Claude: 25/30 no teste contra 29/29 no
            desenvolvimento; as 5 falhas são do classificador)
      - [x] Testar tirar o classificador (`conversa_agente.py`; Claude: 57/61 contra 56/61 do
            chat atual, sem os erros de rota; adotado no app com a chave CHAT_MODO: agente com o
            Claude, classificador com o Ollama, que ainda falta medir no modo agente)
      - [x] Ferramenta `total_gasto` (exercício)
      - [x] Chat que age: cadastro com confirmação (30/10). O agente só PROPÕE (`propor_cadastro`,
            nada é gravado); um cartão com Confirmar/Cancelar grava, e é o código quem grava, nunca
            o modelo. Só no modo agente. Testado no Chrome
      - [x] Chat que age: excluir produto e mudar categoria/prazo com confirmação (mesmo cartão;
            `propor_exclusao` e `propor_alteracao`; só um pendente por vez). Testado no Chrome.
            Achou e corrigiu um bug antigo: o seletor de categoria dos detalhes regravava o valor
            velho do widget e desfazia mudanças feitas por fora (agora o banco manda, on_change grava)
      - [x] Sininho de notificações (30/10): selo vermelho com a quantidade e janelinha no rodapé do
            menu. Dois tipos: aviso de vencimento (automático, calculado na hora pela antecedência
            das Preferências) e lembrete programado (tabela nova `lembretes`: produto, data, texto,
            concluído). Lembrete criado pelo chat com confirmação (`propor_lembrete`, só de hoje em
            diante) e aparece no sino a partir da data. Só dentro do app; e-mail fica para a etapa 12.
            Cada notificação tem o botão "Lido" (e há "Marcar todas como lidas"): no lembrete conclui,
            no aviso guarda a leitura (tabela `notificacoes_lidas`; a chave tem produto, vencimento e
            faixa, então o aviso volta ao entrar na faixa de 7 dias ou se a data mudar). Testado no Chrome
      - [ ] Lembrete também pela tela do produto (campo data + texto) e avisos por e-mail (etapa 12)
      - [x] Chat flutuante: botão redondo em todas as telas (menos na aba Perguntas) que abre o
            mesmo chat, com o mesmo histórico (pedido de 30/10)
      - [x] Servidor MCP próprio (`servidor_mcp.py`): as 4 ferramentas de consulta (só leitura)
            viram um servidor MCP por stdio, para o Claude Code ou o Claude Desktop usarem; a conta
            vem de TAGUARDADO_EMAIL. Não expõe cadastrar/excluir/alterar (sem cartão de confirmação
            o modelo gravaria sem você ver). Testado com um cliente MCP real (processo à parte).
            Como registrar no Claude Code: está no topo de `servidor_mcp.py`
- [ ] **11. Onde acionar a garantia** — assistências que atendem o produto (nome, endereço, contato),
      buscadas na internet perto do endereço do usuário. Pedido de 30/10; ainda não detalhado.
      - [ ] Endereço no perfil (opcional; decidido em 30/10: se houver, é o padrão da busca; se não,
            pergunta a cidade na hora) — coluna nova; falta decidir CEP ou endereço completo
      - [x] Demonstração com OpenStreetMap (30/10): `assistencias.py` (Nominatim acha a cidade,
            Overpass lista lojas e oficinas num raio de 6 km; cache de 7 dias; só repassa o que o
            mapa tem). Google Places fica para depois: exige cartão e ainda não dá para pagar
      - [x] Tela "Onde acionar" (cidade digitada na hora) e ferramenta `onde_acionar_garantia` no chat
      - [ ] Medir a qualidade: em Campinas vieram lugares sem telefone (a maioria) e lojas que não
            são assistência (Vivo, TIM, Magazine Luiza); o Overpass público é lento (~1 min) e às
            vezes dá erro 502. Decidir se compensa trocar a fonte
- [ ] **12. Deploy** — publicar online, login com Google, banco e arquivos fora da máquina, backup,
      avisos de vencimento por e-mail (precisa do app sempre no ar).

Decisões da etapa 8 (29/10/2026): login por e-mail e senha agora e Google só no deploy; perfil
básico com CPF/CNPJ validado, sem endereço; produtos atuais ficam de fora (começa do zero); o perfil
por enquanto só tem tela própria, sem conferir o destinatário da nota.

Limites conhecidos do login (para a etapa 11): sem "Manter conectado", recarregar a página desloga;
não há limite de tentativas de senha nem recuperação de senha; o e-mail não é confirmado; o cookie
não é HttpOnly (o Streamlit só grava cookie por JavaScript) e só ganha o selo Secure em https.
O login com Google do deploy resolve a sessão e a senha.
