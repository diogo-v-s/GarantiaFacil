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

- **Perguntas sobre o cadastro** ("qual produto tenho que ainda tem garantia vigente?") agora são
  respondidas pelo agente (etapa 6, ver [avaliacao-agente.md](avaliacao-agente.md)). Limites do
  modelo local: o título da resposta às vezes sai impreciso e a classificação depende de exemplos
  no prompt. Reavaliar com o Claude.
- O agente ainda não consulta os documentos (RAG) como ferramenta: o chat decide antes, pelo
  classificador, se vai para o agente ou para o RAG.

## Etapas do roteiro ainda não feitas

- 5. RAG em manuais e termos de garantia
- 6. Agente de garantia
- 7. Avaliação
- 8. Extras

## Ideia: XML da nota pela chave do QR code (Tecnospeed / PlugNotas)

Pesquisado em 28/10/2026 (só documentação pública; nada testado).

- O QR code da NFC-e traz a chave de acesso (44 dígitos) como primeiro parâmetro. O pipeline de
  leitura de nota já extrai essa chave (QR ou texto impresso, validada pelo dígito verificador).
- A API **PlugNotas** da Tecnospeed tem a rota "Download do XML Destinatário da NFC-e, por ID ou
  chave" (GET, autenticada por chave de API no cabeçalho, com sandbox e produção). A Tecnospeed
  também descreve o método `ConsultarNF` (consulta na SEFAZ pela chave e recupera o XML).
- **Não confirmado:** se funciona para qualquer chave (nota de terceiro, venda sem CPF) ou só para
  notas em que o CNPJ da conta é emitente ou destinatário; se exige certificado digital; preço e
  limite gratuito. A documentação pública não responde isso.
- Perguntas para o suporte da Tecnospeed: (1) baixa o XML de uma NFC-e qualquer, só com a chave?
  (2) precisa de certificado ou de CNPJ vinculado? (3) existe plano gratuito ou de teste? (4)
  funciona em todas as UFs?
- Se funcionar: chave do QR -> XML -> dados exatos (loja, itens, valor, data), sem erro de IA.
  Manter a leitura por IA como plano B. Não automatizar captcha de portal de SEFAZ.
