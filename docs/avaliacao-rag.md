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
