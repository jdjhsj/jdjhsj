"""Import en masse des salariés depuis un fichier CSV ou Excel (.xlsx).

Une ligne = un salarié. Les colonnes reconnues sont :
- identité : matricule, nom, fonction, cin, numero_cnss, salaire_base, date_embauche,
  date_naissance, personnes_a_charge, taux_cimr_salarie, taux_cimr_patronal (en %) ;
- variables du mois (facultatives) : hs_jour, hs_nuit, hs_repos_jour, hs_repos_nuit,
  salaire_reference_conges, salaire_reference_ij, interets_logement, avance, autres_retenues ;
- toute rubrique du catalogue par son code (ex. transport, prime_13e_mois), avec
  ``<code>_quantite`` et ``<code>_cumul`` si besoin ;
- tout type d'absence par son code (ex. conge_annuel, maladie) en jours.

Les en-têtes sont tolérants : majuscules, accents et espaces sont ignorés
(« Date d'embauche » = date_embauche).
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
import zipfile
from datetime import date, datetime, timedelta
from xml.etree import ElementTree

from .calcul import calculer_bulletin
from .donnees import salarie_depuis_dict, variables_depuis_dict
from .rubriques import RUBRIQUES
from .types_conges import TYPES_CONGE

CHAMPS_SALARIE = ["matricule", "nom", "fonction", "cin", "numero_cnss", "salaire_base", "date_embauche",
                  "date_naissance", "personnes_a_charge", "taux_cimr_salarie", "taux_cimr_patronal"]
CHAMPS_VARIABLES = ["salaire_reference_conges", "salaire_reference_ij", "interets_logement", "avance",
                    "autres_retenues"]
HEURES_SUP = ["jour", "nuit", "repos_jour", "repos_nuit"]
CHAMPS_DATE = {"date_embauche", "date_naissance"}

ALIAS = {
    "nom_et_prenom": "nom", "nom_prenom": "nom", "nom_complet": "nom", "salarie": "nom",
    "mat": "matricule", "n_matricule": "matricule", "poste": "fonction",
    "salaire": "salaire_base", "salaire_de_base": "salaire_base", "salaire_base_mensuel": "salaire_base",
    "date_d_embauche": "date_embauche", "embauche": "date_embauche", "date_entree": "date_embauche",
    "date_de_naissance": "date_naissance", "naissance": "date_naissance",
    "cnss": "numero_cnss", "n_cnss": "numero_cnss", "no_cnss": "numero_cnss", "num_cnss": "numero_cnss",
    "immatriculation_cnss": "numero_cnss",
    "personnes_a_charge": "personnes_a_charge", "charges_de_famille": "personnes_a_charge",
    "nb_personnes_a_charge": "personnes_a_charge", "enfants_a_charge": "personnes_a_charge",
    "cimr_salarie": "taux_cimr_salarie", "cimr_patronal": "taux_cimr_patronal",
    "heures_sup_jour": "hs_jour", "heures_sup_nuit": "hs_nuit",
    "conges_payes": "conge_annuel", "jours_conges": "conge_annuel", "conges": "conge_annuel",
    "jours_absence": "absence_non_payee", "absences": "absence_non_payee",
}

MAX_LIGNES = 5000


def normaliser(entete: str) -> str:
    texte = unicodedata.normalize("NFKD", str(entete)).encode("ascii", "ignore").decode().lower()
    texte = re.sub(r"[^a-z0-9]+", "_", texte).strip("_")
    return ALIAS.get(texte, texte)


# ---------------------------------------------------------------------------
# Lecture des fichiers
# ---------------------------------------------------------------------------

class _PointVirgule(csv.excel):
    delimiter = ";"


def lire_csv(contenu: bytes) -> list[list[str]]:
    try:
        texte = contenu.decode("utf-8-sig")
    except UnicodeDecodeError:
        texte = contenu.decode("cp1252", errors="replace")  # CSV enregistré par Excel sous Windows
    try:
        dialecte = csv.Sniffer().sniff(texte[:4096], delimiters=";,\t")
    except csv.Error:
        dialecte = _PointVirgule
    return list(csv.reader(io.StringIO(texte), dialecte))


_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _colonne(reference: str) -> int:
    lettres = re.match(r"[A-Z]+", reference).group()
    index = 0
    for lettre in lettres:
        index = index * 26 + ord(lettre) - 64
    return index - 1


def lire_xlsx(contenu: bytes) -> list[list[str]]:
    """Lit la première feuille d'un classeur .xlsx (sans dépendance externe)."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(contenu))
    except zipfile.BadZipFile:
        raise ValueError("Fichier Excel illisible. Enregistrez-le au format .xlsx ou .csv.")
    with archive:
        partages = []
        if "xl/sharedStrings.xml" in archive.namelist():
            racine = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for si in racine.findall("m:si", _NS):
                partages.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))

        classeur = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        feuille = classeur.find("m:sheets/m:sheet", _NS)
        chemin = "xl/worksheets/sheet1.xml"
        if feuille is not None and "xl/_rels/workbook.xml.rels" in archive.namelist():
            rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            for rel in rels:
                if rel.get("Id") == feuille.get(_REL):
                    cible = rel.get("Target").lstrip("/")
                    chemin = cible if cible.startswith("xl/") else "xl/" + cible
        racine = ElementTree.fromstring(archive.read(chemin))

    lignes = []
    for row in racine.iter(f"{{{_NS['m']}}}row"):
        valeurs: dict[int, str] = {}
        for c in row.findall("m:c", _NS):
            type_ = c.get("t")
            v = c.find("m:v", _NS)
            if type_ == "s" and v is not None:
                texte = partages[int(v.text)]
            elif type_ == "inlineStr":
                texte = "".join(t.text or "" for t in c.iter(f"{{{_NS['m']}}}t"))
            else:
                texte = v.text if v is not None and v.text is not None else ""
            valeurs[_colonne(c.get("r"))] = texte
        if valeurs:
            ligne = [""] * (max(valeurs) + 1)
            for i, texte in valeurs.items():
                ligne[i] = texte
            lignes.append(ligne)
    return lignes


def lire_fichier(nom: str, contenu: bytes) -> list[list[str]]:
    extension = nom.lower().rsplit(".", 1)[-1] if "." in nom else ""
    if extension in ("xlsx", "xlsm"):
        return lire_xlsx(contenu)
    if extension in ("csv", "txt"):
        return lire_csv(contenu)
    if extension == "xls":
        raise ValueError("Le format Excel 97-2003 (.xls) n'est pas pris en charge : "
                         "enregistrez le fichier en .xlsx ou en .csv.")
    raise ValueError("Format non reconnu : utilisez un fichier .xlsx ou .csv.")


# ---------------------------------------------------------------------------
# Conversion des lignes
# ---------------------------------------------------------------------------

def convertir_date(valeur: str) -> str:
    valeur = str(valeur).strip()
    if not valeur:
        return ""
    if re.fullmatch(r"\d+(\.0+)?", valeur) and float(valeur) > 1000:  # numéro de série Excel
        return (date(1899, 12, 30) + timedelta(days=int(float(valeur)))).isoformat()
    for format_ in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%y"):
        try:
            return datetime.strptime(valeur.split(" ")[0].split("T")[0], format_).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"date invalide « {valeur} » (format attendu JJ/MM/AAAA)")


def _role_colonne(cle: str):
    if cle in CHAMPS_SALARIE or cle in CHAMPS_VARIABLES:
        return ("champ", cle)
    if cle.startswith("hs_") and cle[3:] in HEURES_SUP:
        return ("hs", cle[3:])
    code = cle[4:] if cle.startswith("abs_") else cle
    if code in TYPES_CONGE:
        return ("absence", code)
    code = cle[4:] if cle.startswith("ind_") else cle
    if code in RUBRIQUES:
        return ("rubrique", code, "montant")
    for suffixe, attribut in (("_quantite", "quantite"), ("_cumul", "cumul_annuel")):
        if cle.endswith(suffixe) and cle[: -len(suffixe)] in RUBRIQUES:
            return ("rubrique", cle[: -len(suffixe)], attribut)
    return None


def analyser(lignes: list[list[str]]):
    """Transforme les lignes lues en salariés.

    Retourne ``(salaries, erreurs, colonnes_ignorees)`` où chaque salarié est un dict
    au format du registre (identité + clé ``variables``).
    """
    lignes = [l for l in lignes if any(str(c).strip() for c in l)]
    if not lignes:
        raise ValueError("Le fichier est vide.")
    if len(lignes) - 1 > MAX_LIGNES:
        raise ValueError(f"Trop de lignes (maximum {MAX_LIGNES}).")
    entetes = [normaliser(e) for e in lignes[0]]
    roles = [_role_colonne(e) for e in entetes]
    ignorees = [lignes[0][i] for i, r in enumerate(roles) if r is None and str(lignes[0][i]).strip()]
    manquantes = [c for c in ("nom", "salaire_base", "date_embauche") if c not in entetes]
    if manquantes:
        raise ValueError("Colonnes obligatoires absentes : " + ", ".join(manquantes)
                         + ". Téléchargez le modèle pour voir le format attendu.")

    salaries, erreurs = [], []
    for numero, ligne in enumerate(lignes[1:], start=2):
        entree: dict = {}
        variables: dict = {"heures_sup": {}, "indemnites": {}, "absences": {}}
        try:
            for role, valeur in zip(roles, ligne):
                valeur = str(valeur).strip()
                if role is None or valeur == "":
                    continue
                if role[0] == "champ":
                    cible = entree if role[1] in CHAMPS_SALARIE else variables
                    cible[role[1]] = convertir_date(valeur) if role[1] in CHAMPS_DATE else valeur
                elif role[0] == "hs":
                    variables["heures_sup"][role[1]] = valeur
                elif role[0] == "absence":
                    variables["absences"][role[1]] = valeur
                else:
                    variables["indemnites"].setdefault(role[1], {})[role[2]] = valeur
            if not entree.get("nom"):
                raise ValueError("nom manquant")
            if not entree.get("matricule"):
                entree["matricule"] = f"L{numero}"
            entree["variables"] = variables
            # Validation : le calcul doit passer sur une période de test.
            calculer_bulletin(salarie_depuis_dict(entree),
                              variables_depuis_dict({"annee": date.today().year, "mois": 1, **variables}))
        except (KeyError, ValueError, ArithmeticError, TypeError) as exc:
            erreurs.append(f"Ligne {numero} : {exc}")
            continue
        salaries.append(entree)
    return salaries, erreurs, ignorees


def modele_csv() -> str:
    """Modèle CSV (séparateur « ; », ouvrable dans Excel)."""
    colonnes = (CHAMPS_SALARIE + ["hs_jour", "hs_nuit", "transport", "panier", "prime_rendement",
                                  "kilometrique", "kilometrique_quantite", "conge_annuel", "maladie",
                                  "avance"])
    exemples = [
        ["001", "Ahmed Benali", "Comptable", "AB123456", "123456789", "8000", "01/03/2019", "15/05/1990",
         "3", "", "", "10", "", "500", "400", "500", "", "", "3", "", ""],
        ["002", "Salma El Idrissi", "Directrice commerciale", "BE654321", "987654321", "25000", "15/09/2010",
         "02/11/1982", "2", "6", "7,8", "", "", "500", "", "", "1200", "350", "", "", "1000"],
        ["003", "Youssef Amrani", "Opérateur", "CD112233", "555666777", "3422,72", "01/06/2025", "",
         "0", "", "", "", "6", "", "300", "", "", "", "", "2", ""],
    ]
    sortie = io.StringIO()
    w = csv.writer(sortie, delimiter=";")
    w.writerow(colonnes)
    w.writerows(exemples)
    return sortie.getvalue()
