# GarantiaFácil

Organizador de notas fiscais e garantias. Consumidores perdem comprovantes e não lembram até quando
um produto está na garantia. Este projeto guarda notas, fotos e documentos e avisa antes do vencimento.

É também um **projeto de estudo** de LLM, RAG e agentes, feito passo a passo.

## MVP

- Cadastro de produtos
- Upload de comprovantes (nota fiscal, foto, PDF)
- Prazo de garantia e data de vencimento
- Busca

## Stack

- Python 3.12+ com gerenciador `uv`
- SDK da Anthropic (Claude), sem framework de agentes no começo
- SQLite (dados) e Chroma (banco vetorial)
- Interface web simples (Streamlit ou FastAPI, a decidir na etapa 2)

## Como rodar

```bash
uv sync
copy .env.example .env   # preencha a ANTHROPIC_API_KEY
uv run pytest
```

## Roteiro

Veja [docs/roteiro.md](docs/roteiro.md).
