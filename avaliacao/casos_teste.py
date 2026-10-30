"""Conjunto de TESTE da avaliação do chat: casos que o prompt e o código nunca viram.

Regras de uso (é isso que dá valor à nota):
  1. Nunca ajustar prompt, busca ou ferramentas olhando estes casos. Eles só medem.
  2. Rode poucas vezes (`uv run python -m avaliacao.rodar --conjunto teste`), por exemplo ao fim de
     cada etapa, e guarde o resultado.
  3. Se um caso falhar e revelar um erro real: conserte, mova o caso para `casos.py` (passa a ser de
     desenvolvimento) e escreva um caso novo, com outra frase, aqui. Assim o conjunto continua limpo.

Usa a mesma base de `casos.py` (ver `base.py`), em 28/10/2026:
  Geladeira Brastemp   Magazine Luiza  R$ 3.499,90  vence 10/03/2027  (sem termo)
  Smart TV Samsung 50  Casas Bahia     R$ 2.899,00  vence 15/12/2026  (COM termo; 48 dias)
  Furadeira Bosch      Leroy Merlin    R$ 459,90    vence 20/11/2026  (sem termo; 23 dias)
  iPhone 15            Apple Store     R$ 7.299,00  VENCIDA em 22/03/2026
  Notebook Dell        Dell            R$ 4.150,00  vence 01/10/2027
Compras: geladeira 10/12/2025, TV 16/09/2025, furadeira 22/08/2025, iPhone 22/12/2024, notebook 03/07/2026."""

from garantiafacil.avaliacao import Caso

CASOS_TESTE = [
    # ---------- cadastro ----------
    Caso("t-cad-01-loja-tv", "cadastro", ["Em que loja comprei a TV?"], "agente",
         ferramenta=("detalhes_produto", "listar_produtos"), contem=("Casas Bahia",)),
    Caso("t-cad-02-preco-geladeira", "cadastro", ["Quanto custou a geladeira?"], "agente",
         ferramenta="detalhes_produto", contem_algum=("3499", "3.499")),
    Caso("t-cad-03-quantos", "cadastro", ["Quantos produtos tenho cadastrados?"], "agente",
         ferramenta="listar_produtos", contem_algum=("5", "cinco")),
    Caso("t-cad-04-notebook-vigente", "cadastro", ["O notebook ainda está na garantia?"], "agente",
         ferramenta=("detalhes_produto", "listar_produtos"),
         contem_algum=("sim", "01/10/2027", "vigente"), nao_contem=("já venceu",)),
    Caso("t-cad-05-iphone-coberto", "cadastro", ["O iPhone ainda está coberto?"], "agente",
         ferramenta=("detalhes_produto", "listar_produtos"),
         contem_algum=("não", "venceu", "vencida")),
    Caso("t-cad-06-este-mes", "cadastro", ["Tem alguma garantia vencendo ainda este mês?"], "agente",
         ferramenta=("vencimentos_proximos", "listar_produtos"),
         contem_algum=("nenhum", "não há", "não tem", "nada")),  # a próxima é a furadeira, em 23 dias
    Caso("t-cad-07-so-ferramentas", "cadastro", ["Me mostra só o que é de ferramenta."], "agente",
         ferramenta="listar_produtos", argumentos={"categoria": "Ferramentas"},
         contem=("Furadeira",), nao_contem=("Notebook", "Geladeira")),
    Caso("t-cad-08-quanto-falta-tv", "cadastro", ["Quanto tempo falta para acabar a garantia da TV?"],
         "agente", ferramenta=("detalhes_produto", "listar_produtos"), contem_algum=("48", "15/12/2026")),
    Caso("t-cad-09-comprado-em-2026", "cadastro", ["Quais produtos eu comprei em 2026?"], "agente",
         ferramenta="listar_produtos", contem=("Notebook",)),  # os outros quatro são de 2025 ou antes
    Caso("t-cad-10-loja-e-vencimento", "cadastro",
         ["Qual a loja da furadeira e quando a garantia dela acaba?"], "agente",
         ferramenta="detalhes_produto", contem=("Leroy Merlin", "20/11/2026")),
    Caso("t-cad-11-mais-caro", "cadastro", ["Qual é o produto mais caro que eu tenho?"], "agente",
         ferramenta="listar_produtos", contem=("iPhone",)),
    Caso("t-cad-12-produto-inexistente", "cadastro", ["O fone de ouvido está na garantia?"], "agente",
         contem_algum=("não encontrei", "não achei", "nenhum", "não tenho", "não há", "não consta",
                       "não localizei")),  # não pode inventar um fone

    # ---------- lei (CDC) ----------
    Caso("t-lei-01-devolver-online", "lei", ["Posso devolver algo que comprei pelo site da loja?"], "cdc",
         contem_algum=("7 dias", "sete dias", "arrependimento")),
    Caso("t-lei-02-recusa-troca", "lei", ["O vendedor pode se recusar a trocar um produto com defeito?"],
         "cdc", contem_algum=("30 dias", "trinta", "substitu", "abatimento", "restitui", "conserto")),
    Caso("t-lei-03-inicio-do-prazo", "lei", ["A partir de quando conta o prazo para reclamar?"], "cdc",
         contem_algum=("entrega", "evidenci", "aparec", "descobr")),
    Caso("t-lei-04-defeito-tardio", "lei", ["E se o defeito só aparecer meses depois da compra?"], "cdc",
         contem_algum=("evidenci", "oculto", "aparec", "descobert", "momento")),
    Caso("t-lei-05-nao-duravel", "lei", ["Qual o prazo para reclamar de um alimento estragado?"], "cdc",
         contem_algum=("30", "trinta")),
    Caso("t-lei-06-dinheiro-de-volta", "lei",
         ["Posso exigir meu dinheiro de volta se o produto não tiver conserto?"], "cdc",
         contem_algum=("restitui", "devolução", "dinheiro", "reembolso", "quantia")),

    # ---------- produto COM termo (TV) ----------
    Caso("t-termo-01-controle", "termo", ["A garantia da TV cobre o controle remoto?"],
         "documentos_produto", contem_algum=("sim", "cobre")),
    Caso("t-termo-02-tecnico-qualquer", "termo",
         ["Se eu deixar um técnico qualquer abrir a TV, perco a garantia?"],
         "documentos_produto", contem_algum=("sim", "perde", "perco", "perder")),
    Caso("t-termo-03-o-que-levar", "termo", ["O que preciso levar para acionar a garantia da TV?"],
         "documentos_produto", contem=("nota fiscal",)),
    Caso("t-termo-04-uso-comercial", "termo", ["A garantia da TV vale se eu usar no meu restaurante?"],
         "documentos_produto", contem_algum=("não", "comercial")),
    Caso("t-termo-05-raio", "termo", ["Um raio queimou a TV. A garantia cobre?"],
         "documentos_produto", contem_algum=("não", "descarga")),
    Caso("t-termo-06-inicio-12-meses", "termo", ["Desde quando conta o prazo de 12 meses da TV?"],
         ("documentos_produto", "agente"), contem_algum=("nota fiscal", "emissão", "16/09/2025")),

    # ---------- produto SEM termo ----------
    Caso("t-sem-01-iphone", "sem_termo", ["O que a garantia do iPhone cobre?"], "sem_termo",
         contem=("Não há termo",)),
    Caso("t-sem-02-furadeira-motor", "sem_termo", ["A garantia da furadeira cobre motor queimado?"],
         "sem_termo"),

    # ---------- esclarecimento ----------
    Caso("t-esc-01-queda", "esclarecimento", ["A garantia cobre queda?"], "esclarecimento"),

    # ---------- conversa com mais de uma mensagem ----------
    Caso("t-ctx-01-valor-da-tv", "contexto", ["Qual o valor da geladeira?", "e da TV?"], "agente",
         produto="Smart TV", contem_algum=("2899", "2.899")),
    Caso("t-ctx-02-assistencia", "contexto",
         ["A garantia da TV cobre defeito na fonte?", "e a assistência pode ser qualquer uma?"],
         "documentos_produto", produto="Smart TV", contem_algum=("autorizada",)),
    Caso("t-ctx-03-amplia-janela", "contexto", ["O que vence em 60 dias?", "e em 120?"], "agente",
         ferramenta="vencimentos_proximos", contem=("Furadeira", "Smart TV")),
]  # fmt: skip
