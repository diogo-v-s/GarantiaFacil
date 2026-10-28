# Próximos passos

## Quando a chave do Claude estiver disponível (previsto para a semana de 02/11/2026)

1. Colocar a chave no `.env` (`ANTHROPIC_API_KEY`) e mudar `LLM_PROVIDER=claude`. Definir um
   limite de gasto mensal baixo no console da Anthropic.
2. **Repetir a avaliação da leitura de notas** com os mesmos casos de
   [avaliacao-extracao.md](avaliacao-extracao.md) e preencher uma coluna por modelo
   (principalmente produto e dia da data do DANFE, que o modelo local erra).
3. **Categoria na busca por significado.** O produto agora tem o campo `Categoria`
   (Eletrodomésticos, Eletrônicos, Ferramentas, Vestuário, Móveis, Brinquedos, Automotivo, Outros), escolhido pelo usuário. Falta fazê-la entrar no
   texto indexado junto com o nome e, com o Claude, sugerir a categoria ao ler a nota.
   Motivo: "Moto G60 128GB - AZUL" tem similaridade 0,467 com "celular" (abaixo do corte de 0,5);
   com "celular smartphone" no texto vai a 0,578. O modelo local (llama3.2:3b) errou a categoria
   ("Papel fotográfico" para uma lente), então só vale testar com o Claude.
   - Validar com os casos: Moto G60 → celular, Kodak Blue 1.56 → óculos/lentes.
   - Cuidado: reindexar os produtos já cadastrados quando a regra mudar.
4. **Desfazer os limites do chat local**: `TRECHOS_POR_RESPOSTA` (3, era 5) em `conversa.py` e
   `LIMITE_RESPOSTA_OLLAMA` (250 tokens) em `llm.py` só existem por causa da lentidão da CPU.

## Lacunas conhecidas do chat

- **Perguntas sobre o próprio cadastro não funcionam.** "Qual produto tenho que ainda tem garantia
  vigente?" é tratada como pergunta de produto e o chat pergunta "de qual produto?". O chat só
  consulta textos (CDC e termos). Solução = etapa 6 (agente): ferramentas para listar produtos
  por status, calcular vencimentos e buscar um produto; o modelo escolhe quando usá-las. A lógica
  já existe em `garantia.py` (`status_garantia`, `contar_por_status`, `proximos_vencimentos`).

## Etapas do roteiro ainda não feitas

- 5. RAG em manuais e termos de garantia
- 6. Agente de garantia
- 7. Avaliação
- 8. Extras
