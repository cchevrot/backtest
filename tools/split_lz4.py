import os
import time
import pickle
import lz4.frame
from datetime import datetime, timedelta

def fmt_date(timestamp):
    """Converti un timestamp en date (YYYY-MM-DD)."""
    return (datetime.fromtimestamp(timestamp) + timedelta(hours=-6)).strftime("%Y-%m-%d")

def split_prices_by_day(input_filepath, output_dir):
    """
    Lit un fichier prices_data.lz4 et génère un fichier lz4 par jour.

    Args:
        input_filepath (str): Chemin vers le fichier prices_data.lz4 en entrée.
        output_dir (str): Répertoire où les fichiers lz4 par jour seront sauvegardés.
    """
    # Vérifier si le fichier d'entrée existe
    if not os.path.exists(input_filepath):
        print(f"Erreur: Le fichier {input_filepath} n'existe pas.")
        return

    # Créer le répertoire de sortie s'il n'existe pas
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Dictionnaire pour stocker les données par jour
    data_by_day = {}

    # Lire le fichier d'entrée
    with lz4.frame.open(input_filepath, mode='rb') as f:
        while True:
            try:
                buffer = pickle.load(f)
                for timestamp, ticker, price in buffer:
                    # Convertir le timestamp en date
                    day = fmt_date(timestamp)
                    # Ajouter les données au jour correspondant
                    if day not in data_by_day:
                        data_by_day[day] = []
                    data_by_day[day].append((timestamp, ticker, price))
            except EOFError:
                break

    # Sauvegarder un fichier lz4 par jour
    for day, tuples in data_by_day.items():
        output_filepath = os.path.join(output_dir, f"prices_data_{day}.lz4")
        with lz4.frame.open(output_filepath, mode='wb') as f:
            pickle.dump(tuples, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"Fichier généré: {output_filepath} avec {len(tuples)} tuples")

def main():
    """Point d'entrée principal."""
    input_filepath = r"../data/07/17_18/prices_data.lz4"
    output_dir = r"../data/split_by_day"
    
    print(f"Lecture du fichier: {input_filepath}")
    split_prices_by_day(input_filepath, output_dir)
    print("Traitement terminé.")

if __name__ == "__main__":
    main()