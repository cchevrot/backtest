import os
import time
import pickle
import lz4.frame
import glob
from datetime import datetime, timedelta

def fmt_date(timestamp):
    """Converti un timestamp en date (YYYY-MM-DD)."""
    return (datetime.fromtimestamp(timestamp) + timedelta(hours=-6)).strftime("%Y-%m-%d")

def get_unique_filepath(filepath):
    """
    Retourne un chemin de fichier unique en ajoutant un suffixe si le fichier existe déjà.
    
    Args:
        filepath (str): Chemin du fichier.
        
    Returns:
        str: Chemin unique.
    """
    if not os.path.exists(filepath):
        return filepath
    
    base, ext = os.path.splitext(filepath)
    counter = 1
    while True:
        new_filepath = f"{base}_{counter}{ext}"
        if not os.path.exists(new_filepath):
            return new_filepath
        counter += 1

def split_prices_by_day(input_filepath, output_dir):
    """
    Lit un fichier prices_data.lz4 et génère un fichier lz4 par jour.

    Args:
        input_filepath (str): Chemin vers le fichier prices_data.lz4 en entrée.
        output_dir (str): Répertoire où les fichiers lz4 par jour seront sauvegardés.
    """
    if not os.path.exists(input_filepath):
        print(f"Erreur: Le fichier {input_filepath} n'existe pas.")
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    data_by_day = {}

    print(f"Traitement: {input_filepath}")
    try:
        with lz4.frame.open(input_filepath, mode='rb') as f:
            while True:
                try:
                    buffer = pickle.load(f)
                    for timestamp, ticker, price in buffer:
                        day = fmt_date(timestamp)
                        if day not in data_by_day:
                            data_by_day[day] = []
                        data_by_day[day].append((timestamp, ticker, price))
                except EOFError:
                    break
    except Exception as e:
        print(f"Erreur lors de la lecture de {input_filepath}: {e}")
        return

    for day, tuples in data_by_day.items():
        output_filepath = os.path.join(output_dir, f"{day}-prices_data.lz4")
        output_filepath = get_unique_filepath(output_filepath)
        with lz4.frame.open(output_filepath, mode='wb') as f:
            pickle.dump(tuples, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"Fichier généré: {output_filepath} avec {len(tuples)} tuples")

def main():
    """Point d'entrée principal."""
    input_dir = r"C:\projets\bot\data\prices_data"
    output_dir = r"../data"
    
    lz4_files = glob.glob(os.path.join(input_dir, "**", "*.lz4"), recursive=True)
    
    if not lz4_files:
        print(f"Aucun fichier .lz4 trouvé dans {input_dir}")
        return
    
    print(f"{len(lz4_files)} fichier(s) .lz4 trouvé(s)")
    for lz4_file in lz4_files:
        split_prices_by_day(lz4_file, output_dir)
    print("Traitement terminé.")

if __name__ == "__main__":
    main()