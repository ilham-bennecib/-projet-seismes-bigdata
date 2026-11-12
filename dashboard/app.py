# Dashboard des séismes mondiaux 2016-2025
# Il lit seulement les fichiers Parquet de la couche de service (data/serving),
# écrits par le notebook 06. Il ne lit pas HDFS et n'utilise pas Spark.
#
# Lancement : docker compose up -d dashboard   puis   http://localhost:8501

import math
import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

DOSSIER = Path(__file__).resolve().parent.parent / "data" / "serving"
MC = 4.5        # magnitude de complétude (même valeur que dans les notebooks)
DELTA_M = 0.1   # largeur d'une classe de magnitude

# ---------- Couleurs ----------
TEXTE = "#1d1d1b"
MUET = "#6b6a64"
GRILLE = "#ebe9e4"
BLEU = "#2a78d6"
BLEU_CLAIR = "#9cc1ee"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
# une couleur par classe de profondeur, les mêmes dans tout le dashboard
COULEURS_PROFONDEUR = {"superficiel": BLEU, "intermediaire": ORANGE, "profond": AQUA}
NOMS_PROFONDEUR = {"superficiel": "Superficiel (< 70 km)",
                   "intermediaire": "Intermédiaire (70-300 km)",
                   "profond": "Profond (> 300 km)"}
ORDRE_PROFONDEUR = ["superficiel", "intermediaire", "profond"]
# dégradé d'une seule couleur (clair = peu, foncé = beaucoup) pour la carte de chaleur
DEGRADE_BLEU = ["#f3f7fd", "#d6e5f8", "#a9c9f0", "#6fa3e4", "#2a78d6", "#1b5bab", "#103e7a"]
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin",
        "juil.", "août", "sept.", "oct.", "nov.", "déc."]

st.set_page_config(page_title="Sismicité mondiale 2016-2025", page_icon="🌍", layout="wide")

# ---------- Style de la page ----------
# je cache le menu de Streamlit et je crée des styles pour les titres et les cartes d'indicateurs
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stText, button, input { font-family: 'Inter', sans-serif; }
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1400px; }

.entete-sur { color: #6b6a64; font-size: 0.78rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 0.2rem; }
.entete-titre { color: #1d1d1b; font-size: 2rem; font-weight: 700; letter-spacing: -0.02em; line-height: 1.15; margin: 0; }
.entete-texte { color: #52514e; font-size: 0.98rem; margin-top: 0.4rem; max-width: 820px; }

.kpi { background: #ffffff; border: 1px solid #e6e3dc; border-radius: 12px; padding: 1rem 1.15rem; min-height: 152px; }
.kpi-label { color: #6b6a64; font-size: 0.8rem; font-weight: 500; }
.kpi-valeur { color: #1d1d1b; font-size: 1.9rem; font-weight: 700; letter-spacing: -0.02em; margin: 0.15rem 0 0.1rem 0; }
.kpi-sous { color: #6b6a64; font-size: 0.8rem; line-height: 1.35; }
.kpi-barre { height: 3px; width: 32px; border-radius: 2px; margin-bottom: 0.6rem; }

.carte-titre { color: #1d1d1b; font-size: 1.02rem; font-weight: 600; margin: 0 0 0.1rem 0; }
.carte-texte { color: #6b6a64; font-size: 0.85rem; margin: 0 0 0.6rem 0; }
.note { color: #6b6a64; font-size: 0.8rem; }

div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 12px; border-color: #e6e3dc !important; }
button[data-baseweb="tab"] { font-size: 0.95rem; }
div[data-testid="stTabs"] [data-baseweb="tab-list"] { gap: 1.2rem; }
</style>
""", unsafe_allow_html=True)

# ---------- Style commun des graphiques Plotly ----------
axe = dict(gridcolor=GRILLE, linecolor=GRILLE, zeroline=False, ticks="",
           tickfont=dict(color=MUET, size=12), title_font=dict(color=MUET, size=12))
pio.templates["maison"] = go.layout.Template(layout=dict(
    font=dict(family="Inter, sans-serif", size=13, color=TEXTE),
    paper_bgcolor="white", plot_bgcolor="white",
    colorway=[BLEU, ORANGE, AQUA],
    xaxis=axe, yaxis=axe,
    hoverlabel=dict(bgcolor="white", bordercolor=GRILLE, font=dict(color=TEXTE, family="Inter, sans-serif")),
    margin=dict(l=10, r=10, t=10, b=10),
    legend=dict(orientation="h", y=1.12, x=0, font=dict(color=MUET, size=12)),
))
pio.templates.default = "maison"
CONFIG = {"displayModeBar": False}   # je cache la barre d'outils de Plotly


def afficher(fig):
    # j'applique le fond blanc et les marges automatiques directement sur la figure
    # (sinon Streamlit remet son propre fond et coupe les libellés des axes)
    fig.update_layout(paper_bgcolor="white", plot_bgcolor="white")
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    st.plotly_chart(fig, use_container_width=True, config=CONFIG, theme=None)


# ---------- Petites fonctions d'affichage ----------
def nombre(n):
    # 74362 -> "74 362"
    return f"{int(n):,}".replace(",", " ")


def kpi(colonne, label, valeur, sous_texte, couleur=BLEU):
    colonne.markdown(f"""
    <div class="kpi">
      <div class="kpi-barre" style="background:{couleur}"></div>
      <div class="kpi-label">{label}</div>
      <div class="kpi-valeur">{valeur}</div>
      <div class="kpi-sous">{sous_texte}</div>
    </div>""", unsafe_allow_html=True)


def titre_carte(titre, texte=""):
    st.markdown(f'<p class="carte-titre">{titre}</p><p class="carte-texte">{texte}</p>', unsafe_allow_html=True)


def lieu_court(lieu):
    # "2025 Kamchatka Peninsula, Russia Earthquake" -> "Kamchatka Peninsula, Russia"
    if not isinstance(lieu, str):
        return "Lieu inconnu"
    texte = re.sub(r"^\d{4} ", "", lieu)
    return texte.replace(" Earthquake", "").strip()


def region(lieu):
    # "10 km SW of Tokyo, Japan" -> "Japan" ; "Fiji region" -> "Fiji"
    texte = lieu_court(lieu)
    if ", " in texte:
        texte = texte.split(", ")[-1]
    texte = re.sub(r"^\d+ ?km [NSEW]+ of ", "", texte)
    return texte.replace(" region", "").strip()


def classe_profondeur(p):
    # même règle que dans le notebook 05
    if p < 70:
        return "superficiel"
    elif p <= 300:
        return "intermediaire"
    else:
        return "profond"


def energie(magnitude):
    # énergie libérée en joules (relation de Gutenberg-Richter) : +1 de magnitude = environ 32 fois plus d'énergie
    return 10 ** (1.5 * magnitude + 4.8)


def valeur_b(mag):
    # estimateur d'Aki : b = log10(e) / (M moyenne - (Mc - DELTA_M / 2)), classes >= Mc seulement
    mag = mag[mag["mag_classe"] >= MC - 1e-9]
    if mag["nb_seismes"].sum() == 0:
        return None
    m_moyenne = (mag["mag_classe"] * mag["nb_seismes"]).sum() / mag["nb_seismes"].sum()
    return math.log10(math.e) / (m_moyenne - (MC - DELTA_M / 2))


# ---------- 1. Chargement des données ----------
# st.cache_data : les fichiers sont lus une seule fois, pas à chaque clic sur un filtre
@st.cache_data
def charger():
    mensuel = pd.read_parquet(DOSSIER / "gold_mensuel.parquet")
    magnitudes = pd.read_parquet(DOSSIER / "gold_magnitudes.parquet")
    profondeur = pd.read_parquet(DOSSIER / "gold_profondeur.parquet")
    carte = pd.read_parquet(DOSSIER / "gold_carte.parquet")
    qualite = pd.read_parquet(DOSSIER / "gold_qualite.parquet")
    # colonnes que je calcule une seule fois pour la carte
    carte["mois"] = carte["date"].dt.month
    carte["classe_profondeur"] = carte["profondeur"].apply(classe_profondeur)
    carte["lieu_court"] = carte["lieu"].apply(lieu_court)
    carte["region"] = carte["lieu"].apply(region)
    carte["energie"] = energie(carte["magnitude"])
    # résultats du KMeans (notebook 07) : la zone de chaque séisme + le résumé des zones
    # s'ils n'existent pas encore, l'onglet "Zones (IA)" le dit au lieu de planter
    zones = None
    if (DOSSIER / "gold_zones.parquet").exists() and (DOSSIER / "gold_carte_zones.parquet").exists():
        zones = pd.read_parquet(DOSSIER / "gold_zones.parquet")
        zones["nom"] = zones["region_principale"] + " (" + zones["zone"].astype(str) + ")"
        carte = carte.merge(pd.read_parquet(DOSSIER / "gold_carte_zones.parquet"), on="id", how="left")
    return mensuel, magnitudes, profondeur, carte, qualite, zones


mensuel, magnitudes, profondeur, carte, qualite, zones = charger()
annee_min, annee_max = int(mensuel["annee"].min()), int(mensuel["annee"].max())
nb_analyses = int(qualite.loc[qualite["etape"] == "gardees", "nb_lignes"].sum())


# ---------- 2. En-tête ----------
st.markdown(f"""
<div class="entete-sur">Catalogue USGS · {annee_min}-{annee_max}</div>
<h1 class="entete-titre">Sismicité mondiale</h1>
<div class="entete-texte">{nombre(nb_analyses)} séismes analysés sur dix ans. Où la Terre tremble-t-elle,
à quelle profondeur, et les séismes suivent-ils la loi de Gutenberg-Richter ?</div>
""", unsafe_allow_html=True)
st.write("")


# ---------- 3. Filtres (en haut, sur une ligne) ----------
with st.container(border=True):
    f1, f2, f3 = st.columns([3, 3, 2])
    annees = f1.slider("Période", annee_min, annee_max, (annee_min, annee_max))
    mag_min = f2.slider("Magnitude minimale affichée sur la carte et dans la liste", MC, 8.5, 5.5, 0.1)
    f3.markdown(f'<p class="note" style="margin-top:1.9rem">Analyses sur les séismes de magnitude ≥ {MC} '
                f'(seuil de détection fiable dans le monde).</p>', unsafe_allow_html=True)


def filtrer_annees(df):
    return df[(df["annee"] >= annees[0]) & (df["annee"] <= annees[1])]


mensuel_f = filtrer_annees(mensuel)
magnitudes_f = filtrer_annees(magnitudes)
profondeur_f = filtrer_annees(profondeur)
carte_f = filtrer_annees(carte)                       # tous les séismes >= 4.5 de la période
carte_mag = carte_f[carte_f["magnitude"] >= mag_min]  # seulement pour la carte et la liste
nb_annees = annees[1] - annees[0] + 1
b = valeur_b(magnitudes_f)


# ---------- 4. Indicateurs clés ----------
nb_forts = int(mensuel_f["nb_seismes"].sum())
plus_fort = carte_f.sort_values("magnitude", ascending=False).iloc[0]
majeurs = carte_f[carte_f["magnitude"] >= 7]
part_energie_majeurs = majeurs["energie"].sum() * 100 / carte_f["energie"].sum()
part_profonds = (carte_f["classe_profondeur"] == "profond").mean() * 100

k1, k2, k3, k4 = st.columns(4)
kpi(k1, f"Séismes de magnitude ≥ {MC}", nombre(nb_forts),
    f"environ {nb_forts / (365.25 * nb_annees):.0f} par jour en moyenne")
kpi(k2, "Plus fort séisme", f"M {plus_fort['magnitude']:.1f}",
    f"{plus_fort['lieu_court']}<br>{MOIS[plus_fort['date'].month - 1]} {plus_fort['date'].year}", ORANGE)
kpi(k3, "Séismes majeurs (M ≥ 7)", nombre(len(majeurs)),
    f"{len(majeurs) * 100 / nb_forts:.2f} % des séismes, mais {part_energie_majeurs:.0f} % de l'énergie libérée", ORANGE)
kpi(k4, "Valeur b (Gutenberg-Richter)", "-" if b is None else f"{b:.2f}",
    "pente de la loi, référence mondiale ≈ 1<br>estimateur d'Aki, Mc = 4.5", AQUA)
st.write("")


# ---------- 5. La carte du monde (toujours visible, au-dessus des onglets) ----------
with st.container(border=True):
    titre_carte("Où la Terre tremble",
                f"{nombre(len(carte_mag))} séismes de magnitude ≥ {mag_min:.1f} entre {annees[0]} et {annees[1]}. "
                "Couleur : profondeur. Taille : magnitude. On voit la ceinture de feu du Pacifique, "
                "et les séismes profonds (en vert) sous les zones de subduction.")
    fig = go.Figure()
    for classe in ORDRE_PROFONDEUR:
        # je trie par magnitude pour que les gros points soient dessinés au-dessus des petits
        df = carte_mag[carte_mag["classe_profondeur"] == classe].sort_values("magnitude")
        fig.add_trace(go.Scattergeo(
            lat=df["latitude"], lon=df["longitude"], name=NOMS_PROFONDEUR[classe], mode="markers",
            marker=dict(size=3 + (df["magnitude"] - MC) * 3.5, color=COULEURS_PROFONDEUR[classe],
                        opacity=0.8, line=dict(width=0.6, color="white")),
            customdata=df[["lieu_court", "magnitude", "profondeur"]].values,
            text=df["date"].dt.strftime("%d/%m/%Y"),
            hovertemplate="<b>%{customdata[0]}</b><br>%{text}<br>Magnitude %{customdata[1]:.1f}"
                          "<br>Profondeur %{customdata[2]:.0f} km<extra></extra>"))

    fig.update_geos(projection_type="natural earth", showframe=False, bgcolor="white",
                    showocean=True, oceancolor="#eef3f8",
                    showland=True, landcolor="#f7f6f2",
                    showcountries=True, countrycolor="#dcd9d1", countrywidth=0.5,
                    showcoastlines=True, coastlinecolor="#c9c6bd", coastlinewidth=0.6,
                    showlakes=False)
    fig.update_layout(height=660, margin=dict(l=0, r=0, t=40, b=0),
                      legend=dict(y=1.05, itemsizing="constant"))
    afficher(fig)
st.write("")


# ---------- 6. Onglets ----------
onglets = st.tabs(["Vue d'ensemble", "Géographie", "Magnitudes", "Profondeur", "Séismes majeurs",
                   "Qualité des données", "Zones (IA)"])


# ===== Onglet 1 : vue d'ensemble =====
with onglets[0]:
    with st.container(border=True):
        titre_carte("Activité sismique mois par mois",
                    f"Nombre de séismes de magnitude ≥ {MC} par mois. Les pics sont les grandes séquences de répliques, "
                    "je nomme les trois plus importants avec le séisme principal du mois.")
        evolution = mensuel_f.copy()
        evolution["mois_date"] = pd.to_datetime(dict(year=evolution["annee"], month=evolution["mois"], day=1))
        evolution = evolution.sort_values("mois_date")
        evolution["moyenne_12"] = evolution["nb_seismes"].rolling(12, min_periods=6, center=True).mean()

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=evolution["mois_date"], y=evolution["nb_seismes"], name="Séismes par mois",
            mode="lines", line=dict(color=BLEU, width=2), fill="tozeroy", fillcolor="rgba(42,120,214,0.08)",
            customdata=evolution["mag_max"],
            hovertemplate="<b>%{x|%B %Y}</b><br>%{y} séismes<br>magnitude max : %{customdata:.1f}<extra></extra>"))
        fig.add_trace(go.Scatter(
            x=evolution["mois_date"], y=evolution["moyenne_12"], name="Moyenne sur 12 mois",
            mode="lines", line=dict(color=MUET, width=1.5, dash="dot"), hoverinfo="skip"))

        # j'annote les 3 mois les plus actifs avec le plus fort séisme de ce mois
        # (dans l'ordre des dates, en alternant la hauteur pour que les étiquettes proches ne se chevauchent pas)
        pics = evolution.nlargest(3, "nb_seismes").sort_values("mois_date")
        for numero, (_, pic) in enumerate(pics.iterrows()):
            seismes_du_mois = carte_f[(carte_f["annee"] == pic["annee"]) & (carte_f["mois"] == pic["mois"])]
            principal = seismes_du_mois.sort_values("magnitude", ascending=False).iloc[0]
            fig.add_annotation(
                x=pic["mois_date"], y=pic["nb_seismes"],
                text=f"<b>{principal['lieu_court']}</b><br>M {principal['magnitude']:.1f} · {nombre(pic['nb_seismes'])} séismes",
                showarrow=True, arrowhead=0, arrowcolor=MUET,
                ax=-70 if numero % 2 == 0 else 0, ay=-34 if numero % 2 == 0 else -80,
                font=dict(size=11, color=TEXTE), bgcolor="white", bordercolor=GRILLE, borderpad=4, align="left")
        fig.update_layout(height=440, hovermode="x unified", margin=dict(l=10, r=10, t=100, b=10),
                          yaxis=dict(title="Séismes par mois", rangemode="tozero"))
        afficher(fig)

    g, d = st.columns([3, 2])
    with g:
        with st.container(border=True):
            titre_carte("Calendrier de l'activité", "Chaque case est un mois : plus elle est foncée, plus il y a eu de séismes.")
            grille = mensuel_f.pivot_table(index="annee", columns="mois", values="nb_seismes", aggfunc="sum")
            grille = grille.reindex(columns=range(1, 13))
            fig = go.Figure(go.Heatmap(
                z=grille.values, x=MOIS, y=list(grille.index),
                colorscale=[[i / (len(DEGRADE_BLEU) - 1), c] for i, c in enumerate(DEGRADE_BLEU)],
                xgap=3, ygap=3, colorbar=dict(title=dict(text="séismes", font=dict(size=11, color=MUET)),
                                              thickness=10, outlinewidth=0, tickfont=dict(color=MUET, size=11)),
                hovertemplate="<b>%{x} %{y}</b><br>%{z} séismes<extra></extra>"))
            fig.update_layout(height=360, xaxis=dict(side="top", showgrid=False),
                              yaxis=dict(autorange="reversed", showgrid=False, dtick=1))
            afficher(fig)
    with d:
        with st.container(border=True):
            titre_carte("Séismes par année", f"Magnitude ≥ {MC}, avec la moyenne de la période en pointillés.")
            par_an = mensuel_f.groupby("annee", as_index=False)["nb_seismes"].sum()
            fig = go.Figure(go.Bar(
                x=par_an["annee"], y=par_an["nb_seismes"], marker=dict(color=BLEU, cornerradius=4),
                hovertemplate="<b>%{x}</b><br>%{y} séismes<extra></extra>"))
            fig.add_hline(y=par_an["nb_seismes"].mean(), line=dict(color=MUET, width=1, dash="dot"),
                          annotation_text=f"moyenne {nombre(par_an['nb_seismes'].mean())}",
                          annotation_font=dict(size=11, color=MUET), annotation_position="top left")
            fig.update_layout(height=360, bargap=0.35, xaxis=dict(dtick=1, showgrid=False),
                              yaxis=dict(title="Séismes", rangemode="tozero"))
            afficher(fig)


# ===== Onglet 2 : géographie =====
with onglets[1]:
    g, d = st.columns([3, 2])
    with g:
        with st.container(border=True):
            titre_carte("Les régions les plus actives",
                        f"Nombre de séismes de magnitude ≥ {MC} sur la période (noms de régions donnés par l'USGS).")
            top = carte_f.groupby("region").size().nlargest(12).sort_values()
            fig = go.Figure(go.Bar(
                x=top.values, y=top.index, orientation="h", marker=dict(color=BLEU, cornerradius=4),
                text=[nombre(v) for v in top.values], textposition="outside", cliponaxis=False,
                textfont=dict(color=MUET, size=11),
                hovertemplate="<b>%{y}</b><br>%{x} séismes<extra></extra>"))
            fig.update_layout(height=430, bargap=0.3, margin=dict(l=10, r=50, t=10, b=10),
                              xaxis=dict(showgrid=False, showticklabels=False), yaxis=dict(showgrid=False))
            afficher(fig)
    with d:
        with st.container(border=True):
            titre_carte("Hémisphères", "Part des séismes de magnitude ≥ 4.5 selon la position.")
            nord = (carte_f["latitude"] >= 0).mean() * 100
            ouest = (carte_f["longitude"] < 0).mean() * 100
            pacifique = ((carte_f["longitude"] >= 120) | (carte_f["longitude"] <= -60)).mean() * 100
            for label, valeur, couleur in [("Hémisphère sud", 100 - nord, BLEU),
                                           ("Hémisphère est", 100 - ouest, BLEU),
                                           ("Zone Pacifique (long. > 120° E ou < 60° O)", pacifique, ORANGE)]:
                st.markdown(f"""
                <div style="margin:0.5rem 0 1.1rem 0">
                  <div style="display:flex;justify-content:space-between;font-size:0.88rem">
                    <span style="color:{TEXTE}">{label}</span><span style="color:{TEXTE};font-weight:600">{valeur:.0f} %</span>
                  </div>
                  <div style="background:{GRILLE};border-radius:4px;height:8px;margin-top:6px">
                    <div style="background:{couleur};width:{valeur:.1f}%;height:8px;border-radius:4px"></div>
                  </div>
                </div>""", unsafe_allow_html=True)
            st.markdown('<p class="note">La zone Pacifique est une approximation par longitude de la ceinture de feu.</p>',
                        unsafe_allow_html=True)


# ===== Onglet 3 : magnitudes =====
with onglets[2]:
    g, d = st.columns([3, 2])
    with g:
        with st.container(border=True):
            titre_carte("Loi de Gutenberg-Richter",
                        f"Axe vertical logarithmique. À droite de Mc = {MC}, les points suivent une droite : "
                        "à chaque magnitude en plus, il y a environ 10 fois moins de séismes. La pente de cette droite est la valeur b. "
                        f"À gauche de {MC}, les petits séismes manquent car ils sont mal détectés hors des États-Unis. "
                        "(32 magnitudes à -9.99 ou -5, valeurs « inconnue » de certains réseaux, sont hors du cadre.)")
            gr = magnitudes_f.groupby("mag_classe", as_index=False)["nb_seismes"].sum()
            gr = gr[gr["nb_seismes"] > 0].sort_values("mag_classe")
            gr["cumule"] = gr["nb_seismes"][::-1].cumsum()[::-1]   # nombre de séismes de magnitude >= M

            fig = go.Figure()
            fig.add_vrect(x0=-2.5, x1=MC, fillcolor="#f3f2ee", line_width=0, layer="below",
                          annotation_text="détection incomplète", annotation_position="top left",
                          annotation_font=dict(size=11, color=MUET))
            fig.add_trace(go.Scatter(
                x=gr["mag_classe"], y=gr["nb_seismes"], name="Séismes par classe de magnitude", mode="markers",
                marker=dict(color=BLEU_CLAIR, size=7, line=dict(width=1, color="white")),
                hovertemplate="Magnitude %{x:.1f}<br>%{y:,} séismes<extra></extra>"))
            fig.add_trace(go.Scatter(
                x=gr["mag_classe"], y=gr["cumule"], name="Cumulé : magnitude ≥ M", mode="markers",
                marker=dict(color=BLEU, size=8, line=dict(width=1, color="white")),
                hovertemplate="Magnitude ≥ %{x:.1f}<br>%{y:,} séismes<extra></extra>"))
            if b is not None:
                n_mc = gr.loc[gr["mag_classe"] >= MC - 1e-9, "nb_seismes"].sum()
                a = math.log10(n_mc) + b * MC
                x_droite = [MC, gr["mag_classe"].max()]
                fig.add_trace(go.Scatter(
                    x=x_droite, y=[10 ** (a - b * x) for x in x_droite], name=f"Droite de pente b = {b:.2f}",
                    mode="lines", line=dict(color=ORANGE, width=2), hoverinfo="skip"))
            fig.add_vline(x=MC, line=dict(color=MUET, width=1, dash="dash"))
            fig.update_layout(height=470, margin=dict(l=10, r=10, t=50, b=10),
                              xaxis=dict(title="Magnitude", range=[-2.5, 9.5]),
                              yaxis=dict(title="Nombre de séismes", type="log", exponentformat="power"))
            afficher(fig)

    with d:
        with st.container(border=True):
            titre_carte("La valeur b année par année",
                        "Si elle reste stable, la loi est bien vérifiée. La bande grise montre les valeurs habituelles (0.8 à 1.2).")
            b_annees = pd.DataFrame([
                {"annee": a, "b": valeur_b(magnitudes_f[magnitudes_f["annee"] == a])}
                for a in sorted(magnitudes_f["annee"].unique())])
            fig = go.Figure()
            fig.add_hrect(y0=0.8, y1=1.2, fillcolor="#f3f2ee", line_width=0, layer="below")
            fig.add_hline(y=1, line=dict(color=MUET, width=1, dash="dot"),
                          annotation_text="référence 1.0", annotation_font=dict(size=11, color=MUET),
                          annotation_position="bottom right")
            fig.add_trace(go.Scatter(
                x=b_annees["annee"], y=b_annees["b"], mode="lines+markers+text", name="valeur b",
                line=dict(color=AQUA, width=2), marker=dict(size=8, color=AQUA, line=dict(width=2, color="white")),
                text=[f"{v:.2f}" for v in b_annees["b"]], textposition="top center",
                textfont=dict(size=10, color=MUET),
                hovertemplate="<b>%{x}</b><br>b = %{y:.2f}<extra></extra>"))
            fig.update_layout(height=470, showlegend=False,
                              xaxis=dict(dtick=1, showgrid=False),
                              yaxis=dict(title="valeur b", range=[0.6, 1.6]))
            afficher(fig)

    with st.container(border=True):
        titre_carte("Quelques séismes libèrent presque toute l'énergie",
                    "Part de l'énergie totale libérée sur la période par les 10 plus forts séismes. "
                    "Un séisme de magnitude 8 libère environ 1 000 fois plus d'énergie qu'un séisme de magnitude 6.")
        top10 = carte_f.nlargest(10, "energie").copy()
        top10["part"] = top10["energie"] * 100 / carte_f["energie"].sum()
        top10["label"] = top10["lieu_court"] + " · " + top10["date"].dt.year.astype(str)
        top10 = top10.sort_values("part")
        fig = go.Figure(go.Bar(
            x=top10["part"], y=top10["label"], orientation="h", marker=dict(color=ORANGE, cornerradius=4),
            text=[f"{p:.1f} %  (M {m:.1f})" for p, m in zip(top10["part"], top10["magnitude"])],
            textposition="outside", cliponaxis=False, textfont=dict(size=11, color=MUET),
            hovertemplate="<b>%{y}</b><br>%{x:.1f} % de l'énergie<extra></extra>"))
        fig.update_layout(height=400, bargap=0.3, margin=dict(l=10, r=110, t=10, b=10),
                          xaxis=dict(showgrid=False, showticklabels=False), yaxis=dict(showgrid=False))
        afficher(fig)
        st.markdown(f'<p class="note">À eux seuls, ces 10 séismes représentent <b>{top10["part"].sum():.0f} %</b> '
                    f"de l'énergie libérée par les {nombre(len(carte_f))} séismes de magnitude ≥ {MC}.</p>",
                    unsafe_allow_html=True)


# ===== Onglet 4 : profondeur =====
with onglets[3]:
    g, d = st.columns([3, 2])
    with g:
        with st.container(border=True):
            titre_carte("À quelle profondeur ?",
                        "Nombre de séismes par tranche de 10 km (axe logarithmique). La plupart sont superficiels, "
                        "puis le nombre baisse avec la profondeur, et remonte vers 600 km : ce sont les séismes profonds "
                        "des zones de subduction (Fidji, Tonga, Bolivie...).")
            fig = go.Figure()
            for classe in ORDRE_PROFONDEUR:
                df = carte_f[carte_f["classe_profondeur"] == classe]
                fig.add_trace(go.Histogram(
                    x=df["profondeur"], name=NOMS_PROFONDEUR[classe], xbins=dict(start=-10, end=720, size=10),
                    marker=dict(color=COULEURS_PROFONDEUR[classe], line=dict(width=1, color="white")),
                    hovertemplate="%{x} km<br>%{y} séismes<extra></extra>"))
            fig.update_layout(height=430, barmode="stack", bargap=0.05, margin=dict(l=10, r=10, t=50, b=10),
                              legend=dict(traceorder="normal"),
                              xaxis=dict(title="Profondeur (km)", range=[-10, 720]),
                              yaxis=dict(title="Séismes", type="log"))
            afficher(fig)
    with d:
        with st.container(border=True):
            titre_carte("Répartition par année", "Part de chaque classe de profondeur, magnitude ≥ 4.5.")
            prof = profondeur_f.pivot_table(index="annee", columns="classe_profondeur", values="nb_seismes", aggfunc="sum").fillna(0)
            prof = prof.div(prof.sum(axis=1), axis=0) * 100
            fig = go.Figure()
            for classe in ORDRE_PROFONDEUR:
                if classe in prof.columns:
                    fig.add_trace(go.Bar(
                        x=prof.index, y=prof[classe], name=NOMS_PROFONDEUR[classe].split(" (")[0],
                        marker=dict(color=COULEURS_PROFONDEUR[classe], line=dict(width=1.5, color="white")),
                        hovertemplate="<b>%{x}</b><br>%{y:.1f} %<extra>" + NOMS_PROFONDEUR[classe] + "</extra>"))
            fig.update_layout(height=430, barmode="stack", bargap=0.3, margin=dict(l=10, r=10, t=50, b=10),
                              legend=dict(traceorder="normal"),
                              xaxis=dict(dtick=1, showgrid=False), yaxis=dict(title="% des séismes", range=[0, 100]))
            afficher(fig)

    c1, c2, c3 = st.columns(3)
    for colonne, classe in zip([c1, c2, c3], ORDRE_PROFONDEUR):
        df = carte_f[carte_f["classe_profondeur"] == classe]
        kpi(colonne, NOMS_PROFONDEUR[classe], f"{len(df) * 100 / len(carte_f):.1f} %",
            f"{nombre(len(df))} séismes · magnitude max {df['magnitude'].max():.1f}", COULEURS_PROFONDEUR[classe])


# ===== Onglet 5 : séismes majeurs =====
with onglets[4]:
    with st.container(border=True):
        titre_carte("Liste des séismes",
                    f"{nombre(len(carte_mag))} séismes de magnitude ≥ {mag_min:.1f} sur la période, du plus fort au plus faible. "
                    "On peut trier en cliquant sur une colonne et télécharger la liste.")
        liste = carte_mag.sort_values(["magnitude", "date"], ascending=[False, False])[
            ["date", "magnitude", "profondeur", "lieu_court", "region", "latitude", "longitude", "id"]]
        st.dataframe(
            liste, use_container_width=True, hide_index=True, height=520,
            column_config={
                "date": st.column_config.DatetimeColumn("Date (UTC)", format="DD/MM/YYYY HH:mm"),
                "magnitude": st.column_config.ProgressColumn("Magnitude", format="%.1f", min_value=MC, max_value=9.5),
                "profondeur": st.column_config.NumberColumn("Profondeur (km)", format="%.0f"),
                "lieu_court": "Lieu",
                "region": "Région",
                "latitude": st.column_config.NumberColumn("Latitude", format="%.2f"),
                "longitude": st.column_config.NumberColumn("Longitude", format="%.2f"),
                "id": "Identifiant USGS",
            })
        st.download_button("Télécharger la liste (CSV)", liste.to_csv(index=False).encode("utf-8"),
                           file_name=f"seismes_{annees[0]}_{annees[1]}_M{mag_min:.1f}.csv", mime="text/csv")


# ===== Onglet 6 : qualité des données =====
with onglets[5]:
    etapes = qualite.groupby("etape")["nb_lignes"].sum()
    recues = int(etapes.get("recues", 0))
    q1, q2, q3, q4 = st.columns(4)
    kpi(q1, "Lignes reçues de l'API", nombre(recues), "522 fichiers CSV hebdomadaires")
    kpi(q2, "Gardées dans silver", nombre(etapes.get("gardees", 0)),
        f"{etapes.get('gardees', 0) * 100 / recues:.2f} % des lignes reçues", AQUA)
    kpi(q3, "Hors périmètre", nombre(etapes.get("hors_perimetre", 0)),
        "explosions, tirs de carrière, glissements... (pas des séismes)", ORANGE)
    kpi(q4, "Rejetées", nombre(etapes.get("rejetees", 0)),
        f"règles de qualité · doublons : {nombre(etapes.get('doublons', 0))}", ORANGE)
    st.write("")

    g, d = st.columns([3, 2])
    with g:
        with st.container(border=True):
            titre_carte("Ce qui n'est pas gardé, et pourquoi",
                        "Lignes écartées par motif. Les événements hors périmètre ne sont pas des erreurs, "
                        "ce ne sont juste pas des séismes. Les rejets sont des séismes sans magnitude.")
            ecartes = qualite[qualite["etape"].isin(["hors_perimetre", "rejetees"])].copy()
            ecartes = ecartes.nlargest(10, "nb_lignes").sort_values("nb_lignes")
            couleurs = [ORANGE if e == "rejetees" else BLEU for e in ecartes["etape"]]
            fig = go.Figure(go.Bar(
                x=ecartes["nb_lignes"], y=ecartes["motif"], orientation="h",
                marker=dict(color=couleurs, cornerradius=4),
                text=[nombre(v) for v in ecartes["nb_lignes"]], textposition="outside", cliponaxis=False,
                textfont=dict(size=11, color=MUET),
                hovertemplate="<b>%{y}</b><br>%{x} lignes<extra></extra>"))
            fig.update_layout(height=400, bargap=0.3, margin=dict(l=10, r=60, t=10, b=10),
                              xaxis=dict(showgrid=False, showticklabels=False), yaxis=dict(showgrid=False))
            afficher(fig)
            st.markdown(f'<p class="note"><span style="color:{BLEU}">■</span> hors périmètre &nbsp;&nbsp; '
                        f'<span style="color:{ORANGE}">■</span> rejeté par une règle de qualité</p>',
                        unsafe_allow_html=True)
    with d:
        with st.container(border=True):
            titre_carte("Les règles appliquées en silver")
            st.markdown("""
            <div style="font-size:0.88rem;color:#1d1d1b;line-height:1.7">
            <b>Périmètre</b> : on garde seulement les événements de type earthquake.<br>
            <b>id_manquant</b> : identifiant vide.<br>
            <b>magnitude_manquante</b> : magnitude vide ou non numérique.<br>
            <b>coordonnees_invalides</b> : latitude hors [-90, 90] ou longitude hors [-180, 180].<br>
            <b>date_invalide</b> : date impossible à lire.<br>
            <b>Doublons</b> : même identifiant, on garde la version la plus récente.
            </div>""", unsafe_allow_html=True)
            st.write("")
            tableau = qualite.sort_values("nb_lignes", ascending=False).copy()
            tableau["nb_lignes"] = tableau["nb_lignes"].apply(nombre)   # 1604291 -> "1 604 291"
            st.dataframe(tableau.rename(columns={"etape": "Étape", "motif": "Motif", "nb_lignes": "Lignes"}),
                use_container_width=True, hide_index=True, height=260)


# ===== Onglet 7 : les zones trouvées par l'IA (KMeans) =====
# mêmes couleurs que dans le notebook 07 (palette "tab10" de matplotlib), une par zone
COULEURS_ZONES = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
                  "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]

with onglets[6]:
    if zones is None:
        st.info("Les zones n'existent pas encore : lance d'abord le notebook 07_kmeans.")
    else:
        plus_grande = zones.sort_values("nb_seismes", ascending=False).iloc[0]
        plus_profonde = zones.sort_values("pct_profonds", ascending=False).iloc[0]
        z1, z2, z3 = st.columns(3)
        kpi(z1, "Zones trouvées par le KMeans", str(len(zones)),
            "regroupement automatique (Spark MLlib), sans aucune connaissance des plaques")
        kpi(z2, "Zone la plus active", plus_grande["region_principale"],
            f"{nombre(plus_grande['nb_seismes'])} séismes, "
            f"{plus_grande['nb_seismes'] * 100 / zones['nb_seismes'].sum():.0f} % du total", ORANGE)
        kpi(z3, "Zone la plus profonde", plus_profonde["region_principale"],
            f"{plus_profonde['pct_profonds']:.1f} % de séismes à plus de 300 km", AQUA)
        st.write("")

        with st.container(border=True):
            titre_carte("Les zones sismiques trouvées par l'IA",
                        f"{nombre(len(carte_mag))} séismes de magnitude ≥ {mag_min:.1f} entre {annees[0]} et {annees[1]}, "
                        "coloriés selon leur zone. Le KMeans a seulement regroupé les séismes proches les uns des autres, "
                        "et il retrouve pourtant les grandes régions sismiques. Les croix sont les centres des zones.")
            fig = go.Figure()
            for _, z in zones.sort_values("zone").iterrows():
                df = carte_mag[carte_mag["zone"] == z["zone"]].sort_values("magnitude")
                fig.add_trace(go.Scattergeo(
                    lat=df["latitude"], lon=df["longitude"], name=z["nom"], mode="markers",
                    marker=dict(size=3 + (df["magnitude"] - MC) * 3, color=COULEURS_ZONES[int(z["zone"])],
                                opacity=0.8, line=dict(width=0.4, color="white")),
                    customdata=df[["lieu_court", "magnitude", "profondeur"]].values,
                    hovertemplate="<b>%{customdata[0]}</b><br>Zone : " + z["nom"] +
                                  "<br>Magnitude %{customdata[1]:.1f}<br>Profondeur %{customdata[2]:.0f} km<extra></extra>"))
            fig.add_trace(go.Scattergeo(
                lat=zones["centre_latitude"], lon=zones["centre_longitude"], name="Centre de zone", mode="markers",
                marker=dict(symbol="x", size=11, color=TEXTE, line=dict(width=1.5, color="white")),
                text=zones["nom"], hovertemplate="<b>Centre de la zone %{text}</b><extra></extra>"))
            fig.update_geos(projection_type="natural earth", showframe=False, bgcolor="white",
                            showocean=True, oceancolor="#eef3f8", showland=True, landcolor="#f7f6f2",
                            showcountries=True, countrycolor="#dcd9d1", countrywidth=0.5,
                            showcoastlines=True, coastlinecolor="#c9c6bd", coastlinewidth=0.6, showlakes=False)
            fig.update_layout(height=640, margin=dict(l=0, r=0, t=60, b=0),
                              legend=dict(y=1.12, itemsizing="constant"))
            afficher(fig)

        g, d = st.columns([3, 2])
        with g:
            with st.container(border=True):
                titre_carte("Fiche de chaque zone", "Calculée sur toute la période 2016-2025 (séismes de magnitude ≥ 4.5).")
                fiche = zones.sort_values("nb_seismes", ascending=False)[
                    ["nom", "nb_seismes", "mag_moyenne", "mag_max", "profondeur_moyenne", "pct_profonds"]]
                st.dataframe(fiche, use_container_width=True, hide_index=True, height=400, column_config={
                    "nom": "Zone",
                    "nb_seismes": st.column_config.NumberColumn("Séismes", format="%d"),
                    "mag_moyenne": st.column_config.NumberColumn("Mag. moy.", format="%.2f"),
                    "mag_max": st.column_config.NumberColumn("Mag. max", format="%.1f"),
                    "profondeur_moyenne": st.column_config.NumberColumn("Prof. moy. (km)", format="%.0f"),
                    "pct_profonds": st.column_config.ProgressColumn("Profonds", format="%.1f %%",
                                                                    min_value=0, max_value=20),
                })
        with d:
            with st.container(border=True):
                titre_carte("Où sont les séismes profonds ?",
                            "Part des séismes à plus de 300 km dans chaque zone : ils sont presque tous dans la zone Tonga, "
                            "là où la plaque plonge le plus profondément (subduction).")
                tri = zones.sort_values("pct_profonds")
                fig = go.Figure(go.Bar(
                    x=tri["pct_profonds"], y=tri["nom"], orientation="h",
                    marker=dict(color=[COULEURS_ZONES[int(z)] for z in tri["zone"]], cornerradius=4),
                    text=[f"{v:.1f} %" for v in tri["pct_profonds"]], textposition="outside", cliponaxis=False,
                    textfont=dict(size=11, color=MUET),
                    hovertemplate="<b>%{y}</b><br>%{x:.1f} % de séismes profonds<extra></extra>"))
                fig.update_layout(height=400, bargap=0.3, margin=dict(l=10, r=50, t=10, b=10),
                                  xaxis=dict(showgrid=False, showticklabels=False), yaxis=dict(showgrid=False))
                afficher(fig)

st.markdown(f'<p class="note" style="margin-top:1.5rem">Source : USGS Earthquake Catalog (ComCat). '
            f'Chaîne de traitement : HDFS + Delta Lake (bronze, silver, gold) + Spark. '
            f'Couche de service : Parquet. Valeur b : estimateur d\'Aki (1965), Mc = {MC}, ΔM = {DELTA_M}.</p>',
            unsafe_allow_html=True)
