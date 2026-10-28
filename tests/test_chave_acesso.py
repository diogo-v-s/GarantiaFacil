from garantiafacil.chave_acesso import buscar_chave, calcular_dv, interpretar


def montar_chave(
    uf="42", aamm="2609", cnpj="11222333000181", modelo="65", serie="001", numero="000000123"
) -> str:
    """Monta uma chave fictícia válida (calculando o dígito verificador)."""
    base = f"{uf}{aamm}{cnpj}{modelo}{serie}{numero}" + "1" + "12345678"
    return base + str(calcular_dv(base))


def test_chave_valida_e_decomposta():
    chave = interpretar(montar_chave())

    assert chave is not None
    assert chave.uf == "42"
    assert (chave.ano, chave.mes) == (2026, 9)
    assert chave.cnpj == "11222333000181"
    assert chave.modelo == "65"
    assert chave.serie == "001"
    assert chave.numero == "000000123"


def test_digito_verificador_errado_rejeita():
    valida = montar_chave()
    errada = valida[:-1] + str((int(valida[-1]) + 1) % 10)
    assert interpretar(errada) is None


def test_um_digito_trocado_e_detectado():
    valida = montar_chave()
    trocada = valida[:10] + ("0" if valida[10] != "0" else "1") + valida[11:]
    assert interpretar(trocada) is None


def test_tamanho_errado_ou_vazio():
    assert interpretar(None) is None
    assert interpretar("") is None
    assert interpretar("123") is None
    assert interpretar(montar_chave() + "0") is None


def test_mes_impossivel_rejeita():
    # Mês 13 com dígito verificador recalculado: estrutura "válida", conteúdo impossível.
    assert interpretar(montar_chave(aamm="2613")) is None


def test_buscar_chave_em_url_de_qr_code():
    chave = montar_chave()
    url = f"https://sat.sef.sc.gov.br/nfce/consulta?p={chave}|2|1|1|ABCDEF123456"
    assert buscar_chave(url) == chave


def test_buscar_chave_impressa_com_espacos():
    chave = montar_chave()
    impressa = " ".join(chave[i : i + 4] for i in range(0, 44, 4))
    assert buscar_chave(f"CHAVE DE ACESSO {impressa}") == chave


def test_buscar_chave_sem_44_digitos():
    assert buscar_chave("nada aqui 12345") is None
    assert buscar_chave("") is None
