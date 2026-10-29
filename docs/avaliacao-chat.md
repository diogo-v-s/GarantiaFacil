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

## Citações e trechos na tela (28/10)

O usuário pediu para esconder os "Trechos usados" e depois os marcadores `[1]`. Decisão e lição:

- A tela não mostra mais os trechos nem os marcadores (`limpar_citacoes`, só na exibição; o texto
  original continua guardado e a checagem de citações inventadas segue funcionando).
- Só apagar os marcadores deixou frases sem sentido ("o trecho também menciona..."). A correção
  foi no prompt: "só no fim da frase; nunca escreva a palavra 'trecho'". O modelo local então parou
  de citar, e o texto saiu limpo. Efeito: a checagem de citação inventada quase nunca dispara agora.
- Reavaliação parcial depois da mudança: lei 4/5 (antes 3/5), termo e sem termo 7/7. A rodada
  completa ainda não foi refeita.
- **Lição:** esconder informação da interface pode exigir mudar o que o modelo escreve, não só o que
  a tela mostra.

## Primeira rodada com o Claude (29/10/2026)

Modelo: `claude-haiku-5-5`, mesma régua e mesma base (31 casos). Nota: **29/29 (100%)** contra 24/29
(83%) do `llama3.2:3b`. Tempo médio por caso: 5 s (era 25 s na CPU).

| Tipo | llama3.2:3b | claude-haiku-5-5 |
|---|---|---|
| cadastro | 10/11 | 11/11 |
| lei | 3/5 | 5/5 |
| termo | 4/4 | 4/4 |
| sem termo | 3/3 | 3/3 |
| esclarecimento | 2/2 | 2/2 |
| contexto | 2/4 | 4/4 |

Os opcionais `total_gasto` continuam falhando: a ferramenta ainda não existe (exercício do usuário).
O Claude se virou com `listar_produtos` + `detalhes_produto` por produto, o que mostra o valor de ter
uma ferramenta própria (menos chamadas e menos erro de soma).

Cuidados: 100% **não** significa pronto. A régua tem 29 casos que o prompt já viu; ela já não separa
bem um modelo bom de um ótimo. O próximo passo útil é o conjunto de teste separado, com casos novos.

Bugs que só apareceram com a API real (o cliente falso não pegava):
1. Os modelos Claude 5 e o SDK 2.x não aceitam `temperature`: removido de `ClaudeLlm`.
2. A resposta pode trazer um bloco de raciocínio antes do texto: `perguntar` agora junta só os blocos
   de texto, como `passo()` já fazia.

**Trechos por provedor (29/10).** `trechos_por_resposta()` entrega 5 trechos com o Claude e 3 com o
Ollama (`LLM_PROVIDER`). Rodada completa com 5 trechos no Claude: 29/29, 5 s por caso, igual a antes:
a régua atual não distingue a diferença. O ganho só aparece num conjunto de teste separado.
