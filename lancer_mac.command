#!/bin/bash
cd "$(dirname "$0")"
echo "Lancement du logiciel de paie..."
if command -v python3 >/dev/null 2>&1; then
    python3 -m paie_maroc web --ouvrir
else
    echo "Python n'est pas installé. Téléchargez-le sur https://www.python.org/downloads/"
    read -p "Appuyez sur Entrée pour fermer."
fi
