from garantiafacil.documentos import dividir_em_trechos, extrair_paginas


def test_extrai_texto_de_arquivo_txt():
    assert extrair_paginas("termo.txt", "Garantia de 12 meses.".encode()) == [
        (1, "Garantia de 12 meses.")
    ]


def test_arquivo_sem_texto_devolve_lista_vazia():
    assert extrair_paginas("vazio.txt", b"  \n ") == []


def test_pdf_corrompido_devolve_lista_vazia():
    assert extrair_paginas("quebrado.pdf", b"isto nao e um pdf") == []


def test_texto_curto_vira_um_trecho_so():
    trechos = dividir_em_trechos([(3, "Garantia de 12 meses.\n\nVale a partir da compra.")])

    assert len(trechos) == 1
    assert trechos[0].pagina == 3
    assert "Garantia de 12 meses." in trechos[0].texto
    assert "Vale a partir da compra." in trechos[0].texto


def test_texto_longo_vira_varios_trechos_de_tamanho_limitado():
    paragrafos = [f"Paragrafo {i}. " + "palavra " * 40 for i in range(20)]
    trechos = dividir_em_trechos([(1, "\n\n".join(paragrafos))], tamanho=500, sobreposicao=80)

    assert len(trechos) > 3
    # tamanho + sobreposição + folga do separador
    assert all(len(t.texto) <= 500 + 80 + 10 for t in trechos)


def test_todo_o_conteudo_aparece_em_algum_trecho():
    paragrafos = [f"Item{i} " + "texto " * 50 for i in range(15)]
    trechos = dividir_em_trechos([(1, "\n\n".join(paragrafos))], tamanho=400, sobreposicao=60)
    junto = " ".join(t.texto for t in trechos)

    assert all(f"Item{i}" in junto for i in range(15))


def test_sobreposicao_repete_o_fim_do_trecho_anterior():
    paragrafos = [f"Marca{i} " + "conteudo " * 30 for i in range(10)]
    trechos = dividir_em_trechos([(1, "\n\n".join(paragrafos))], tamanho=400, sobreposicao=100)

    for anterior, proximo in zip(trechos, trechos[1:]):
        ultima_palavra = anterior.texto.split()[-1]
        assert ultima_palavra in proximo.texto[:200]


def test_nao_corta_palavras_no_meio():
    texto = "\n\n".join(f"Paragrafo numero {i} com palavras completas e inteiras." for i in range(40))
    trechos = dividir_em_trechos([(1, texto)], tamanho=300, sobreposicao=60)
    vocabulario = set(texto.split())

    for trecho in trechos:
        assert set(trecho.texto.split()) <= vocabulario


def test_paragrafo_gigante_sem_pontuacao_e_quebrado():
    trechos = dividir_em_trechos([(1, "palavra " * 500)], tamanho=300, sobreposicao=50)

    assert len(trechos) > 5
    assert all(len(t.texto) <= 300 + 50 + 10 for t in trechos)


def test_preserva_o_numero_da_pagina():
    trechos = dividir_em_trechos([(1, "Pagina um."), (7, "Pagina sete.")])

    assert [t.pagina for t in trechos] == [1, 7]
