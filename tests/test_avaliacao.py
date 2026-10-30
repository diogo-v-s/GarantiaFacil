from types import SimpleNamespace

from garantiafacil.agente import Consulta
from garantiafacil.avaliacao import Caso, avaliar_caso, conferir, formatar, resumir, rota_da
from garantiafacil.conversa import Mensagem
from garantiafacil.rag import TrechoEncontrado


def trecho(produto_id=None) -> TrechoEncontrado:
    return TrechoEncontrado(fonte="f.txt", pagina=1, texto="t", similaridade=0.9, produto_id=produto_id)


def mensagem(texto="ok", trechos=(), consultas=(), citacoes_invalidas=()) -> Mensagem:
    return Mensagem(texto, list(trechos), list(citacoes_invalidas), None, list(consultas))


def consulta(nome="listar_produtos", **argumentos) -> Consulta:
    return Consulta(nome, argumentos, "{}")


# ---------- rota_da ----------


def test_rota_de_cada_tipo_de_resposta():
    assert rota_da(mensagem(consultas=[consulta()])) == "agente"
    assert rota_da(mensagem("De qual produto você está falando?")) == "esclarecimento"
    assert rota_da(mensagem("Não achei isso nas leis. A pergunta é sobre...")) == "esclarecimento"
    assert rota_da(mensagem("Não há termo de garantia cadastrado para 'X'.", [trecho()])) == "sem_termo"
    assert rota_da(mensagem("Cobre.", [trecho(produto_id=3), trecho()])) == "documentos_produto"
    assert rota_da(mensagem("90 dias.", [trecho()])) == "cdc"
    assert rota_da(mensagem("???")) == "outra"


# ---------- conferir ----------


def caso(**campos) -> Caso:
    padrao = dict(id="c", tipo="t", mensagens=["?"], rota="cdc")
    return Caso(**{**padrao, **campos})


def test_caso_que_cumpre_tudo_nao_tem_falhas():
    c = caso(contem=("90",), nao_contem=("nunca",))

    assert conferir(c, mensagem("O prazo é de 90 dias.", [trecho()]), None) == []


def test_falha_de_rota_e_aceita_mais_de_uma_rota():
    resposta = mensagem("90 dias", [trecho()])

    assert any("rota" in f for f in conferir(caso(rota="agente"), resposta, None))
    assert conferir(caso(rota=("agente", "cdc")), resposta, None) == []


def test_texto_compara_sem_acento_e_sem_diferenca_de_maiuscula():
    c = caso(contem=("Não",), contem_algum=("GARANTIA",))

    assert conferir(c, mensagem("nao cobre. A garantia vale.", [trecho()]), None) == []


def test_falta_e_proibicao_no_texto():
    c = caso(contem=("90",), nao_contem=("fabricação",))

    falhas = conferir(c, mensagem("Cobre defeitos de fabricação.", [trecho()]), None)

    assert any("faltou" in f for f in falhas) and any("não devia aparecer" in f for f in falhas)


def test_ferramenta_e_argumentos_esperados():
    c = caso(rota="agente", ferramenta="listar_produtos", argumentos={"status": "vencida"})

    assert conferir(c, mensagem(consultas=[consulta(status="vencida")]), None) == []
    sem_filtro = conferir(c, mensagem(consultas=[consulta()]), None)
    outra = conferir(c, mensagem(consultas=[consulta("vencimentos_proximos")]), None)
    assert any("argumentos" in f for f in sem_filtro)
    assert any("ferramenta" in f for f in outra)


def test_argumentos_comparam_sem_acento():
    c = caso(rota="agente", ferramenta="listar_produtos", argumentos={"categoria": "Eletrônicos"})

    assert conferir(c, mensagem(consultas=[consulta(categoria="eletronicos")]), None) == []


def test_citacao_inventada_e_falha():
    falhas = conferir(caso(), mensagem("x [4]", [trecho()], citacoes_invalidas=[4]), None)

    assert any("citação" in f for f in falhas)


def test_assunto_da_conversa():
    c = caso(produto="Smart TV")

    assert conferir(c, mensagem("x", [trecho()]), SimpleNamespace(nome="Smart TV Samsung 50")) == []
    assert any("assunto" in f for f in conferir(c, mensagem("x", [trecho()]), None))


# ---------- avaliar_caso e resumir ----------


class ConversaFalsa:
    def __init__(self, respostas, erro=None):
        self.respostas, self.erro = list(respostas), erro
        self.produto_atual = None
        self.recebidas = []

    def responder(self, fala):
        self.recebidas.append(fala)
        if self.erro:
            raise self.erro
        return self.respostas.pop(0)


def test_so_a_ultima_resposta_e_avaliada_e_toda_a_conversa_e_enviada():
    conversa = ConversaFalsa([mensagem("De qual produto?"), mensagem("90 dias", [trecho()])])
    c = caso(mensagens=["a", "b"], rota="cdc", contem=("90",))

    resultado = avaliar_caso(c, lambda: conversa)

    assert resultado.passou and conversa.recebidas == ["a", "b"] and resultado.rota == "cdc"


def test_cada_caso_comeca_com_conversa_nova():
    criadas = []

    def criar():
        criadas.append(ConversaFalsa([mensagem("90", [trecho()])]))
        return criadas[-1]

    avaliar_caso(caso(), criar)
    avaliar_caso(caso(), criar)

    assert len(criadas) == 2


def test_excecao_na_conversa_vira_falha_e_nao_derruba_a_avaliacao():
    conversa = ConversaFalsa([], erro=ConnectionError("Ollama fora do ar"))

    resultado = avaliar_caso(caso(), lambda: conversa)

    assert not resultado.passou and "Ollama fora do ar" in resultado.falhas[0]


def test_resumo_ignora_opcionais_agrupa_por_tipo_e_lista_falhas():
    def resultado(id, tipo, passou, opcional=False):
        return SimpleNamespace(
            caso=id, tipo=tipo, passou=passou, falhas=[] if passou else ["rota: x"],
            segundos=10.0, opcional=opcional,
        )  # fmt: skip

    resumo = resumir(
        [
            resultado("a", "lei", True),
            resultado("b", "lei", False),
            resultado("c", "cadastro", True),
            resultado("d", "opcional", False, opcional=True),
        ]
    )

    assert (resumo.acertos, resumo.total) == (2, 3)
    assert resumo.por_tipo == {"lei": (1, 2), "cadastro": (1, 1)}
    assert [r.caso for r in resumo.falhas] == ["b"] and [r.caso for r in resumo.opcionais] == ["d"]
    texto = formatar(resumo)
    assert "2/3" in texto and "[b]" in texto and "Opcionais" in texto


# ---------- conjunto de teste separado ----------


def test_conjunto_de_teste_nao_repete_caso_nem_pergunta_do_desenvolvimento():
    from avaliacao.casos import CASOS
    from avaliacao.casos_teste import CASOS_TESTE

    ids = [c.id for c in CASOS + CASOS_TESTE]
    assert len(ids) == len(set(ids))

    def perguntas(casos):
        return {m.strip().lower() for c in casos for m in c.mensagens}

    assert perguntas(CASOS) & perguntas(CASOS_TESTE) == set()
