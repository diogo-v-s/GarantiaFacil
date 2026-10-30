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
- [ ] **9. O app trabalha por você** — avisos de vencimento (e-mail/WhatsApp), garantia do
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
- [ ] **11. Deploy** — publicar online, login com Google, banco e arquivos fora da máquina, backup,
      avisos de vencimento por e-mail (precisa do app sempre no ar).

Decisões da etapa 8 (29/10/2026): login por e-mail e senha agora e Google só no deploy; perfil
básico com CPF/CNPJ validado, sem endereço; produtos atuais ficam de fora (começa do zero); o perfil
por enquanto só tem tela própria, sem conferir o destinatário da nota.

Limites conhecidos do login (para a etapa 11): sem "Manter conectado", recarregar a página desloga;
não há limite de tentativas de senha nem recuperação de senha; o e-mail não é confirmado; o cookie
não é HttpOnly (o Streamlit só grava cookie por JavaScript) e só ganha o selo Secure em https.
O login com Google do deploy resolve a sessão e a senha.
