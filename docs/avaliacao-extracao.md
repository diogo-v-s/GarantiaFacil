# Avaliação da extração de notas fiscais

Registro dos casos testados. Serve de base para a etapa 7 (avaliação) e para comparar
Ollama (modelo local) com Claude.

Campos: produto, loja, data da compra, valor. "Esperado" é o que um humano lê na nota.
Modelo local: `qwen2.5vl:3b`.

## Lição: o prompt e o schema importam mais que o modelo

Na primeira versão, os campos eram opcionais (`str | None`) e o prompt dizia "se não estiver
visível, use null". O modelo local devolvia `null` em quase tudo e só o valor vinha.
Com campos obrigatórios e instruções positivas, o mesmo modelo passou a ler o cupom inteiro.

## Caso 1: cupom simples gerado (texto nítido, 3 itens)

| Versão | produto | loja | data | valor |
|---|---|---|---|---|
| Schema com null | ❌ | ✅ | ✅ | ✅ |

## Caso 2: DANFE (NF-e A4, denso) de celular Moto G60, 11/08/2022, R$ 1.883,20

Esperado: `MOTO G60 128GB - AZUL`, `OPEN COMERCIO DE ELETRONICOS LTDA`, `11/08/2022`, `1883.20`.

| Versão | produto | loja | data | valor |
|---|---|---|---|---|
| Schema com null (webp original) | ❌ | ❌ | ❌ | ✅ |
| Schema com null, PNG ampliado 2x (454 s) | ❌ | ❌ | ❌ | ✅ |
| Dois passos: transcrever e extrair (499 s) | ❌ | ❌ | ❌ | ❌ |
| Campos obrigatórios (versão atual) | ❌ `MOTOROLA` | ⚠️ `ELECTRONICOS` | ❌ 26/03/2022 | ✅ |

Ampliar a imagem e usar dois passos não ajudaram e foram 100 vezes mais lentos.

## Caso 3: cupom NFC-e (GV Villa, foto de celular), 30/09/2026, R$ 219,20

Esperado: `LP KODAK BLUE 1.56`, `GV VILLA LTDA`, `30/09/2026`, `219.20`.

| Versão | produto | loja | data | valor |
|---|---|---|---|---|
| Schema com null | ❌ | ❌ | ❌ | ✅ |
| Campos obrigatórios (versão atual) | ✅ | ✅ | ✅ | ✅ |

## Leitura da chave de acesso (pipeline híbrido)

A chave de 44 dígitos traz CNPJ e mês/ano da compra e tem dígito verificador.

- QR code via OpenCV: não foi lido nas fotos dos casos 2 e 3 (QR cortado na foto do cupom,
  código de barras pequeno no DANFE).
- Chave lida pela IA a partir do texto impresso (caso 3): a IA devolveu 42 dígitos em vez de 44.
  O dígito verificador rejeita leituras assim, então nunca usamos uma chave errada.

## Pipeline híbrido completo (IA + chave de acesso + CNPJ), modelo local

Chave lida pela IA com saída estruturada e validada pelo dígito verificador (nos dois casos
passou). Nome da loja pela BrasilAPI. Tempo: cerca de 15 s por nota.

| Caso | produto | loja | data | valor |
|---|---|---|---|---|
| 2 DANFE | ❌ `MOTOROLA` | ✅ corrigida pelo CNPJ (`ELETRONICOS`) | ⚠️ mês/ano corrigidos (08/2022), dia errado (26 em vez de 11), com aviso | ✅ |
| 3 Cupom | ✅ | ✅ confirmada pelo CNPJ | ✅ mês/ano conferem | ✅ |

## A repetir com Claude (semana que vem)

Rodar os mesmos casos com `LLM_PROVIDER=claude` e preencher uma coluna por modelo.
