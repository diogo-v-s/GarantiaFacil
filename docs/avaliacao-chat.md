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

## Conjunto de teste separado (30/10/2026)

`avaliacao/casos_teste.py`: 30 casos novos, em frases que o prompt nunca viu, na mesma base. Regra:
**não se ajusta nada olhando para eles** (`uv run python -m avaliacao.rodar --conjunto teste`). Se um
caso revelar um erro real, conserta-se, o caso vai para `casos.py` e se escreve outro no lugar. Um
teste garante que nenhuma pergunta se repete entre os dois conjuntos.

Antes de rodar: a garantia passou a somar 90 dias da lei (etapa 9), então as datas de compra da base
ficaram 90 dias mais antigas para os vencimentos dos casos continuarem os mesmos. O conjunto de
desenvolvimento seguiu em 29/29, confirmando que nada quebrou.

**Resultado com `claude-haiku-5-5`: 25/30 (83%)**, contra 29/29 (100%) nos casos de desenvolvimento.
Essa diferença de 17 pontos é o quanto os 100% eram ajuste aos exemplos conhecidos.

| Tipo | Desenvolvimento | Teste |
|---|---|---|
| cadastro | 11/11 | 10/12 |
| lei | 5/5 | 6/6 |
| termo | 4/4 | 4/6 |
| sem termo | 3/3 | 2/2 |
| esclarecimento | 2/2 | 1/1 |
| contexto | 4/4 | 2/3 |

As 5 falhas são **todas de roteamento** (o classificador mandou a pergunta pelo caminho errado), não de
conteúdo:
- `t-cad-04` e `t-cad-05` ("O notebook ainda está na garantia?", "O iPhone ainda está coberto?"): foram
  para "produto sem termo" e responderam com o CDC em vez de consultar o cadastro.
- `t-termo-02` e `t-termo-06` (perda de garantia ao abrir a TV; desde quando conta o prazo): foram para o
  CDC e ignoraram o termo da TV.
- `t-ctx-01` ("e da TV?" depois de perguntar o valor da geladeira): foi para o termo em vez do cadastro.

**Conclusão:** o ponto fraco é o classificador, que decide a rota por uma pergunta antes de o modelo
ver as ferramentas. O padrão se repete: a pergunta mistura "garantia" com um produto e o classificador
escolhe documento ou lei. Isso sustenta o próximo experimento (tirar o classificador e deixar o agente
decidir, com o RAG como ferramenta) e dá a régua para medir: ele precisa passar de 25/30 no conjunto
de teste sem piorar o de desenvolvimento.

Cuidado: com 30 casos, 1 acerto são 3 pontos; só diferenças de 3 ou mais casos contam como sinal.

## Ferramenta `total_gasto` (30/10)

Criada a ferramenta (soma o valor pago, com filtro de categoria e aviso dos produtos sem valor) e os
2 casos `opc-*` deixaram de ser opcionais: a rodada de desenvolvimento passa a ter 31 casos. Com o
Claude, os dois passam usando a ferramenta nova (antes ele somava chamando `detalhes_produto` um a um).

## Experimento: tirar o classificador (30/10/2026)

`src/garantiafacil/conversa_agente.py` (`ConversaAgente`): um agente só, sem a chamada que classifica a
pergunta. Recebe as ferramentas do cadastro (incluindo `total_gasto`) mais `consultar_documentos` (o RAG
como ferramenta: sem produto busca no CDC; com produto, no termo dele, ou na garantia legal se não
houver termo) e guarda as últimas 6 mensagens para perguntas de seguimento. Não toca o chat atual:
`uv run python -m avaliacao.rodar --modo agente [--conjunto teste]`.

| Chat (`claude-haiku-5-5`) | Desenvolvimento (31) | Teste (30) | Total (61) | Tempo médio |
|---|---|---|---|---|
| com classificador | 31 (100%) | 25 (83%) | 56 (92%) | 5 s |
| agente decide tudo | 29 (94%) | 28 (93%) | 57 (93%) | 4 s |

**Leitura honesta:** empate técnico no total (1 caso de diferença). A diferença que importa é onde cada
um erra:
- O classificador perdia no teste exatamente por **roteamento**: 5 falhas, todas de rota errada. O agente
  zerou essa classe de erro: no teste, 28/30.
- As 4 falhas do agente (`cad-09` e `termo-02` no desenvolvimento; `t-termo-02` e `t-termo-05` no teste)
  vêm de como a régua mede: ele chamou `listar_produtos` antes de `consultar_documentos` para achar o
  nome do produto, e a régua conta qualquer ferramenta do cadastro como "rota agente".
  O texto de `termo-02` e dos dois do teste está certo. Em `cad-09` listou os 5 produtos em vez de
  filtrar por categoria e respondeu certo. Não mudei a régua depois de ver isso (seria ajustar a
  medida ao resultado); fica registrado como limite dela.
- Nenhum dos 61 casos precisou da "rede de segurança" nem das regras de palavras ("vence", "paguei").

**Custo:** o agente faz mais chamadas ao modelo por pergunta (muitas vezes lista os produtos antes de
consultar o termo). Não medi tokens; o tempo médio ficou igual porque o Claude é rápido.

**Não medido, e provavelmente o ponto fraco:** o `llama3.2:3b` com várias ferramentas. O classificador
existe por causa dele (a avaliação 1 mostrou que escolher ferramentas com 2 perguntas sim/não falhava).

**Pendências do modo agente antes de adotar:** a pergunta "De qual produto?" com opções numeradas
("responda 2") não existe nele (o histórico cobre "a tv", mas não "2"); o texto da resposta não passa por
`limpar_citacoes`; e falta rodar com o Ollama.

Não troquei o chat do app. Decisão pendente: adotar o agente para o Claude e manter o classificador
para o Ollama (`CHAT_MODO`), ou manter só o classificador.

**Decisão (30/10): adotado com chave.** O app usa `criar_conversa` (`conversa_agente.py`), que lê
`CHAT_MODO` no `.env`: `agente` ou `classificador`. Vazio = agente com o Claude e classificador com o
Ollama (onde o agente não foi medido). Voltar ao chat antigo: `CHAT_MODO=classificador`.
