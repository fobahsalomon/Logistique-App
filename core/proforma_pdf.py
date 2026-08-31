"""Génération de facture proforma simplifiée CA TRANS au format PDF."""

import os
from datetime import datetime
from io import BytesIO
from math import floor

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from core.pricing import DevisInput, DevisResult


YELLOW = colors.HexColor("#F2B705")
DARK = colors.HexColor("#1B232B")
TEXT = colors.HexColor("#20262B")
MUTED = colors.HexColor("#62707A")
LINE = colors.HexColor("#D8DEE3")
RED = colors.HexColor("#E2574C")


def formater_fcfa(valeur: float) -> str:
    """Formate une valeur monétaire avec l'usage français et le F CFA."""
    return f"{valeur:,.2f}".replace(",", " ").replace(".", ",") + " F CFA"


def nombre_en_lettres(n: int) -> str:
    """Convertit un nombre entier en lettres (français)."""
    unites = ["", "UN", "DEUX", "TROIS", "QUATRE", "CINQ", "SIX", "SEPT", "HUIT", "NEUF"]
    dizaines = ["", "DIX", "VINGT", "TRENTE", "QUARANTE", "CINQUANTE", "SOIXANTE",
                "SOIXANTE-DIX", "QUATRE-VINGTS", "QUATRE-VINGT-DIX"]
    centaines = ["", "CENT", "DEUX CENT", "TROIS CENT", "QUATRE CENT", "CINQ CENT",
                 "SIX CENT", "SEPT CENT", "HUIT CENT", "NEUF CENT"]

    if n == 0:
        return "ZÉRO"
    if n < 0:
        return "NÉGATIF " + nombre_en_lettres(-n)

    parties = []
    
    if n >= 1_000_000:
        millions = n // 1_000_000
        if millions == 1:
            parties.append("UN MILLION")
        else:
            parties.append(nombre_en_lettres(millions) + " MILLIONS")
        n %= 1_000_000

    if n >= 1_000:
        milliers = n // 1_000
        if milliers == 1:
            parties.append("MILLE")
        else:
            parties.append(nombre_en_lettres(milliers) + " MILLE")
        n %= 1_000

    if n >= 100:
        c = n // 100
        parties.append(centaines[c])
        n %= 100

    if n >= 20:
        d = n // 10
        parties.append(dizaines[d])
        n %= 10
        if n > 0:
            parties.append(unites[n])
    elif n >= 10:
        if n == 10:
            parties.append("DIX")
        elif n == 11:
            parties.append("ONZE")
        elif n == 12:
            parties.append("DOUZE")
        elif n == 13:
            parties.append("TREIZE")
        elif n == 14:
            parties.append("QUATORZE")
        elif n == 15:
            parties.append("QUINZE")
        elif n == 16:
            parties.append("SEIZE")
        elif n == 17:
            parties.append("DIX-SEPT")
        elif n == 18:
            parties.append("DIX-HUIT")
        elif n == 19:
            parties.append("DIX-NEUF")
    elif n > 0:
        parties.append(unites[n])

    return " ".join(parties)


def generer_proforma_pdf(
    entree: DevisInput,
    resultat: DevisResult,
    origine: str | None = None,
    destination: str | None = None,
    num_proforma: int | str | None = None,
    client_nom: str = "Client",
    responsable_flotte: str = "GNAYE SARAH",
    date_debut: str | None = None,
    date_fin: str | None = None,
) -> bytes:
    """Retourne une facture proforma PDF au format CA TRANS."""
    today = datetime.now().strftime("%d/%m/%Y")
    if num_proforma is None:
        num_proforma = int(datetime.now().strftime("%d%H%M%S"))
    elif isinstance(num_proforma, str):
        chiffres = "".join(ch for ch in num_proforma if ch.isdigit())
        num_proforma = int(chiffres) if chiffres else int(datetime.now().strftime("%d%H%M%S"))

    def parse_date_to_fr(value: str | None, fallback: str = today) -> str:
        if not value:
            return fallback
        raw = value.split("T", 1)[0]
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
            except ValueError:
                pass
        return raw

    date_debut_txt = parse_date_to_fr(date_debut, today)
    date_fin_txt = parse_date_to_fr(date_fin, date_debut_txt)

    origine_text = (origine or "Point de départ").strip()
    destination_text = (destination or "Point d'arrivée").strip()
    categorie = "73 PLACES" if entree.nb_places == 73 else f"{entree.nb_places} PLACES"
    montant_ht = float(resultat.ht_aller_retour)
    montant_tva = float(resultat.tva)
    montant_ttc = float(resultat.ttc_aller_retour)
    prix_unitaire = montant_ht / entree.nb_places if entree.nb_places else 0.0
    type_voyage = "ALLER-RETOUR"

    logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "catrans-logo.png")
    if not os.path.exists(logo_path):
        logo_path = os.path.join(os.path.dirname(__file__), "..", "Ca trans logo.png")

    sortie = BytesIO()
    document = SimpleDocTemplate(
        sortie,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.2 * cm,
        title="Facture Proforma CA TRANS",
        author="CA TRANS",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("CaTransTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=19, leading=22, textColor=DARK)
    subtitle_style = ParagraphStyle("CaTransSubtitle", parent=styles["Normal"], fontName="Helvetica-Oblique", fontSize=8, leading=10, textColor=MUTED)
    meta_style = ParagraphStyle("CaTransMeta", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=11, textColor=TEXT)
    proforma_style = ParagraphStyle("CaTransProforma", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=16, leading=18, textColor=DARK, alignment=TA_CENTER, borderPadding=6, borderWidth=1, borderColor=LINE, backColor=colors.HexColor("#F4F7FA"))
    bold_small = ParagraphStyle("BoldSmall", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=DARK)
    note_style = ParagraphStyle("CaTransNote", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=RED, alignment=TA_CENTER)
    footer_style = ParagraphStyle("CaTransFooter", parent=styles["Normal"], fontName="Helvetica", fontSize=7, leading=10, textColor=MUTED, alignment=TA_CENTER)

    elements = []

    logo_exists = os.path.exists(logo_path)
    left_block = []
    if logo_exists:
        left_block.append(Image(logo_path, width=2.9 * cm, height=2.2 * cm))
    left_block.extend([
        Paragraph("CA TRANS SARL U", title_style),
        Paragraph("Compagnie Abdoul Transport", title_style),
        Paragraph("Le transport public de personnes et de biens", subtitle_style),
    ])

    right_block = [
        Paragraph("FACTURE PROFORMA", proforma_style),
        Paragraph(f"N° Proforma: CAT-PRO-{int(num_proforma):06d}", meta_style),
        Paragraph("Prestataire: CA TRANS SARL U", meta_style),
        Paragraph(f"Date: {today}", meta_style),
        Paragraph("Objet: Prestation de transport (convoi)", meta_style),
    ]

    header_table = Table([[left_block, right_block]], colWidths=[9.5 * cm, 6.3 * cm])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 6))

    table_data = [
        ["N°", "Désignation", "Nbre de J", "Prix unitaire/J", "Montant"],
        [
            "1",
            Paragraph(
                f"LOCATION DE 1 BUS CLIMATISÉ<br/>DE {categorie}<br/>"
                f"Lieu de départ : {origine_text.upper()}<br/>"
                f"Lieu d'arrivée : {destination_text.upper()}<br/>"
                f"Type : {type_voyage}",
                meta_style,
            ),
            Paragraph(f"LE {date_debut_txt} ET LE {date_fin_txt}", meta_style),
            Paragraph(f"{formater_fcfa(prix_unitaire).replace(' F CFA', '')} / place", meta_style),
            Paragraph(formater_fcfa(montant_ht), meta_style),
        ],
    ]

    main_table = Table(table_data, colWidths=[0.8 * cm, 7.7 * cm, 2.3 * cm, 2.7 * cm, 2.6 * cm], repeatRows=1)
    main_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.7, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("WORDWRAP", (1, 1), (1, 1), "CJK"),
    ]))
    elements.append(main_table)
    elements.append(Spacer(1, 10))

    totals_table = Table([
        [Paragraph(f"Client: <b>{client_nom}</b>", bold_small), Table([
            ["Total HT", formater_fcfa(montant_ht)],
            ["TVA", formater_fcfa(montant_tva) if montant_tva else "Exonéré"],
            ["Total à payer", formater_fcfa(montant_ttc)],
        ], colWidths=[3.0 * cm, 3.1 * cm], hAlign="RIGHT")]
    ], colWidths=[7.8 * cm, 8.0 * cm], hAlign="RIGHT")
    totals_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(totals_table)
    elements.append(Spacer(1, 12))

    montant_texte = nombre_en_lettres(int(round(montant_ttc)))
    elements.append(Paragraph("Arrêté la présente facture proforma à la somme de :", bold_small))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(f"<b>{montant_texte} FRANCS CFA.</b>", bold_small))
    elements.append(Spacer(1, 16))

    signature_table = Table([
        [
            Paragraph("Signature et cachet du client", meta_style),
            Paragraph(f"Fait à Abidjan, le {today}\nCATRANS\n{responsable_flotte}\nResponsable Gestion de Flotte", meta_style),
        ]
    ], colWidths=[7.3 * cm, 7.3 * cm])
    signature_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(signature_table)
    elements.append(Spacer(1, 18))

    elements.append(Paragraph(
        "NB: Cette facture n'est valable qu'après signature de la charte de location de car de CATRANS par le client.",
        note_style,
    ))
    elements.append(Spacer(1, 20))

    line = Table([[" "]], colWidths=[15.5 * cm])
    line.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.5, colors.HexColor("#334155"))]))
    elements.append(line)
    elements.append(Spacer(1, 5))
    elements.append(Paragraph(
        "Siège Social: San-Pedro, quartier Cité, Capital social: 5 000 000, SARL U<br/>"
        "NCC: 2009427-V, RCCM: CI-SAP-2020-B-077, 01 BP: 2318 SAN-PEDRO 01<br/>"
        "Email: catransdirectionprof198021@yahoo.com | Tel: 07 08 45 28 64<br/>"
        "Site web: www.catrans-ci.com",
        footer_style,
    ))

    document.build(elements)
    return sortie.getvalue()
