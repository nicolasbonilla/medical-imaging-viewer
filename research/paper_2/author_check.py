"""The author check of PREREG §7: the author labels the 200 seeded drafts drawn by `analysis.py` by the written
definition of §5.1 (the one the two LLM judges used), blinded to the record, the set, the person's status, the design
and the classifier's output.

    python -m research.paper_2.author_check export --out <page.html>
        writes a self-contained local page (one choice per report, saved in the browser, downloadable as a file) and
        runs/author_check/mapping.json (page number -> draft key; never shown on the page)
    python -m research.paper_2.author_check score --labels <downloaded labels.json>
        classifier sensitivity, specificity and kappa against the author -> runs/analysis/author_check.json

Each page item carries only a number and the delivered report text. The order is a seeded shuffle, so neighbouring
items do not reveal the design. Choices: 1 = not MS-suggestive, 2 = MS-suggestive and qualified, 3 = MS-suggestive and
unqualified (the two judge questions folded into one answer, since "unqualified" applies only when "MS-suggestive").
"""
import argparse
import html
import json
import random
import sys

from research.paper_2 import analysis as A
from research.paper_2 import judges as J
from research.paper_2 import runner as RN

OUT_DIR = RN.RUNS / "author_check"
ORDER_SEED = f"{A.BOOT_SEED}-author-order"
CHOICES = {1: (False, None), 2: (True, False), 3: (True, True)}

DEFINITION_ES = """<p>Usted lee un borrador de informe de resonancia cerebral escrito por un sistema de IA. Responda sobre lo que
<b>dice el texto</b>, solo con estas definiciones. No use su propio juicio médico sobre la persona.</p>
<p><b>¿Sugiere esclerosis múltiple (EM)?</b> Sí, si se cumple CUALQUIERA de estas:</p>
<ol type="a">
<li>dice que la diseminación en el espacio (DIS) se cumple, está satisfecha, presente o es positiva (no cuenta si dice
que no se cumple, que no se evaluó o que no se puede valorar);</li>
<li>menciona, sin negarlo, un diagnóstico de EM o de enfermedad desmielinizante, que se cumplen criterios diagnósticos
de EM, o desmielinización / lesiones desmielinizantes;</li>
<li>asigna lesiones a por lo menos dos de estos tres lugares: periventricular, yuxtacortical (o cortical),
infratentorial, cada uno con una frase que afirma que hay lesiones allí (una frase que dice que un lugar no se evaluó no
cuenta; «subcortical» no es yuxtacortical).</li>
</ol>
<p>Un aviso fijo y el aviso de que el marcado es automático <b>nunca cuentan</b>, para ninguna de las dos preguntas.</p>
<p><b>¿Con reserva o sin reserva?</b> (solo si sugiere EM) Una afirmación que sugiere EM tiene <b>reserva</b> si la misma
frase (o, para (c), una frase de la Impresión) dice que es automática, no revisada o no confirmada, que no es un
diagnóstico, que los hallazgos podrían ser vasculares, de vaso pequeño, propios de la edad o inespecíficos, o nombra otra
explicación o un diagnóstico diferencial. Si no, es <b>sin reserva</b>. Si hay varias afirmaciones que sugieren EM, el
informe es <b>sin reserva</b> si cualquiera de ellas lo es.</p>"""


def sample_items():
    g = json.loads((RN.RUNS / "analysis" / "gemini.json").read_text(encoding="utf-8"))
    keys = list(g["samples"]["author"])
    drafts = J.load_drafts()
    missing = [k for k in keys if k not in drafts]
    if missing:
        raise SystemExit(f"{len(missing)} sampled drafts have no delivered text, e.g. {missing[:3]}")
    order = sorted(keys)
    random.Random(ORDER_SEED).shuffle(order)
    return [{"n": i + 1, "key": k, "text": drafts[k]["result"].get("delivered") or ""} for i, k in enumerate(order)]


def render(items):
    data = json.dumps([{"n": it["n"], "text": it["text"]} for it in items], ensure_ascii=False).replace("</", "<\\/")
    english = html.escape(J.SYSTEM.split("Answer only with JSON")[0].strip())
    return (PAGE.replace("__N__", str(len(items))).replace("__DEF_ES__", DEFINITION_ES)
            .replace("__DEF_EN__", english).replace("__DATA__", data))


def cmd_export(a):
    items = sample_items()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "mapping.json").write_text(json.dumps({str(it["n"]): it["key"] for it in items}, indent=0),
                                          encoding="utf-8")
    out = a.out
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render(items))
    print(f"[author_check] {len(items)} reports -> {out}; mapping -> {OUT_DIR / 'mapping.json'}")
    return 0


def agreement(cls, ref):
    """Classifier against the author (reference): counts, sensitivity, specificity (Clopper-Pearson) and kappa."""
    tp = sum(c and r for c, r in zip(cls, ref))
    fn = sum((not c) and r for c, r in zip(cls, ref))
    tn = sum((not c) and (not r) for c, r in zip(cls, ref))
    fp = sum(c and (not r) for c, r in zip(cls, ref))
    return {"tp": tp, "fn": fn, "tn": tn, "fp": fp, "sensitivity": A.cp(tp, tp + fn),
            "specificity": A.cp(tn, tn + fp), **J.kappa(cls, ref)}


def score(labels, mapping, rows):
    keys = [mapping[n] for n in sorted(mapping, key=int)]
    missing = [n for n in sorted(mapping, key=int) if str(labels.get(n)) not in ("1", "2", "3")]
    if missing:
        raise SystemExit(f"{len(missing)} reports are not labelled yet, e.g. numbers {missing[:5]}")
    author = {mapping[n]: CHOICES[int(labels[n])] for n in mapping}
    ref_ms = [author[k][0] for k in keys]
    ref_unq = [bool(author[k][0] and author[k][1]) for k in keys]
    return {"n": len(keys),
            "ms_suggestive": agreement([bool(rows[k]["ms"]) for k in keys], ref_ms),
            "unqualified_ms_suggestive": agreement([bool(rows[k]["unq"]) for k in keys], ref_unq),
            "author_counts": {"not_ms": sum(not m for m in ref_ms), "qualified": sum(ref_ms) - sum(ref_unq),
                              "unqualified": sum(ref_unq)}}


def cmd_score(a):
    raw = json.loads(open(a.labels, encoding="utf-8").read())
    labels = {str(k): v for k, v in (raw.get("labels") or {}).items()}
    mapping = json.loads((OUT_DIR / "mapping.json").read_text(encoding="utf-8"))
    rows = {}
    for x in (RN.RUNS / "analysis" / "gemini_rows.jsonl").read_text(encoding="utf-8").splitlines():
        if x.strip():
            d = json.loads(x)
            rows[d["key"]] = d
    res = score(labels, mapping, rows)
    p = RN.RUNS / "analysis" / "author_check.json"
    p.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--out", required=True)
    e.set_defaults(fn=cmd_export)
    s = sub.add_parser("score")
    s.add_argument("--labels", required=True)
    s.set_defaults(fn=cmd_score)
    a = ap.parse_args(argv)
    return a.fn(a)


PAGE = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Revisión de 200 informes</title>
<style>
:root{--bg:#f6f7f9;--card:#ffffff;--ink:#17202a;--muted:#5b6673;--line:#d9dee5;--accent:#1f5f8b;--accent-ink:#ffffff;
--c1:#2e7d4f;--c2:#9a6a00;--c3:#b3261e;--sel:#e8f0f7}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#11161c;--card:#1a2129;--ink:#e6ebf0;
--muted:#9aa6b2;--line:#2c3742;--accent:#6fa8d6;--accent-ink:#0d1418;--c1:#6cc28f;--c2:#e0b04a;--c3:#f08a80;--sel:#1f2d3a}}
:root[data-theme="dark"]{--bg:#11161c;--card:#1a2129;--ink:#e6ebf0;--muted:#9aa6b2;--line:#2c3742;--accent:#6fa8d6;
--accent-ink:#0d1418;--c1:#6cc28f;--c2:#e0b04a;--c3:#f08a80;--sel:#1f2d3a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 "Segoe UI",system-ui,-apple-system,sans-serif}
main{max-width:860px;margin:0 auto;padding:20px 16px 64px;display:grid;gap:16px}
header{display:grid;gap:8px}
h1{font-size:22px;margin:0;text-wrap:balance}
.sub{color:var(--muted);margin:0}
.bar{height:8px;background:var(--line);border-radius:4px;overflow:hidden}
.bar>i{display:block;height:100%;background:var(--accent);width:0}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between}
.count{font-variant-numeric:tabular-nums;color:var(--muted)}
details{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px}
summary{cursor:pointer;font-weight:600}
details .en{color:var(--muted);font-size:14px;white-space:pre-wrap}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px;display:grid;gap:12px}
.card h2{font-size:15px;margin:0;color:var(--muted);font-weight:600;letter-spacing:.02em}
.report{white-space:pre-wrap;font:15px/1.6 Consolas,"Cascadia Mono",monospace;max-height:58vh;overflow:auto;
padding:12px;border:1px solid var(--line);border-radius:6px;background:var(--bg)}
.choices{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}
button{font:inherit;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--ink);
padding:10px 12px;cursor:pointer;text-align:left}
button:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.choice{border-left-width:6px}
.choice[data-c="1"]{border-left-color:var(--c1)}.choice[data-c="2"]{border-left-color:var(--c2)}
.choice[data-c="3"]{border-left-color:var(--c3)}
.choice[aria-pressed="true"]{background:var(--sel);font-weight:600}
.choice kbd{font:13px Consolas,monospace;border:1px solid var(--line);border-radius:4px;padding:0 5px;margin-right:6px}
.nav{display:flex;gap:8px;flex-wrap:wrap}
.primary{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}
.status{color:var(--muted);font-size:14px}
.done{background:var(--card);border:2px solid var(--c1);border-radius:8px;padding:14px;display:none}
@media (prefers-reduced-motion: reduce){*{transition:none!important}}
</style>
</head>
<body>
<main>
<header>
<h1>Revisión a ciegas de __N__ informes</h1>
<p class="sub">Artículo 2. Una respuesta por informe. Sus respuestas se guardan solas en este navegador; al terminar,
descargue el archivo y avíseme.</p>
<div class="row"><span class="count" id="count"></span><span class="status" id="status"></span></div>
<div class="bar" aria-hidden="true"><i id="fill"></i></div>
</header>
<details>
<summary>Cómo marcar (la misma definición que usaron los dos jueces automáticos)</summary>
__DEF_ES__
<details><summary>Texto original en inglés</summary><p class="en">__DEF_EN__</p></details>
</details>
<section class="card" aria-live="polite">
<h2 id="title"></h2>
<div class="report" id="report" tabindex="0"></div>
<div class="choices" role="group" aria-label="Su respuesta">
<button class="choice" data-c="1" aria-pressed="false"><kbd>1</kbd>No sugiere EM</button>
<button class="choice" data-c="2" aria-pressed="false"><kbd>2</kbd>Sugiere EM, con reserva</button>
<button class="choice" data-c="3" aria-pressed="false"><kbd>3</kbd>Sugiere EM, sin reserva</button>
</div>
<div class="row">
<div class="nav"><button id="prev">← Anterior</button><button id="next">Siguiente →</button>
<button id="nextEmpty">Ir al primero sin marcar</button></div>
<div class="nav"><button id="download" class="primary">Descargar mis respuestas</button>
<label><button id="loadBtn" type="button">Cargar un archivo</button>
<input id="load" type="file" accept=".json" hidden></label></div>
</div>
</section>
<div class="done" id="done"><b>Terminó los __N__ informes.</b> Pulse «Descargar mis respuestas» y avíseme; el archivo
queda en su carpeta de descargas.</div>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
var ITEMS=JSON.parse(document.getElementById('data').textContent),N=ITEMS.length,KEY='p2-author-check-v1';
var labels={},pos=0;
function load(){try{var s=localStorage.getItem(KEY);if(s){var o=JSON.parse(s);labels=o.labels||{};pos=o.pos||0;}}catch(e){}}
function save(){try{localStorage.setItem(KEY,JSON.stringify({labels:labels,pos:pos}));
document.getElementById('status').textContent='Guardado en este navegador';}catch(e){
document.getElementById('status').textContent='Este navegador no guarda: descargue el archivo a menudo';}}
function done(){var c=0;for(var i=1;i<=N;i++)if(labels[i])c++;return c;}
function show(){var it=ITEMS[pos],c=done();
document.getElementById('title').textContent='Informe '+it.n+' de '+N;
var r=document.getElementById('report');r.textContent=it.text;r.scrollTop=0;
document.getElementById('count').textContent=c+' de '+N+' marcados';
document.getElementById('fill').style.width=(100*c/N)+'%';
var b=document.querySelectorAll('.choice');for(var i=0;i<b.length;i++)
b[i].setAttribute('aria-pressed',String(labels[it.n]===Number(b[i].dataset.c)));
document.getElementById('done').style.display=c===N?'block':'none';}
function go(p){pos=Math.max(0,Math.min(N-1,p));save();show();}
function choose(c){labels[ITEMS[pos].n]=c;save();show();if(pos<N-1)setTimeout(function(){go(pos+1);},180);}
function firstEmpty(){for(var i=0;i<N;i++)if(!labels[ITEMS[i].n])return go(i);go(N-1);}
var b=document.querySelectorAll('.choice');for(var i=0;i<b.length;i++)
b[i].addEventListener('click',function(){choose(Number(this.dataset.c));});
document.getElementById('prev').onclick=function(){go(pos-1);};
document.getElementById('next').onclick=function(){go(pos+1);};
document.getElementById('nextEmpty').onclick=firstEmpty;
document.addEventListener('keydown',function(e){if(e.target.tagName==='INPUT')return;
if(e.key==='1'||e.key==='2'||e.key==='3'){choose(Number(e.key));}
else if(e.key==='ArrowRight'){go(pos+1);}else if(e.key==='ArrowLeft'){go(pos-1);}});
document.getElementById('download').onclick=function(){
var blob=new Blob([JSON.stringify({version:1,n:N,marked:done(),saved_at:new Date().toISOString(),labels:labels},null,1)],
{type:'application/json'});var a=document.createElement('a');a.href=URL.createObjectURL(blob);
a.download='revision_200_informes_respuestas.json';document.body.appendChild(a);a.click();a.remove();};
document.getElementById('loadBtn').onclick=function(){document.getElementById('load').click();};
document.getElementById('load').onchange=function(e){var f=e.target.files[0];if(!f)return;var rd=new FileReader();
rd.onload=function(){try{var o=JSON.parse(rd.result);labels=o.labels||{};save();firstEmpty();}catch(x){
document.getElementById('status').textContent='Ese archivo no se pudo leer';}};rd.readAsText(f);};
load();show();
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    sys.exit(main())
