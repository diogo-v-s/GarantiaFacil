# Avaliação do chat (etapa 7)

Data: 28/10/2026. Modelo: `llama3.2:3b` (Ollama, CPU). Embeddings: `bge-m3`.

## Como medir

- `avaliacao/casos.py`: 31 casos (29 na nota + 2 opcionais do exercício `total_gasto`). Cada caso
  descreve o que se espera, não o texto exato: por onde a pergunta passa (agente, CDC, termo do
  produto, produto sem termo, esclarecimento), qual ferramenta e argumentos, o que a resposta deve ou
  não conter e qual produto fica como assunto.
- `avaliacao/base.py`: base fixa (5 produtos, 1 termo de TV, CDC) e data fixa (28/10/2026), para os
  resultados se repetirem. Fica em `data/avaliacao.db`, fora do git.
- `uv run python -m avaliacao.rodar` roda tudo (`--filtro` e `--limite` gravam como `_parcial`);
  `uv run python -m avaliacao.classificador` mede só o classificador.
- Os resultados de cada rodada ficam em `avaliacao/resultados/`.
- A régua tem testes próprios (`tests/test_avaliacao.py`).

## Evolução

| Rodada | Mudança | Nota | Classificador |
|---|---|---|---|
| 1 | desenho original: duas perguntas sim/não (`sobre_cadastro`, `precisa_produto`) | 15/29 (52%) | 14/22 (64%) |
| 2 | uma classificação de 3 opções (cadastro, lei, produto) | 21/29 (72%) | 18/22 (82%) |
| 3 | busca com o nome do produto + exemplos de "vence" | **24/29 (83%)** | 21/22 (95%)* |

\* Otimista: os exemplos novos do prompt são paráfrases de casos que estavam falhando (ver Cuidados).

Por tipo na rodada 3: cadastro 10/11, termo 4/4, sem termo 3/3, esclarecimento 2/2, contexto 2/4,
lei 3/5. Tempo médio por caso: 25 s (máximo 63 s) na CPU.

## O que cada mudança ensinou

1. **Dois sim/não viram "não" nos dois.** O modelo pequeno tem um viés para a resposta padrão: os 8
   erros da rodada 1 foram todos para "lei". Uma escolha entre 3 opções obriga a decidir.
2. **A rede de segurança escondia o problema.** Perguntas de cadastro classificadas como "lei"
   terminavam em "não achei nas leis, é sobre algum produto?". Evitava resposta errada, mas o
   agente nunca era chamado. A avaliação mostrou isso em minutos.
3. **Busca de seguimento precisa de contexto.** "E o prazo?" sozinha acha o CDC. Com o nome do
   produto na busca ("Smart TV: e o prazo?"), acha o termo.
4. **Referência vaga não pode ser resolvida por significado quando já há um produto.** "Desse
   produto" virava o iPhone 15 pela busca semântica e trocava o assunto em silêncio (`ctx-02`).
   Corrigido: com produto em discussão, só vale casar pelo nome. Depois da correção, `ctx-02` passa.
5. **Medir em separado mostra onde está o erro.** O classificador isolado (64%) explicou a maior
   parte das falhas da nota geral.

## Falhas que restam (modelo local)

- `cad-09`: chamou `listar_produtos` sem o filtro de categoria e disse "você tem 4 produtos" (eram
  5): erro de contagem do modelo pequeno.
- `lei-04`, `lei-05`: perguntas gerais da lei ("o fornecedor é obrigado a trocar?", "o que é garantia
  legal?") terminam em "não encontrei" no CDC. É um problema de busca/resposta, não do classificador.
- `ctx-03`: "e o prazo?" já busca o termo da TV, mas o modelo responde "não encontrei" mesmo com o
  trecho certo (recusa falsa, já vista antes).
- Opcionais `total_gasto`: falham até a ferramenta existir (exercício do usuário).

## Cuidados com a medida

- **Contaminação.** Ajustei o prompt olhando as frases que falhavam. Uma primeira tentativa deu 86%
  porque os exemplos eram quase iguais aos casos de teste; refeita com frases diferentes, deu 77%.
  Os exemplos de "vence" adicionados depois são paráfrases dos casos `cad-04`, `cad-05` e `cad-11`,
  então os 95% e parte dos 83% estão inflados. **A nota justa exige casos que o prompt nunca viu.**
- Com 29 casos, uma diferença de 1 acerto (3,5 pontos) é ruído.
- Os tempos de algumas rodadas foram inflados por outras tarefas usando o mesmo modelo.

## Próximos passos

1. Criar um **conjunto de teste separado** (casos novos, nunca usados para ajustar o prompt) e medir
   só nele.
2. Rodar a mesma régua com o **Claude** (semana de 02/11) e comparar nota, tipo a tipo, e tempo.
3. Se o Claude acertar o roteamento, avaliar tirar o classificador e deixar o agente decidir, com uma
   ferramenta `consultar_documentos` (o RAG como ferramenta).
4. Investigar `lei-04` e `lei-05`: por que o CDC não responde perguntas gerais (tamanho do trecho,
   número de trechos, consulta da busca).
5. Medir também a **qualidade do texto** (hoje só medimos roteamento e conteúdo), por exemplo com um
   segundo modelo como juiz, e a taxa de resposta inventada.
