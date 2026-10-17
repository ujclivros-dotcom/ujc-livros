import csv, html, io, json, os, re, smtplib, ssl, time, unicodedata, hashlib
from datetime import date, timedelta
from email.message import EmailMessage
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, urljoin
import requests

API = "https://pncp.gov.br/api/consulta/v1/contratacoes"
SEEN = Path("seen.json")
DIAS_A_FRENTE = 90
DIAS_PUBLICACAO = 3
MAX_PAGINAS = 400
MODALIDADES = [4, 5, 6, 7, 8, 12]
UFS = []
EXTRAS = []

KEYWORDS = [
    "produto quimico", "produtos quimicos", "desengraxante", "desengripante",
    "solvente", "thinner", "lubrificante", "graxa", "oleo lubrificante",
    "antiferrugem", "anticorrosivo", "removedor", "limpa contato", "tinta",
    "verniz", "esmalte", "resina", "soda caustica", "hipoclorito", "acido",
    "detergente", "desinfetante", "saneante", "sabao", "cera", "silicone",
    "vedante", "adesivo", "cola industrial", "fluido", "aditivo", "querosene",
    "alcool isopropilico", "material de limpeza", "inseticida", "cloro",
    "material de consumo industrial", "manutencao industrial",
]
EXCLUIR = ["medicamento", "hospitalar", "software", "obra de engenharia",
           "veiculo", "passagem aerea", "alimenticio", "genero alimenticio"]

PORTAIS = {"bllcompras": "BLL", "bnc.org": "BNC", "licitanet": "Licitanet",
           "portaldecompraspublicas": "Compras Públicas", "gov.br/compras": "Compras.gov.br",
           "compras.gov": "Compras.gov.br", "comprasnet": "ComprasNet",
           "bb.com.br": "Licitações-e (BB)", "comprasbr": "ComprasBR",
           "pncp.gov": "PNCP", "compras.mg": "Compras MG", "bec.sp": "BEC SP"}
ERROS = []

def norm(t):
    t = unicodedata.normalize("NFD", t or "").lower()
    return "".join(c for c in t if unicodedata.category(c) != "Mn")

def casa(texto):
    t = norm(texto)
    return any(k in t for k in KEYWORDS) and not any(x in t for x in EXCLUIR)

def get(url, params=None):
    for i in range(4):
        try:
            r = requests.get(url, params=params, timeout=60,
                             headers={"User-Agent": "Mozilla/5.0 RadarLicitacoes"})
            if r.status_code in (200, 204): return r
        except requests.RequestException:
            pass
        time.sleep(3 * (i + 1))
    ERROS.append(f"Falha em {url} {params or ''}")
    return None

def paginar(url, params):
    p = 1
    while p <= MAX_PAGINAS:
        r = get(url, {**params, "pagina": p, "tamanhoPagina": 50})
        if r is None or r.status_code == 204: return
        d = r.json()
        yield from d.get("data", [])
        if p >= d.get("totalPaginas", 1): return
        p += 1

def portal(c):
    link = (c.get("linkSistemaOrigem") or "").lower()
    for k, v in PORTAIS.items():
        if k in link: return v
    return urlparse(link).netloc or "PNCP"

def normalizar(c):
    u, o = c.get("unidadeOrgao") or {}, c.get("orgaoEntidade") or {}
    cnpj = o.get("cnpj", "")
    return {
        "id": c.get("numeroControlePNCP") or f"{cnpj}-{c.get('anoCompra')}-{c.get('sequencialCompra')}",
        "esfera": {"F": "Federal", "E": "Estadual", "M": "Municipal", "D": "Distrital"}.get(o.get("esferaId"), "?"),
        "orgao": o.get("razaoSocial", ""), "cidade": u.get("municipioNome", ""), "uf": u.get("ufSigla", ""),
        "modalidade": c.get("modalidadeNome", ""), "numero": c.get("numeroCompra", ""),
        "objeto": c.get("objetoCompra") or "", "valor": c.get("valorTotalEstimado"),
        "prazo": c.get("dataEncerramentoProposta") or "", "portal": portal(c),
        "link": c.get("linkSistemaOrigem") or f"https://pncp.gov.br/app/editais/{cnpj}/{c.get('anoCompra','')}/{c.get('sequencialCompra','')}",
        "pncp": f"https://pncp.gov.br/app/editais/{cnpj}/{c.get('anoCompra','')}/{c.get('sequencialCompra','')}",
    }

def fonte_pncp():
    achados = {}
    fim = (date.today() + timedelta(days=DIAS_A_FRENTE)).strftime("%Y%m%d")
    for c in paginar(f"{API}/proposta", {"dataFinal": fim}):
        if casa(c.get("objetoCompra")): achados[c.get("numeroControlePNCP")] = c
    ini = (date.today() - timedelta(days=DIAS_PUBLICACAO)).strftime("%Y%m%d")
    hoje = date.today().strftime("%Y%m%d")
    for m in MODALIDADES:
        for c in paginar(f"{API}/publicacao", {"dataInicial": ini, "dataFinal": hoje,
                                                "codigoModalidadeContratacao": m}):
            if casa(c.get("objetoCompra")): achados.setdefault(c.get("numeroControlePNCP"), c)
    out = [normalizar(c) for c in achados.values()]
    return [x for x in out if not UFS or x["uf"] in UFS]

class _Links(HTMLParser):
    def __init__(self): super().__init__(); self.l, self._h, self._t = [], None, ""
    def handle_starttag(self, tag, a):
        if tag == "a": self._h, self._t = dict(a).get("href"), ""
    def handle_data(self, d):
        if self._h is not None: self._t += d
    def handle_endtag(self, tag):
        if tag == "a" and self._h is not None:
            self.l.append((self._h, " ".join(self._t.split()))); self._h = None

def fonte_extras():
    out = []
    for nome, url in EXTRAS:
        r = get(url)
        if r is None or r.status_code != 200: continue
        p = _Links(); p.feed(r.text)
        for href, txt in p.l:
            if len(txt) > 15 and casa(txt):
                full = urljoin(url, href)
                out.append({"id": "x-" + hashlib.md5(full.encode()).hexdigest(), "esfera": "Municipal",
                            "orgao": nome, "cidade": "", "uf": "", "modalidade": "Portal próprio",
                            "numero": "", "objeto": txt, "valor": None, "prazo": "",
                            "portal": urlparse(url).netloc, "link": full, "pncp": ""})
    return out

def texto(it):
    v = f"R$ {it['valor']:,.2f}" if it["valor"] else "n/i"
    return (f"[{it['esfera']}] {it['orgao']} - {it['cidade']}/{it['uf']}\n{it['modalidade']} {it['numero']} | Portal: {it['portal']}\n"
            f"Objeto: {it['objeto'][:350]}\nValor: {v} | Propostas até: {it['prazo'][:16]}\nLink: {it['link']}\n")

def corpo_html(novos):
    linhas = ""
    for it in novos:
        v = "R$ {:,.2f}".format(it["valor"]) if it["valor"] else "n/i"
        linhas += ("<tr><td>%s</td><td>%s<br>%s/%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                   "<td><a href='%s'>edital</a></td></tr>" % (
                   it["esfera"], html.escape(it["orgao"]), html.escape(it["cidade"]), it["uf"],
                   html.escape(it["objeto"][:300]), v, it["prazo"][:16], html.escape(it["portal"]), it["link"]))
    return ("<h3>%d novas licitações</h3><table border=1 cellpadding=4 style='border-collapse:collapse;font:13px Arial'>"
            "<tr><th>Esfera</th><th>Órgão</th><th>Objeto</th><th>Valor</th><th>Prazo</th><th>Portal</th><th>Link</th></tr>%s</table>"
            % (len(novos), linhas))

def enviar(assunto, txt, htm=None, anexo=None):
    if os.getenv("SMTP_HOST"):
        m = EmailMessage()
        m["Subject"], m["From"], m["To"] = assunto, os.environ["SMTP_USER"], os.environ["EMAIL_TO"]
        m.set_content(txt)
        if htm: m.add_alternative(htm, subtype="html")
        if anexo: m.add_attachment(anexo.encode("utf-8-sig"), maintype="text", subtype="csv", filename="licitacoes.csv")
        with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], 465, context=ssl.create_default_context()) as s:
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"]); s.send_message(m)
    if os.getenv("TELEGRAM_TOKEN"):
        for i in range(0, len(txt), 3800):
            requests.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}/sendMessage",
                          data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": txt[i:i+3800]})
    print(txt)

def main():
    vistos = set(json.loads(SEEN.read_text())) if SEEN.exists() else set()
    todos = {i["id"]: i for i in fonte_pncp() + fonte_extras()}
    novos = [i for k, i in todos.items() if k not in vistos]
    novos.sort(key=lambda i: (i["esfera"], i["prazo"]))
    aviso = ("\n\n⚠ Avisos:\n" + "\n".join(sorted(set(ERROS)))) if ERROS else ""
    if novos:
        buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=list(novos[0]), delimiter=";")
        w.writeheader(); w.writerows(novos)
        enviar(f"Radar de Licitações: {len(novos)} novas ({date.today():%d/%m/%Y})",
               f"{len(novos)} novas licitações:\n\n" + "\n".join(texto(i) for i in novos) + aviso,
               corpo_html(novos) + html.escape(aviso).replace("\n", "<br>"), buf.getvalue())
    else:
        enviar(f"Radar de Licitações: sem novidades ({date.today():%d/%m/%Y})", "Nenhuma licitação nova hoje." + aviso)
    SEEN.write_text(json.dumps(sorted(vistos | {i["id"] for i in novos if i["id"]})))

if __name__ == "__main__":
    main()
