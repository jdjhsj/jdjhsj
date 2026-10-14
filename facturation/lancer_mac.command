#!/bin/bash
cd "$(dirname "$0")"
echo "Lancement du logiciel de facturation..."
if command -v python3 >/dev/null 2>&1; then
    python3 -m facturation_maroc --ouvrir
else
    echo "Python n'est pas installé. Téléchargez-le sur https://www.python.org/downloads/"
    read -p "Appuyez sur Entrée pour fermer."
fi
