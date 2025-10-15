# ajouter une explication qui explique au mieux tout ce qui peut être expliquer pour
# être compris pédagogiquement et simplement, je vais écouter en boucle dans tts reader pour mémoriser

# Bien faire apparaître
# - le rôle de la classe
# - les attributs et fonctions importantes
# - les autres classes du projet (pas celle interne à python) qiu sont utilisés par cette classe

# Générer une nouvelle version avec des commentaires parfait ni trop, ni pas assez

# Générer ensuite tous les commentaires sans le code, avec  chaque phrase répétée 3 fois pour tts reader

import json
import os

class SimulationMemoire:
    """
    Classe responsable de la gestion d'une mémoire persistante des résultats de simulation.
    Le but est de conserver et relire des métriques de performance associées à des paramètres,
    afin d'éviter de recalculer des tests déjà effectués.
    """

    def __init__(self, filename="memoire_config.json"):
        """
        Constructeur.
        - filename : nom du fichier JSON où les résultats sont sauvegardés.
        - memoire : dictionnaire contenant les résultats en mémoire vive pendant l'exécution.
        """
        self.filename = filename
        self.memoire = self._load()

    def _load(self):
        """
        Charge le contenu du fichier JSON si il existe, sinon renvoie un dictionnaire vide.
        Utilise le module json pour lire les données et le module os pour vérifier l'existence du fichier.
        """
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save(self):
        """
        Sauvegarde le contenu actuel de self.memoire dans le fichier JSON.
        Écrit avec une indentation pour faciliter la lecture humaine.
        """
        with open(self.filename, 'w') as f:
            json.dump(self.memoire, f, indent=4)

    def has_been_tested(self, params):
        """
        Vérifie si un ensemble de paramètres a déjà été enregistré.
        Retourne True si présent, False sinon.
        """
        key = self._make_key(params)
        return key in self.memoire

    def get_pnl(self, params):
        """
        Récupère les métriques associées à un ensemble de paramètres.
        Si les paramètres n'existent pas, renvoie un dictionnaire avec des valeurs par défaut.
        """
        key = self._make_key(params)
        return self.memoire.get(key, {
            'total_pnl': 0.0,
            'total_invested_capital': 0.0,
            'total_roi': 0.0,
            'daily_pnl_std': 0.0,
            'positive_or_zero_pnl_days': 0,
            'negative_pnl_days': 0
        })

    def add_result(self, params, metrics):
        """
        Ajoute ou met à jour les métriques pour un ensemble de paramètres.
        Puis sauvegarde immédiatement la mémoire mise à jour dans le fichier JSON.
        """
        key = self._make_key(params)
        self.memoire[key] = {
            'total_pnl': metrics['total_pnl'],
            'total_invested_capital': metrics['total_invested_capital'],
            'total_roi': metrics['total_roi'],
            'daily_pnl_std': metrics['daily_pnl_std'],
            'positive_or_zero_pnl_days': metrics['positive_or_zero_pnl_days'],
            'negative_pnl_days': metrics['negative_pnl_days']
        }
        self.save()

    def _make_key(self, params):
        """
        Transforme les paramètres en une chaîne JSON triée pour servir de clé unique.
        Cela garantit que l'ordre des paramètres n'affecte pas la reconnaissance.
        """
        return json.dumps(params, sort_keys=True)




# import json
# import os

# class SimulationMemoire:
#     def __init__(self, filename="memoire_config.json"):
#         self.filename = filename
#         self.memoire = self._load()

#     def _load(self):
#         if os.path.exists(self.filename):
#             try:
#                 with open(self.filename, 'r') as f:
#                     return json.load(f)
#             except Exception:
#                 return {}
#         return {}

#     def save(self):
#         with open(self.filename, 'w') as f:
#             json.dump(self.memoire, f, indent=4)

#     def has_been_tested(self, params):
#         key = self._make_key(params)
#         return key in self.memoire

#     def get_pnl(self, params):
#         key = self._make_key(params)
#         return self.memoire.get(key, {
#             'total_pnl': 0.0,
#             'total_invested_capital': 0.0,
#             'total_roi': 0.0,
#             'daily_pnl_std': 0.0,
#             'positive_or_zero_pnl_days': 0,
#             'negative_pnl_days': 0
#         })

#     def add_result(self, params, metrics):
#         key = self._make_key(params)
#         self.memoire[key] = {
#             'total_pnl': metrics['total_pnl'],
#             'total_invested_capital': metrics['total_invested_capital'],
#             'total_roi': metrics['total_roi'],
#             'daily_pnl_std': metrics['daily_pnl_std'],
#             'positive_or_zero_pnl_days': metrics['positive_or_zero_pnl_days'],
#             'negative_pnl_days': metrics['negative_pnl_days']
#         }
#         self.save()

#     def _make_key(self, params):
#         return json.dumps(params, sort_keys=True)