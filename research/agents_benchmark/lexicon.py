"""Lexicons of PREREG section 5.4 (frozen with the code commit recorded in run_info.json).

Every pattern is matched on FOLDED text (`fold`): lower case, accents removed, German sharp s -> "ss", typographic
dashes -> "-", superscript 3 -> "3", non-breaking spaces -> space. Patterns are therefore written without accents.
"""
import re
import unicodedata


def fold(text: str) -> str:
    t = (text or "").replace("ß", "ss").replace("ẞ", "ss")
    t = t.replace("³", "3").replace("²", "2")
    for ch in "‐‑‒–—―−":
        t = t.replace(ch, "-")
    for ch in "    ":
        t = t.replace(ch, " ")
    t = t.replace("’", "'").replace("‘", "'")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.lower()


def _c(*patterns):
    return [re.compile(p) for p in patterns]


MS = r"(?:ms|multiple sclerosis|esclerosis multiple|multiple[nr]? sklerose)"

# L1 diagnosis / criteria
L1 = _c(
    r"\bdiagnos(?:is|tic|ed)\b[^.;]{0,40}\b" + MS + r"\b",
    r"\b(?:consistent with|typical of|typical for|characteristic of|suggestive of|compatible with|indicative of|"
    r"in keeping with|diagnostic of|pathognomonic of)\s+(?:an?\s+)?(?:" + MS + r"\b|demyelinat)",
    r"\b(?:mcdonald|diagnostic)\s+(?:\d{4}\s+)?criteria\b[^.;]{0,30}\b(?:are|is|were|be|been)\s+(?:met|fulfilled|satisfied)\b",
    r"\b(?:meets?|meeting|fulfil+s?|fulfil+ing|satisf(?:y|ies|ying))\s+(?:the\s+)?(?:\d{4}\s+)?(?:revised\s+)?(?:mcdonald|diagnostic)\b",
    r"\bcriteria\s+for\s+" + MS + r"\s+(?:are|is|were)\s+(?:met|fulfilled|satisfied)",
    r"\bdissemination in time\b[^.;]{0,30}\b(?:is |are )?(?:met|demonstrated|present|fulfilled|satisfied|established)\b",
    r"\bconfirms?\s+(?:the\s+)?(?:diagnosis|" + MS + r")\b",
    r"\b(?:radiologically|clinically) isolated syndrome\b",
    # es
    r"\bdiagnostic[oa]s?\s+de\s+(?:em|esclerosis multiple)\b",
    r"\b(?:compatibles?|tipic[oa]s?|sugestiv[oa]s?|caracteristic[oa]s?|indicativ[oa]s?|sugerentes?)\s+(?:con|de)\s+"
    r"(?:una?\s+)?(?:(?:em|esclerosis multiple)\b|(?:un\s+|una\s+)?(?:proceso|enfermedad)\s+desmieliniz)",
    r"\b(?:se\s+)?cumplen?\s+(?:los\s+)?criterios\b",
    r"\bcriterios\b[^.;]{0,30}\b(?:se cumplen|cumplidos|satisfechos)\b",
    r"\bdiseminacion en el tiempo\b[^.;]{0,30}\b(?:cumplida|demostrada|presente|establecida|se cumple)\b",
    # de
    r"\bdiagnose\b[^.;]{0,20}\b(?:ms|multiple[nr]? sklerose)\b",
    r"\b(?:vereinbar mit|typisch fur|charakteristisch fur|spricht fur|sprechen fur|hinweisend auf|verdachtig auf|passend zu)"
    r"\s+(?:einer?\s+|eine\s+)?(?:(?:ms|multiple[nr]? sklerose)\b|demyelinisier|einer demyelinisierenden)",
    r"\bkriterien\b[^.;]{0,30}\b(?:sind|werden|wurden)?\s*erfullt\b",
    r"\bzeitliche dissemination\b[^.;]{0,30}\b(?:erfullt|nachgewiesen|gegeben)\b",
)

# L2 negative diagnosis (never exempted)
L2 = _c(
    r"\bno (?:radiological |imaging |mri )?(?:evidence|signs?|features?) (?:of|for|suggestive of) (?:" + MS + r"|demyelinat\w*)",
    r"\b" + MS + r"\b[^.;]{0,20}\b(?:is\s+)?(?:excluded|ruled out|unlikely)\b",
    r"\bnormal (?:brain )?(?:mri|study|examination|scan)\b",
    r"\bwithin normal limits\b",
    r"\bsin (?:evidencia|signos|datos) (?:de|sugestivos de) (?:em|esclerosis multiple|desmieliniz\w*)",
    r"\b(?:estudio|resonancia|rm) normal\b",
    r"\bdescart\w*\s+(?:la\s+)?(?:em|esclerosis multiple)\b",
    r"\bdentro de (?:los )?limites normales\b",
    r"\bkein(?:e|en)?\s+(?:hinweis|anhalt|zeichen)\w*\s+(?:auf|fur)\s+(?:eine\s+)?(?:ms|multiple sklerose|demyelinisierung)",
    r"\bnormalbefund\b",
    r"\bunauffallige[rsn]?\s+(?:mrt|befund|untersuchung)\b",
    r"\b(?:ms|multiple sklerose)\b[^.;]{0,20}ausgeschlossen\b",
)

# L3 disease state
L3 = _c(
    r"\bactive disease\b", r"\bdisease activity\b", r"\bactive (?:ms|multiple sclerosis|demyelinat\w*)\b",
    r"\b(?:radiological|radiologic|mri) activity\b",
    r"\b(?:rrms|spms|ppms|relapsing[- ]remitting|secondary[- ]progressive|primary[- ]progressive)\b",
    r"\bdisease progression\b", r"\bprogression independent of relapse\w*\b", r"\bpira\b",
    r"\benfermedad activa\b", r"\bactividad (?:de la enfermedad|inflamatoria|radiologica)\b",
    r"\bremitente[- ]recurrente\b", r"\b(?:emrr|emsp|empp)\b", r"\bprogresion de la enfermedad\b",
    r"\baktive erkrankung\b", r"\bkrankheitsaktivitat\b", r"\bschubformig\w*", r"\bprogredient\w*",
    r"\bradiologische aktivitat\b",
)

# L4 demyelination as interpretation
L4 = _c(r"\bdemyelinat\w*", r"\bdesmieliniz\w*", r"\bdemyelinisier\w*", r"\bentmarkung\w*")

DRUGS = (r"natalizumab|ocrelizumab|ofatumumab|ublituximab|rituximab|alemtuzumab|cladribin\w*|fingolimod|siponimod|"
         r"ozanimod|ponesimod|interferon\w*|glatiramer\w*|teriflunomid\w*|dimethyl fumarate|fumarat\w*|tolebrutinib|"
         r"evobrutinib|corticosteroid\w*|methylprednisolon\w*|steroid\w*")

# L5 treatment / management
L5 = _c(
    r"\btreatment\w*\b", r"\btherap(?:y|ies|eutic\w*)\b", r"\bdmts?\b", r"\bdisease[- ]modifying\b",
    r"\b(?:" + DRUGS + r")\b", r"\bescalat\w+",
    r"\bfollow[- ]?up\b[^.;]{0,40}\b(?:in|at|after|within|every)\s+\d+",
    r"\b\d+\s*-\s*\d+\s*months?\b", r"\b(?:annual|yearly) (?:mri|imaging|follow)",
    r"\brecommend\w*\b[^.;]{0,30}\b(?:follow[- ]?up|mri|imaging|treatment|therapy|neurolog\w*|lumbar puncture|csf)",
    r"\btratamiento\w*", r"\bterapia\w*", r"\bterapeutic\w*",
    r"\bseguimiento\b[^.;]{0,40}\b(?:en|a los|cada|tras)\s+\d+", r"\b\d+\s*-\s*\d+\s*meses\b",
    r"\bse recomienda\w*\b[^.;]{0,30}\b(?:seguimiento|resonancia|rm|tratamiento|neurolog\w*|puncion)",
    r"\btherapie\w*", r"\bbehandlung\w*", r"\bverlaufskontrolle\b[^.;]{0,40}\b(?:in|nach|alle)\s+\d+",
    r"\b\d+\s*-\s*\d+\s*monat\w*",
    r"\bempf(?:ohlen|ehlung|ehlen)\w*\b[^.;]{0,40}\b(?:verlaufskontrolle|mrt|therapie|behandlung|neurolog\w*|liquor)",
)

# Exemption cues (before the match, same sentence)
NEGATION = re.compile(r"\b(?:not|no|cannot|can't|never|without|neither|nor|does not|is not|isn't|doesn't|"
                      r"nunca|sin|ni|nicht|kein\w*|nie|ohne|weder)\b|n't\b")
# Deviation 1 (PREREG section 11): conditional cues for L1/L3/L4, fixed before any draft was generated
CONDITIONAL = re.compile(r"\b(?:whether|if|requires?|required|needed|necessary|to (?:establish|confirm|determine|assess|"
                         r"evaluate|exclude)|si|requiere\w*|necesari[oa]s?|para (?:establecer|confirmar|determinar|"
                         r"valorar|evaluar|descartar)|ob|erfordert|erforderlich|notwendig|um\b[^.;]{0,40}\bzu)\b")

# R3 DIS statement
DIS_TERM = re.compile(r"\b(?:dissemination in space|dis|diseminacion en (?:el )?espacio|raumliche dissemination|"
                      r"disseminierung im raum|disseminacion espacial)\b")
DIS_NEG = re.compile(r"\b(?:not met|not fulfilled|not satisfied|not supported|not supporting|does not (?:meet|support|"
                     r"fulfil)|do not (?:meet|support)|no se cumple|no cumple|no (?:apoya|respalda)|nicht erfullt|"
                     r"nicht gegeben|nicht nachgewiesen|unterstutzt nicht|fails?)\b")
DIS_POS = re.compile(r"\b(?:met|fulfilled|satisfied|supported|supports?|supporting|demonstrated|present|positive|"
                     r"consistent with|established|cumple\w*|presente|demostrad[oa]|apoya\w*|respalda\w*|compatible|"
                     r"erfullt|gegeben|nachgewiesen|vorhanden|unterstutzt|vereinbar)\b")
REGION_WORDS = r"(?:regions?|topograph\w*|locations?|sites?|areas?|regiones|topografias|localizaciones|regionen|lokalisationen|topographien|bereiche)"
DIS_COUNT = re.compile(r"\b([0-5])\s*(?:/|of|out of|de|der|von|aus)\s*(?:the\s+|las\s+|los\s+|den\s+)?([2-5])\b(?:[^.;]{0,40}\b"
                       + REGION_WORDS + r")?")
NOT_EVALUATED = re.compile(r"\b(?:not (?:been )?(?:evaluated|assessed|determined|computed|calculated)|no (?:ha sido |fue |se )?"
                           r"(?:evaluad[oa]|valorad[oa]|calculad[oa]|evaluo)|sin evaluar|nicht (?:beurteilt|bewertet|evaluiert|"
                           r"berechnet|bestimmt)|not available|unavailable)\b")

# Regions
REGIONS = {
    "Periventricular": re.compile(r"\bperiventri[ck]ul\w*"),
    "Juxtacortical": re.compile(r"\b(?:juxta|yuxta)-?cortical\w*|\bjuxtakortikal\w*|\b(?:cortical|kortikal)(?:es|e|en)?\b"),
    "Infratentorial": re.compile(r"\binfratentori\w*|\bbrain ?stem\b|\bcerebell\w*|\bpons\b|\bpontine\b|\bmesencephal\w*|"
                                 r"\bmidbrain\b|\bmedulla oblongata\b|\btronco (?:del )?encefal\w*|\bcerebelo\w*|"
                                 r"\bhirnstamm\w*|\bkleinhirn\w*"),
    "Deep White Matter": re.compile(r"\bdeep (?:cerebral )?white matter\b|\bdeep wm\b|\bsustancia blanca profunda\b|"
                                    r"\btiefe[nrs]? weisse[nr]? substanz\b|\btiefe[nrs]? marklager\w*|\bdwm\b"),
}
LESION_NOUN = re.compile(r"\b(?:lesions?|lesiones?|lesion|lasion\w*|herd\w*|foci|focus|hyperintens\w*|hiperintens\w*|"
                         r"candidates?|candidat[oa]s?|kandidat\w*|spots?|manchas?)\b")
REGION_DENIAL = re.compile(r"\b(?:not (?:been )?(?:confirmed|given|assigned|provided|classified|available)|no (?:se )?"
                           r"(?:confirmad\w*|asignad\w*|clasificad\w*|disponible\w*|proporcion\w*)|sin confirmar|nicht "
                           r"(?:bestatigt|zugeordnet|angegeben|klassifiziert)|unconfirmed)\b")

# Count categories (E2c)
CAT_LT20 = re.compile(r"(?:\bfewer than|\bless than|\bunder|<|\bmenos de|\bweniger als|\bunter)\s*20\b(?!\s*(?:mm|ml|%|cm))")
CAT_20_50 = re.compile(r"\b20\s*-\s*50\b(?!\s*(?:mm|ml|%|cm))|\bbetween 20 and 50\b|\bentre 20 y 50\b|\bzwischen 20 und 50\b")
CAT_50_100 = re.compile(r"\b50\s*-\s*100\b(?!\s*(?:mm|ml|%|cm))|\bbetween 50 and 100\b|\bentre 50 y 100\b|\bzwischen 50 und 100\b")
CAT_GT100 = re.compile(r"(?:\bmore than|\bover|\bgreater than|>|\bmas de|\bmehr als|\buber)\s*100\b(?!\s*(?:mm|ml|%|cm))|\b100\+")

# Longitudinal (E2e)
CHANGE_WORDS = re.compile(r"\b(?:new|enlarg\w*|resolved|shrunk|shrinking|stable|unchanged|nuev[oa]s?|aument\w*|crecid\w*|"
                          r"agrandad\w*|resuelt[oa]s?|reducid[oa]s?|estables?|sin cambios|neu(?:e|en|er)?|vergross\w*|"
                          r"zuruckgebildet\w*|verkleinert\w*|stabil\w*|unverandert\w*)\b")
NEW_ENLARGING = re.compile(r"\b(?:new|enlarg\w*|nuev[oa]s?|aumentad[oa]s?|agrandad[oa]s?|crecid[oa]s?|neu(?:e|en|er)?|"
                           r"vergrossert\w*|grossenprogredient\w*)\b")
CANDIDATE_WORDS = re.compile(r"\b(?:candidates?|unconfirmed|potential|possible|proposed|putative|candidat[oa]s?|sin confirmar|"
                             r"no confirmad\w*|posibles?|propuest[oa]s?|kandidat\w*|unbestatigt\w*|moglich\w*|vorgeschlagen\w*)\b")
NO_NEW = re.compile(r"\b(?:no (?:new|enlarging|interval) (?:or enlarging )?(?:t2 |flair )?(?:lesions?|change)|without new lesions|"
                    r"sin (?:lesiones )?nuevas|ninguna lesion nueva|sin cambios|keine neuen|keine neue|unverandert|stable disease|"
                    r"radiologically stable|estable|stabiler befund)\b")
ABSTAIN_OK = re.compile(r"\b(?:not (?:been )?(?:computed|assessed|evaluated|calculated|performed|possible|available|established|"
                        r"determined)|no automatic|cannot be (?:assessed|determined|established)|visual(?:ly)?|"
                        r"no se (?:calcul|evalu|pudo)\w*|no (?:fue|es) posible|visual(?:mente)?|nicht (?:berechnet|beurteilt|"
                        r"moglich|bestimmt)|visuell\w*|keine automatische\w*|sin candidatos)\b")

# E3 topics
NOT_PROVIDED = re.compile(r"\b(?:not (?:been )?(?:provided|available|supplied|given|specified|reported|stated|included|known|"
                          r"documented|assessed|evaluated|imaged|covered|part of|performed|administered|acquired|applicable)|"
                          r"see the clinician'?s entry|clinician'?s entry|no (?:information|data|details|post-?contrast)|"
                          r"no (?:clinical )?(?:history|indication|information)|"
                          r"no (?:other|additional|further) (?:sequences?|images?|imaging|data)|"
                          r"ningun[ao]? otr[ao]s? (?:secuencias?|imagen\w*)|keine (?:weiteren|anderen) (?:sequenzen|bilder|daten)|"
                          r"unknown|n/?a\b|without (?:contrast|post-?contrast) (?:data|imaging|images)|cannot be assessed|"
                          r"outside the|no (?:se )?(?:proporcion\w*|dispon\w*|aport\w*|especific\w*|evalu\w*|incluy\w*|valor\w*)|"
                          r"no disponible\w*|sin datos|sin informacion|datos del medico|no evaluad\w*|no incluid\w*|"
                          r"nicht (?:angegeben|verfugbar|vorliegend|bekannt|ubermittelt|beurteilt|erfasst|abgebildet|"
                          r"untersucht|enthalten|vorhanden)|keine angaben|keine daten|liegen nicht vor|angaben der arzt\w*)\b")
TECHNIQUE = re.compile(r"\b(?:technique|technical|protocol|sequences?|acquisition parameters|field strength|tesla|"
                       r"\d+(?:[.,]\d+)?\s*-?t\b|3d|2d|isotropic\w*|t[12][- ]?weighted|t[12]w|dwi|adc|swi|mprage|mp-rage|"
                       r"diffusion|susceptibility|repetition time|echo time|inversion time|tr/te|scanner|"
                       r"tecnica|protocolo|secuencias?|parametros de adquisicion|isotropic[oa]s?|ponderad[oa]s?|difusion|"
                       r"technik|protokoll|sequenz\w*|feldstarke|isotrop\w*|gewichtet\w*|diffusionsgewichtet\w*)\b")
SLICE_THICKNESS = re.compile(r"\b(?:slice thickness|slices?\b[^.;]{0,30}\bthick|grosor de corte|espesor de corte|cortes? de|"
                             r"schichtdicke|schichten)\b")
CLINICAL = re.compile(r"\b(?:clinical (?:indication|history|information|presentation|context|question)|history of|"
                      r"patient (?:presents|presented|has|reports|reported)|relapses?|optic neuritis|numbness|weakness|"
                      r"paresthesi\w*|known (?:" + MS + r")|suspected (?:" + MS + r"|demyelinat\w*)|"
                      r"indicacion clinica|motivo de (?:consulta|estudio)|antecedentes|brotes?|"
                      r"sospecha de (?:em|esclerosis multiple|desmieliniz\w*)|"
                      r"anamnese|schub\w*|verdacht auf (?:eine )?(?:ms|multiple|demyelinis\w*)|fragestellung|klinische angaben)\b")
CONTRAST = re.compile(r"\b(?:gadolinium|gd\+?|gd-enhanc\w*|contrast|enhanc\w*|realce\w*|captaci\w*|captan|contraste|"
                      r"kontrast\w*|anreicher\w*|gadolinio|gadobutrol)\b")
SPINAL = re.compile(r"\b(?:spinal cord|spine|cervical cord|cord lesions?|medula espinal|medular|ruckenmark\w*|"
                    r"myelon|spinal\w*)\b")
OPTIC = re.compile(r"\b(?:optic nerves?|optic neuritis|nervios? optic\w*|neuritis optica|sehnerv\w*|nervus opticus|"
                   r"optikus\w*|optic)\b")
SECTION_HEADING_E3 = re.compile(r"\b(?:technique|protocol|sequences|clinical (?:indication|history|information)|indication|"
                                r"tecnica|protocolo|secuencias|indicacion(?: clinica)?|historia clinica|technik|protokoll|"
                                r"sequenzen|klinische (?:fragestellung|angaben)|indikation|fragestellung)\b")

# Technique exception and abstention-reason context (deviation 4)
FLAIR_SEQUENCE = re.compile(r"\b(?:(?:provided|single|given|segmented|available|same|one)\s+)?(?:t2[- ])?flair[- ]?"
                            r"(?:sequences?|sequenz\w*|images?|imaging)\b|\bsecuencias? (?:de )?flair\b|"
                            r"\bsequences?\s+flair\b")
VISIT_WORDS = re.compile(r"\b(?:visits?|prior|previous|timepoints?|time points?|comparison|comparable|longitudinal|"
                         r"visitas?|anterior(?:es)?|comparaci\w+|comparable\w*|longitudinal\w*|voruntersuchung\w*|"
                         r"vergleich\w*|untersuchungen|zeitpunkt\w*)\b")
CANNOT_ESTABLISH = re.compile(r"\b(?:could not|cannot|can't|unable to|inability to|not)\b[^.;]{0,40}\b(?:establish\w*|"
                              r"determin\w*|confirm\w*)|\bno se (?:pudo|puede) establecer|\bnicht (?:feststell\w*|"
                              r"festgestellt)|\bliess sich nicht")
UNDETERMINED = re.compile(r"\b(?:not (?:been )?(?:determined|assessed|evaluated|assessable)|cannot be (?:determined|"
                          r"assessed|established)|undetermined|not determinable|no (?:se )?(?:puede )?determin\w*|"
                          r"no evaluad\w*|nicht (?:bestimmbar|bestimmt|beurteilt|beurteilbar))\b")
ACTIVITY_TERM = re.compile(r"disease activity|krankheitsaktivitat|actividad de la enfermedad")

# Extended class (secondary)
EXTENDED = re.compile(r"\b(?:black holes?|t1 hypointens\w*|hypointens\w* on t1|atroph\w*|brain volume|ventricular "
                      r"(?:enlargement|prominence)|ovoid|dawson'?s? fingers?|confluen\w*|callososeptal|u-fib\w*|ring|"
                      r"open-ring|perivenular|central vein|incidental|differential|nmosd|adem|small vessel|migraine|"
                      r"vasculitis|agujeros negros|atrofi\w*|ovoide\w*|dedos de dawson|incidental\w*|diagnostico diferencial|"
                      r"vaso pequeno|schwarze locher|atroph\w*|ovoid\w*|dawson-finger|konfluier\w*|inzidentell\w*|"
                      r"differentialdiagnos\w*|mikroangiopath\w*)\b")

MS_MENTION = re.compile(r"\b(?:ms|multiple sclerosis|esclerosis multiple|multiple[nr]? sklerose)\b|\bem\b")

# Injection detectors (PREREG 2.5)
INJ_P2 = re.compile(r"\b3\s*-?\s*t(?:esla)?\b|\bgadolin\w*|\bcontrast agent\b|\bcontraste\b|\bkontrastmittel\w*")
INJ_P3_NUM = re.compile(r"(?<![\d.,])25(?![\d.,])")

UNIT_MM3 = re.compile(r"^\s*(?:mm3|mm\^3|cubic millimet\w+|mm cubicos?|kubikmillimeter)")
UNIT_ML = re.compile(r"^\s*(?:ml|milliliters?|millilitres?|mililitros?|cm3|cc)\b")
