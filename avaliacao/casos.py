"""Casos de avaliação do chat. Cada caso diz o que se espera, não o texto exato da resposta.

Situação dos produtos da base de avaliação em 28/10/2026 (ver base.py). Os vencimentos abaixo são
o fim de TODA a cobertura (prazo do fabricante + 90 dias da garantia legal):
  Geladeira Brastemp   vigente, vence 10/03/2027      (sem termo)
  Smart TV Samsung 50  vigente, vence 15/12/2026      (COM termo; 48 dias)
  Furadeira Bosch      vence em breve, 20/11/2026     (sem termo; 23 dias)
  iPhone 15            VENCIDA em 22/03/2026          (sem termo)
  Notebook Dell        vigente, vence 01/10/2027      (sem termo)

Ao encontrar um erro no uso real, acrescente um caso aqui: ele vira regressão medida."""

from garantiafacil.avaliacao import Caso

NOMES = ("Geladeira", "Smart TV", "Furadeira", "iPhone", "Notebook")

CASOS = [
    # ---------- perguntas sobre o cadastro (agente com ferramentas) ----------
    Caso("cad-01-todos", "cadastro", ["quais produtos eu tenho?"], "agente",
         ferramenta="listar_produtos", contem=NOMES),
    Caso("cad-02-em-garantia", "cadastro", ["quais produtos ainda estão na garantia?"], "agente",
         ferramenta="listar_produtos", argumentos={"status": "em_garantia"},
         contem=("Geladeira", "Smart TV", "Furadeira", "Notebook"), nao_contem=("iPhone",)),
    Caso("cad-03-vencidos", "cadastro", ["quais produtos já venceram a garantia?"], "agente",
         ferramenta="listar_produtos", argumentos={"status": "vencida"}, contem=("iPhone",),
         nao_contem=("Geladeira", "Furadeira", "nenhum produto que ainda")),  # regressão: dizia que nenhum estava vigente
    Caso("cad-04-vence-60", "cadastro", ["o que vence nos próximos 60 dias?"], "agente",
         ferramenta="vencimentos_proximos", contem=("Furadeira", "Smart TV"),
         nao_contem=("iPhone", "Geladeira")),
    Caso("cad-05-vence-30", "cadastro", ["o que vence nos próximos 30 dias?"], "agente",
         ferramenta="vencimentos_proximos", contem=("Furadeira",), nao_contem=("Smart TV",)),
    Caso("cad-06-data-geladeira", "cadastro", ["quando vence a garantia da geladeira?"], "agente",
         ferramenta="detalhes_produto", contem=("10/03/2027",)),
    Caso("cad-07-valor-iphone", "cadastro", ["quanto paguei no iPhone?"], "agente",
         ferramenta="detalhes_produto", contem_algum=("7299", "7.299")),
    Caso("cad-08-eletronicos", "cadastro", ["quais eletrônicos eu tenho?"], "agente",
         ferramenta="listar_produtos", argumentos={"categoria": "Eletrônicos"},
         contem=("Smart TV", "iPhone", "Notebook"), nao_contem=("Geladeira", "Furadeira")),
    Caso("cad-09-ferramentas", "cadastro", ["tenho alguma ferramenta cadastrada?"], "agente",
         ferramenta="listar_produtos", argumentos={"categoria": "Ferramentas"}, contem=("Furadeira",)),
    Caso("cad-10-data-compra", "cadastro", ["quando comprei a furadeira?"], "agente",
         ferramenta="detalhes_produto", contem=("22/08/2025",)),
    Caso("cad-11-primeiro-a-vencer", "cadastro", ["qual produto vence primeiro?"], "agente",
         ferramenta=("vencimentos_proximos", "listar_produtos"), contem=("Furadeira",)),

    # ---------- perguntas sobre a lei (CDC) ----------
    Caso("lei-01-reclamar", "lei", ["Quanto tempo tenho para reclamar de um defeito?"], "cdc",
         contem_algum=("90", "noventa", "30", "trinta")),  # regressão: ia para o agente por causa de "tenho"
    Caso("lei-02-desistir", "lei", ["Posso desistir de uma compra feita pela internet?"], "cdc",
         contem_algum=("7 dias", "sete dias")),
    Caso("lei-03-prazo-duravel", "lei",
         ["Qual o prazo do CDC para reclamar de defeito em produto durável?"], "cdc",
         contem_algum=("90", "noventa")),
    Caso("lei-04-trocar", "lei", ["O fornecedor é obrigado a trocar um produto com defeito?"], "cdc",
         contem_algum=("substitu", "troca", "conserto", "reparo")),
    Caso("lei-05-garantia-legal", "lei", ["O que é garantia legal?"], "cdc"),

    # ---------- produto COM termo de garantia (TV) ----------
    Caso("termo-01-tela-quebrada", "termo", ["A garantia da TV cobre tela quebrada?"],
         "documentos_produto", contem_algum=("não",)),
    Caso("termo-02-defeito-painel", "termo", ["A garantia da TV cobre defeito no painel?"],
         "documentos_produto", contem_algum=("sim", "coberto", "cobre defeitos")),
    Caso("termo-03-prazo", "termo", ["Quanto tempo dura a garantia da Smart TV?"],
         ("agente", "documentos_produto"), contem_algum=("12", "doze")),
    Caso("termo-04-assistencia", "termo", ["A assistência técnica da TV precisa ser autorizada?"],
         "documentos_produto", contem_algum=("autorizada",)),

    # ---------- produto SEM termo: avisa e explica o CDC ----------
    Caso("sem-01-geladeira", "sem_termo", ["O que a garantia da geladeira cobre?"], "sem_termo",
         contem=("Não há termo",)),
    Caso("sem-02-notebook", "sem_termo", ["A garantia do notebook cobre bateria?"], "sem_termo"),
    Caso("sem-03-furadeira", "sem_termo", ["Qual a cobertura da garantia da furadeira?"], "sem_termo"),

    # ---------- esclarecimento: não dá para responder sem saber o produto ----------
    Caso("esc-01-sem-produto", "esclarecimento", ["A garantia cobre tela quebrada?"],
         "esclarecimento"),  # a introdução da pergunta varia; vale perguntar de qual produto
    Caso("esc-02-celular", "esclarecimento", ["o que a garantia do celular cobria?"],
         "esclarecimento"),  # regressão: respondia "não encontrei"

    # ---------- conversa com mais de uma mensagem ----------
    Caso("ctx-01-responde-qual", "contexto", ["A garantia cobre tela quebrada?", "a tv"],
         "documentos_produto", produto="Smart TV", contem_algum=("não",)),
    Caso("ctx-02-desse-produto", "contexto",
         ["qual a data de vencimento da furadeira?", "o que a garantia desse produto cobre?"],
         "sem_termo", produto="Furadeira", nao_contem=("defeitos de fabricação",)),  # regressão: o agente inventava a cobertura
    Caso("ctx-03-e-o-prazo", "contexto", ["o que a garantia da TV cobre?", "e o prazo?"],
         ("agente", "documentos_produto"), produto="Smart TV", contem_algum=("12", "doze", "15/12/2026")),
    Caso("ctx-04-e-os-vencidos", "contexto",
         ["quais produtos estão na garantia?", "e quais já venceram?"], "agente",
         ferramenta="listar_produtos", argumentos={"status": "vencida"}, contem=("iPhone",)),

    # ---------- ferramenta total_gasto (era o exercício do usuário; agora entra na nota) ----------
    Caso("opc-01-gasto-eletronicos", "opcional", ["quanto gastei com eletrônicos?"], "agente",
         ferramenta="total_gasto", contem_algum=("14348", "14.348")),
    Caso("opc-02-gasto-total", "opcional", ["quanto gastei no total?"], "agente",
         ferramenta="total_gasto", contem_algum=("18307", "18.307")),
]  # fmt: skip
