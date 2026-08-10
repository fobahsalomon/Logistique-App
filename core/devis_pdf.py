"""Génération en mémoire des fiches de devis CA TRANS au format PDF."""

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
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
PALE_YELLOW = colors.HexColor("#FFF7D6")


def formater_fcfa(valeur: float) -> str:
    """Formate une valeur monétaire avec l'usage français et le F CFA."""
    return f"{valeur:,.2f}".replace(",", " ").replace(".", ",") + " F CFA"


def _texte(valeur: str | None, fallback: str) -> str:
    texte = (valeur or "").strip()
    return texte or fallback


def generer_pdf_devis(
    entree: DevisInput,
    resultat: DevisResult,
    origine: str | None = None,
    destination: str | None = None,
) -> bytes:
    """Retourne une fiche de devis PDF sans écrire sur le disque."""
    sortie = BytesIO()
    document = SimpleDocTemplate(
        sortie,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.35 * cm,
        bottomMargin=1.35 * cm,
        title="Devis CA TRANS",
        author="CA TRANS",
    )

    styles = getSampleStyleSheet()
    titre = ParagraphStyle(
        "CaTransTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=DARK,
        spaceAfter=2,
    )
    sous_titre = ParagraphStyle(
        "CaTransSubtitle",
        parent=styles["Normal"],
        fontSize=9,
        leading=13,
        textColor=MUTED,
        spaceAfter=14,
    )
    section = ParagraphStyle(
        "CaTransSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=DARK,
        spaceBefore=13,
        spaceAfter=7,
    )
    valeur_total = ParagraphStyle(
        "CaTransTotalValue",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=TA_RIGHT,
        textColor=DARK,
    )
    label_total = ParagraphStyle(
        "CaTransTotalLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=DARK,
    )

    origine = _texte(origine, "Point de départ")
    destination = _texte(destination, "Point d'arrivée")
    categorie = "58 places — VIP" if entree.nb_places == 58 else f"{entree.nb_places} places"

    elements = [
        Paragraph("CA TRANS", titre),
        Paragraph(
            f"Fiche de devis · Émise le {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
            sous_titre,
        ),
    ]

    trajet = [
        ["Origine", origine],
        ["Destination", destination],
        ["Distance aller simple", f"{entree.distance_km:.1f} km"],
        ["Catégorie de car", categorie],
    ]
    table_trajet = Table(trajet, colWidths=[4.4 * cm, 12.2 * cm])
    table_trajet.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F5F6")),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEADING", (0, 0), (-1, -1), 13),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    elements.extend([Paragraph("Trajet", section), table_trajet])

    elements.append(Spacer(1, 12))
    total_label = "TTC aller-retour après remise" if entree.remise_montant > 0 else "TTC aller-retour"
    total_montant = resultat.ttc_apres_remise if entree.remise_montant > 0 else resultat.ttc_aller_retour
    total = Table(
        [[Paragraph(total_label, label_total), Paragraph(formater_fcfa(total_montant), valeur_total)]],
        colWidths=[8 * cm, 8.6 * cm],
    )
    total.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE_YELLOW),
        ("BOX", (0, 0), (-1, -1), 1.2, YELLOW),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    elements.append(total)

    elements.append(Paragraph("Paramètres du voyage", section))
    parametres = [
        ["Consommation / 100 km", f"{entree.conso_100km:.2f} L"],
        ["Prix du litre", formater_fcfa(entree.prix_litre)],
        ["Frais chauffeur", formater_fcfa(entree.frais_chauffeur)],
        ["Frais convoyeur", formater_fcfa(entree.frais_convoyeur)],
        ["Péage", formater_fcfa(entree.peage)],
        ["Marge", f"{entree.marge_pct:.2f} %"],
        ["Remise", formater_fcfa(entree.remise_montant)],
    ]
    table_parametres = Table(parametres, colWidths=[8 * cm, 8.6 * cm])
    table_parametres.setStyle(TableStyle([
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(table_parametres)

    elements.append(Paragraph("Détail du calcul", section))
    detail = [
        ["Consommation totale", f"{resultat.consommation_totale:.2f} L"],
        ["Coût carburant", formater_fcfa(resultat.cout_carburant)],
        ["Coût carburant × 4 (facturé)", formater_fcfa(resultat.cout_carburant_x4)],
        ["Total autres frais", formater_fcfa(resultat.total_autres_frais)],
        ["Coût de revient total", formater_fcfa(resultat.cout_revient_total)],
        ["Marge", formater_fcfa(resultat.marge)],
        ["Prix de vente aller simple", formater_fcfa(resultat.prix_vente_aller)],
        ["Montant HT aller-retour", formater_fcfa(resultat.ht_aller_retour)],
        ["TVA (18 %)", formater_fcfa(resultat.tva)],
        ["TTC aller-retour", formater_fcfa(resultat.ttc_aller_retour)],
        ["TTC après remise", formater_fcfa(resultat.ttc_apres_remise)],
        ["TTC aller simple", formater_fcfa(resultat.ttc_aller_simple)],
    ]
    table_detail = Table(detail, colWidths=[8 * cm, 8.6 * cm])
    table_detail.setStyle(TableStyle([
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(table_detail)

    elements.append(Paragraph("Prix par place", section))
    places = [["Capacité", "Prix / place aller simple, sans TVA"]]
    places.extend([
        [f"{capacite} places", formater_fcfa(prix)]
        for capacite, prix in sorted(resultat.prix_par_place.items())
    ])
    places.append(["58 places × 2 (VIP, sans TVA)", formater_fcfa(resultat.prix_par_place_vip_58)])
    table_places = Table(places, colWidths=[8 * cm, 8.6 * cm], repeatRows=1)
    table_places.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    elements.append(table_places)
    elements.extend([
        Spacer(1, 12),
        Paragraph("CA TRANS · Fiche générée automatiquement depuis l'application de cotation.", sous_titre),
    ])

    document.build(elements)
    return sortie.getvalue()
