# Avaliação do agente (etapa 6)

Data: 28/10/2026. Modelo: `llama3.2:3b` (Ollama, CPU). Banco real do usuário com 3 produtos:
LP KODAK BLUE 1.56 (vigente), Xbox Series S e MOTO G60 (vencidos).

O agente tem 3 ferramentas (`ferramentas_cadastro.py`): `listar_produtos` (filtros `status` e
`categoria`), `vencimentos_proximos` e `detalhes_produto`. O laço está em `agente.py`.

## Resultados

| Pergunta | Ferramenta escolhida | Resposta |
|---|---|---|
| Qual produto tenho que ainda tem garantia vigente? | `listar_produtos()` sem filtro (1ª tentativa) | ❌ resposta confusa |
| (mesma, depois de ajustar o prompt) | `listar_produtos(status=em_garantia)` | ✅ |
| Quais produtos eletrônicos eu tenho? | `listar_produtos(categoria=Eletrônicos)` | ✅ |
| Quando vence a garantia do moto g60? | `detalhes_produto(nome="moto g60")` | ✅ |
| O que vence nos próximos 60 dias? | nenhuma (classificador mandou para o RAG) | ❌ "Não encontrei" |
| (mesma, depois de dar exemplos ao classificador) | `vencimentos_proximos(dias=60)` | ✅ |
| Quais produtos vencidos eu tenho? | `listar_produtos(status=vencida)` | ✅ depois do ajuste dos dias |
| Quais produtos eu tenho? | `listar_produtos()` | ⚠️ itens certos, título "em garantia" errado |

## Lições

1. **A escolha da ferramenta e dos argumentos foi boa**, até para um modelo de 3B. O que falhou foi
   o texto da resposta e a classificação inicial.
2. **O número negativo enganou o modelo.** `dias_restantes = -8` virou "8 dias restantes". Trocamos
   por texto ("faltam N dias para vencer" / "já venceu"). Com "há 8 dias" ele ainda escreveu "8 dias
   após a compra"; tirar o número dos vencidos resolveu. **Formate o resultado das ferramentas
   para o modelo ler, não para o programador.**
3. **A descrição da ferramenta e o prompt orientam o uso**: dizer "garantia vigente =
   `status=em_garantia`" no prompt fez o modelo passar o filtro.
4. **A classificação é um ponto frágil**: a pergunta sobre o cadastro sem exemplo parecido caiu no
   fluxo de documentos. Exemplos no prompt de classificação corrigem caso a caso; com o Claude,
   avaliar se continua necessário.
5. **Erros de ferramenta não derrubam o agente**: argumento errado ou ferramenta inexistente
   voltam ao modelo como resultado, e há um limite de 5 voltas.

## A fazer (semana do Claude)

- Rodar as mesmas perguntas com o Claude e comparar escolha de ferramenta e texto.
- Testar o `passo()` do Claude de verdade (hoje só com cliente falso).
- Medir perguntas combinadas ("o que vence em 60 dias e quanto paguei?") e cadeias de 2 ferramentas.
- Decidir se o classificador separado continua necessário ou se o agente passa a cuidar de tudo,
  incluindo uma ferramenta `consultar_documentos` (o RAG como ferramenta).

## Classificação "é sobre o cadastro?" (medida com 10 frases)

Com o `llama3.2:3b`, o classificador `sobre_cadastro` acerta 8 a 9 de 10 frases, e o resultado
oscila entre versões do prompt. Erros vistos: "quanto tempo tenho para reclamar de um defeito?"
(pergunta da lei) foi para o agente por causa de "tenho"/"quanto"; "o que vence nos próximos 60
dias?" e "quanto paguei no xbox?" foram para o fluxo de documentos.

- Descrição do campo e critério com o que NÃO é cadastro ("tenho" e "quanto tempo" não indicam
  cadastro) corrigiram a pergunta da lei.
- Padronizar o formato dos exemplos **piorou** (8/10, errando frases que estavam nos exemplos):
  o modelo pequeno não aproveita bem exemplos. Com 10 frases, a diferença de 1 acerto é ruído.
- **Próximo passo:** montar um conjunto maior de frases (a etapa 7 de avaliação) e medir com o
  Claude. Se o Claude acertar, o classificador deixa de ser problema; se não, trocar a
  classificação por um agente único com uma ferramenta `consultar_documentos`.

## Produto sem termo (28/10)

Sem termo cadastrado, o chat buscava a pergunta no CDC e trazia o art. 50 em vez dos arts. 18 e
26, e o modelo respondia "não encontrei". Agora busca a garantia legal direto (consulta fixa sobre
vício do produto e prazos) mais a pergunta, usa um prompt próprio ("explique o que a lei prevê",
no máximo 5 linhas) e avisa que não há termo. Resposta com o modelo local: completa, citando
substituição, devolução do dinheiro e abatimento; a precisão dos prazos (30 e 90 dias) ainda
é irregular.

## Dois erros vistos no uso real (28/10)

1. "quais produtos já venceram a garantia?" → a ferramenta e os dados estavam certos, mas o modelo
   abriu a resposta com "não há nenhum produto com garantia vigente" (falso: a lente está vigente).
   Ele comentou sobre produtos que a ferramenta não devolveu. Correção: o prompt do agente manda
   responder só o que foi perguntado, sem afirmar nada sobre produtos fora da lista devolvida.
2. "o que a garantia do Celular cobria?" → o classificador disse "pergunta geral" e o CDC não tem a
   resposta ("não encontrei"). Em vez de depender só do classificador, há uma **rede de segurança**:
   se uma pergunta geral termina em "não encontrei" e o usuário tem produtos, o chat usa o produto
   da conversa (se houver) ou pergunta se a dúvida é sobre algum deles. Limite conhecido: "celular"
   não bate com o nome "MOTO G60" nem com a categoria "Eletrônicos"; o usuário precisa dizer o nome.
   Resolver com a categoria/descrição gerada pelo Claude (docs/proximos-passos.md, item 3).

**Lição:** não confie num único classificador pequeno; desenhe o fluxo para que o erro dele caia
numa pergunta de esclarecimento, e não numa resposta errada ou numa recusa.
