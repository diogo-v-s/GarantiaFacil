# Avaliação do RAG

Documento: `docs/exemplos/termo-garantia-exemplo.txt` (fictício, 1.527 caracteres).
Modelos locais: embeddings `bge-m3`, texto `llama3.2:3b`. Temperatura 0, 4 trechos por pergunta.

## Perguntas e resultados

| Pergunta | Está no documento? | Prompt rígido | Prompt brando (atual) |
|---|---|---|---|
| A garantia cobre tela quebrada? | sim (seção 4) | ❌ "não encontrei" | ✅ (citou [4], inexistente) |
| Quanto tempo dura a garantia da bateria? | sim (seção 2) | ✅ | ✅ |
| Preciso da nota fiscal para acionar a garantia? | sim (seção 5) | ❌ "não encontrei" | ✅ |
| Posso usar o aparelho em viagens internacionais? | não | ✅ admitiu não saber | ✅ admitiu não saber |

## Lições

1. **A busca acertou em todas.** O trecho com a resposta ficou em 1º lugar mesmo nas perguntas
   que o modelo errou. Quando o RAG falha, vale checar separadamente se o erro foi da busca
   (trecho certo não veio) ou da geração (veio, mas o modelo não usou).
2. **O prompt rígido** ("responda exatamente 'Não encontrei...' se não estiver nos trechos")
   fez o modelo de 3B recusar perguntas que tinham resposta. O prompt brando ("só recuse se
   nenhum trecho tratar do assunto") corrigiu sem fazer o modelo inventar resposta na pergunta
   sem cobertura.
3. **Citações não são confiáveis.** O modelo citou `[4]` com apenas 3 trechos. O código agora
   confere as citações (`achar_citacoes_invalidas`) e a tela avisa.
4. Tamanho do trecho (800 vs 400 caracteres) não mudou o resultado neste documento pequeno.
   Reavaliar com documentos maiores (manual em PDF de verdade).

## A fazer

- Testar com um manual ou termo real em PDF do usuário.
- Repetir com o Claude e comparar (respostas, citações inventadas, tempo).
- Montar um conjunto fixo de perguntas e respostas esperadas para medir na etapa 7.

## Conversa com produto (28/10/2026)

O chat passou a ter o CDC como base geral e o termo de garantia de cada produto. Se a pergunta
depende do produto, ele pergunta de qual aparelho se trata. Teste com os modelos locais:

| Fala | Resultado |
|---|---|
| "Qual o prazo do CDC para reclamar de defeito em produto durável?" | ✅ 90 dias, só com o CDC |
| "A garantia cobre tela quebrada?" | ✅ perguntou de qual produto |
| "o celular moto g60" | ✅ achou o produto e respondeu com o termo dele |
| "e quanto tempo de garantia?" | ❌ tratou como pergunta geral (o classificador via só a frase solta) |

Correção: o classificador recebe o produto da conversa no prompt. Repetido, a quarta fala
respondeu com o termo do Moto G60.

Lições:

1. **Pergunta de seguimento perde o contexto** se a classificação olhar só a última frase.
2. **Indexar o CDC** (120 trechos) leva ~2,5 min com o bge-m3 na CPU. No app, scripts órfãos de
   reruns do Streamlit rodaram várias indexações ao mesmo tempo e chegaram a 10 min; agora ela
   roda uma vez, numa thread, ao abrir o app.
3. **Latência no modelo local**: ~40 a 60 s por resposta, a maior parte gerando texto na CPU.
   Reduzido por ora para 3 trechos e no máximo 250 tokens (ver `TRECHOS_POR_RESPOSTA` em
   `conversa.py` e `LIMITE_RESPOSTA_OLLAMA` em `llm.py`). Voltar a 5 trechos e tirar o limite
   com o Claude.
