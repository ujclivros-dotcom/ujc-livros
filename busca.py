import os, io, csv, html
from datetime import date
import radar

termos = [radar.norm(t.strip()) for t in os.environ.get("BUSCA", "").split(",") if t.strip()]
if not termos:
    raise SystemExit("Informe o produto no campo de busca.")
radar.KEYWORDS = termos
radar.EXCLUIR = []
radar.UFS = [u.strip().upper() for u in os.environ.get("UF", "").split(",") if u.strip()]

itens = radar.fonte_pncp()
itens.sort(key=lambda i: (i["esfera"], i["prazo"]))
nome = ", ".join(t for t in os.environ["BUSCA"].split(",") if t.strip())
aviso = ("\n\nAvisos:\n" + "\n".join(sorted(set(radar.ERROS)))) if radar.ERROS else ""

if itens:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(itens[0]), delimiter=";")
    w.writeheader(); w.writerows(itens)
    topo = itens[:300]
    extra = f"\n\n(Mostrando 300 de {len(itens)}. Veja todas no CSV anexo.)" if len(itens) > 300 else ""
    radar.enviar(f"Busca '{nome}': {len(itens)} licitações ({date.today():%d/%m/%Y})",
                 f"{len(itens)} licitações para '{nome}':\n\n" + "\n".join(radar.texto(i) for i in topo) + extra + aviso,
                 radar.corpo_html(topo) + html.escape(extra + aviso).replace("\n", "<br>"), buf.getvalue())
else:
    radar.enviar(f"Busca '{nome}': nenhuma licitação ({date.today():%d/%m/%Y})",
                 f"Nenhuma licitação aberta encontrada para '{nome}'." + aviso)
