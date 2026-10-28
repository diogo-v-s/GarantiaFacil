# Próximos passos

## Quando a chave do Claude estiver disponível (previsto para a semana de 02/11/2026)

1. Colocar a chave no `.env` (`ANTHROPIC_API_KEY`) e mudar `LLM_PROVIDER=claude`. Definir um
   limite de gasto mensal baixo no console da Anthropic.
2. **Repetir a avaliação da leitura de notas** com os mesmos casos de
   [avaliacao-extracao.md](avaliacao-extracao.md) e preencher uma coluna por modelo
   (principalmente produto e dia da data do DANFE, que o modelo local erra).
3. **Categoria gerada pela IA para a busca por significado.** Decisão: não criar campo no
   cadastro; a IA gera a categoria e ela entra no texto indexado junto com o nome.
   Motivo: "Moto G60 128GB - AZUL" tem similaridade 0,467 com "celular" (abaixo do corte de 0,5);
   com "celular smartphone" no texto vai a 0,578. O modelo local (llama3.2:3b) errou a categoria
   ("Papel fotográfico" para uma lente), então só vale testar com o Claude.
   - Validar com os casos: Moto G60 → celular, Kodak Blue 1.56 → óculos/lentes.
   - Cuidado: reindexar os produtos já cadastrados quando a regra mudar.

## Etapas do roteiro ainda não feitas

- 5. RAG em manuais e termos de garantia
- 6. Agente de garantia
- 7. Avaliação
- 8. Extras
