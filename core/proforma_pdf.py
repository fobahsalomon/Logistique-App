"""Génération de facture proforma simplifiée CA TRANS au format PDF."""

from datetime import datetime
from io import BytesIO
from math import floor

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
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
    num_proforma: int = 68,
    client_nom: str = "Client",
) -> bytes:
    """Retourne une facture proforma PDF sans écrire sur le disque."""
    sortie = BytesIO()
    document = SimpleDocTemplate(
        sortie,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.35 * cm,
        bottomMargin=1.35 * cm,
        title="Facture Proforma CA TRANS",
        author="CA TRANS",
    )

    styles = getSampleStyleSheet()
    
    # En-tête
    titre = ParagraphStyle(
        "TitreProforma",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=28,
        leading=32,
        textColor=DARK,
        spaceAfter=2,
        alignment=TA_CENTER,
    )
    sous_titre_header = ParagraphStyle(
        "SousTitreHeader",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        textColor=TEXT,
        spaceAfter=4,
        alignment=TA_CENTER,
    )
    label_info = ParagraphStyle(
        "LabelInfo",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        textColor=TEXT,
    )
    titre_section = ParagraphStyle(
        "TitreSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=14,
        textColor=DARK,
        spaceBefore=8,
        spaceAfter=6,
    )
    label_note = ParagraphStyle(
        "LabelNote",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=RED,
        fontName="Helvetica-Bold",
    )
    sous_titre = ParagraphStyle(
        "SousTitre",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=MUTED,
    )

    elements = []

    # En-tête CA TRANS
    elements.append(Paragraph("CA TRANS SARL U", titre))
    elements.append(Paragraph("Le transport public de personnes et de biens", sous_titre_header))
    elements.append(Spacer(1, 8))

    # Titre facture proforma
    elements.append(Paragraph("FACTURE PROFORMA", titre_section))
    elements.append(Paragraph(f"N° Proforma : CAT-PRO-{num_proforma:06d}", label_info))
    elements.append(Spacer(1, 10))

    # Infos client et prestataire
    info_table = Table([
        [Paragraph(f"<b>Prestataire :</b> CA TRANS SARL U", label_info),
         Paragraph(f"<b>Client :</b> {client_nom}", label_info)],
        [Paragraph(f"<b>Date :</b> {datetime.now().strftime('%d/%m/%Y')}", label_info), ""],
    ])
    info_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 8))

    # Objet
    elements.append(Paragraph("<b>Objet :</b> Prestation de transport (convoi)", label_info))
    elements.append(Spacer(1, 12))

    # Tableau principal
    origine_text = (origine or "Point de départ").strip()
    destination_text = (destination or "Point d'arrivée").strip()
    categorie = "73 PLACES" if entree.nb_places == 73 else f"{entree.nb_places} PLACES"
    
    # Calcul des prix
    montant_total = resultat.ht_aller_retour
    prix_par_place = montant_total / entree.nb_places

    designation = (
        f"LOCATION DE 1 BUS CLIMATISÉ DE {categorie}\n"
        f"Lieu de départ : {origine_text.upper()}\n"
        f"Lieu d'arrivé : {destination_text.upper()}\n"
        f"Type : ALLER-RETOUR"
    )

    tableau_data = [
        ["N°", "Désignation", "Nbre de J", "Prix unitaire/J", "Montant"],
        [
            "1",
            designation,
            "01/02",
            f"{prix_par_place:,.0f}",
            f"{montant_total:,.0f}",
        ],
    ]

    tableau_principal = Table(tableau_data, colWidths=[0.7*cm, 6*cm, 1.5*cm, 2.5*cm, 2.5*cm])
    tableau_principal.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(tableau_principal)
    elements.append(Spacer(1, 12))

    # Résumé : Total, TVA, Total à payer
    montant_total = resultat.ht_aller_retour
    resume_data = [
        ["", "Total", f"{montant_total:,.0f}"],
        ["", "TVA", ""],
        ["", "Total à payer", f"{montant_total:,.0f}"],
    ]
    resume_table = Table(resume_data, colWidths=[6*cm, 2.5*cm, 2.5*cm])
    resume_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (1, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (1, 0), (-1, -1), 10),
        ("GRID", (1, 0), (-1, -1), 0.5, LINE),
        ("BACKGROUND", (1, 2), (-1, 2), colors.HexColor("#F0F0F0")),
        ("LEFTPADDING", (1, 0), (-1, -1), 6),
        ("RIGHTPADDING", (1, 0), (-1, -1), 6),
        ("TOPPADDING", (1, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (1, 0), (-1, -1), 5),
    ]))
    elements.append(resume_table)
    elements.append(Spacer(1, 14))

    # Arrêté de la facture
    montant_entier = int(montant_total)
    montant_texte = nombre_en_lettres(montant_entier)
    
    elements.append(Paragraph(
        f"Arrêté la présente facture proforma à la somme de :",
        label_info
    ))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(
        f"<b>{montant_texte} FRANCS CFA.</b>",
        ParagraphStyle("", parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold", textColor=DARK)
    ))
    elements.append(Spacer(1, 16))

    # Signature
    signature_data = [
        [
            Paragraph("Fait à Abidjan, le " + datetime.now().strftime("%d/%m/%Y"), label_info),
            Paragraph("Signature et cachet du client", label_info),
        ],
        [
            Paragraph("<b>CA TRANS</b><br/>GNAYE SARAH<br/><i>Responsable Gestion de Flotte</i>", 
                     ParagraphStyle("", parent=styles["Normal"], fontSize=8, leading=10)),
            "",
        ],
    ]
    signature_table = Table(signature_data, colWidths=[8.5*cm, 8.5*cm])
    signature_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(signature_table)
    elements.append(Spacer(1, 14))

    # Note obligatoire
    elements.append(Paragraph(
        "NB : Cette facture n'est valable qu'après signature de la charte de location de car de CATRANS par le client.",
        label_note
    ))
    elements.append(Spacer(1, 20))

    # Footer avec infos entreprise
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=7,
        leading=9,
        textColor=MUTED,
        alignment=TA_CENTER,
    )
    footer_text = (
        "Siège Social: San-Pedro, quartier Cité, Capital social: 5 000 000, SARL U<br/>"
        "NCC: 2009427-V, RCCM: CI-SAP-2020-B-077, 01 BP: 2318 SAN-PEDRO 01<br/>"
        "Email: catransdirectionprof198021@yahoo.com | Tel: 07 08 45 28 64<br/>"
        "Site web: www.catrans-ci.com"
    )
    elements.append(Paragraph(footer_text, footer_style))

    document.build(elements)
    return sortie.getvalue()
