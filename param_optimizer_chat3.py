#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Param Optimizer — Version "Hill-Climb Expand" (ANTI OPTIMUM LOCAL)
------------------------------------------------------------------
Principe :
  • Recherche colline classique + expansion progressive automatique
  • Exploration radius = n * step (n = 1 → max reachable)
  • L'exploration d'un paramètre se répète dès qu'un autre paramètre change
  • Exploration par paires (2D hill climb) pour casser les optimums locaux
  • Cache global conservé
  • Boucle infinie → stop avec CTRL-C
"""

import json
import csv
import os
import glob
from datetime import datetime, timedelta
from multi_file_simulator import MultiFileSimulator

# ================================================================
# DISPLAY
# ================================================================
class Display:
    @staticmethod
    def info(t): print(f"[INFO] {t}")
    @staticmethod
    def warn(t): print(f"[WARN] {t}")
    @staticmethod
    def success(t): print(f"[OK]   {t}")
    @staticmethod
    def title(t): print(f"\n==== {t} ====")

# ================================================================
# SIMULATOR
# ================================================================
class TradingSimulator:
    def __init__(self, data_files=None, parallel=True):
        if data_files is None:
            data_files = glob.glob('../data/prices_data/dataset3/**/*.lz4', recursive=True)
        self.backend = MultiFileSimulator(data_files=data_files, parallel=parallel, verbose=False)

    def run(self, config):
        r = self.backend.run_all_files(config)
        return r["total_pnl"]

# ================================================================
# CACHE
# ================================================================
def _parse_value(v):
    try: return int(v)
    except: pass
    try: return float(v)
    except: return v

class ResultCache:
    def __init__(self, filename):
        self.filename = filename
        self.data = {}
        if os.path.exists(filename):
            self._load()

    def _load(self):
        with open(self.filename) as f:
            rd = csv.DictReader(f)
            for row in rd:
                pnl = float(row.pop("pnl"))
                cfg = {k: _parse_value(v) for k, v in row.items()}
                self.data[self.key(cfg)] = pnl
        Display.info(f"Cache chargé : {len(self.data)} entrées")

    def key(self, cfg): return json.dumps(cfg, sort_keys=True)
    def get(self, cfg): return self.data.get(self.key(cfg))

    def store(self, cfg, pnl):
        k = self.key(cfg)
        self.data[k] = pnl
        write_header = not os.path.exists(self.filename)
        with open(self.filename, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["pnl"] + list(cfg.keys()))
            if write_header: w.writeheader()
            w.writerow({"pnl": pnl, **cfg})

# ================================================================
# PARAMETER
# ================================================================
class Parameter:
    def __init__(self, name, meta):
        self.name = name
        self.initial = meta["initial_value"]
        self.min = meta["min_value"]
        self.max = meta["max_value"]
        self.step = meta["step"]
        self.priority = meta["priority"]
        self.enabled = meta.get("enabled", True)

    def is_time(self):
        return isinstance(self.initial, str) and ":" in self.initial

    # Expanded search: generate values center ± n*step
    def generate_expanded(self, center):
        if self.is_time():
            return self._time(center)

        values = [center]
        n = 1
        while True:
            up = center + n * self.step
            down = center - n * self.step
            pushed = False

            if up <= self.max:
                values.append(up)
                pushed = True
            if down >= self.min:
                values.append(down)
                pushed = True

            if not pushed:
                break

            n += 1

        return values

    def _time(self, center_str):
        to_dt = lambda s: datetime.strptime(s, "%H:%M")

        ct = to_dt(center_str)
        mn = to_dt(self.min)
        mx = to_dt(self.max)
        step = timedelta(minutes=int(self.step))

        values = [center_str]
        n = 1

        while True:
            up = ct + n * step
            down = ct - n * step
            pushed = False

            if up <= mx:
                values.append(up.strftime("%H:%M"))
                pushed = True
            if down >= mn:
                values.append(down.strftime("%H:%M"))
                pushed = True

            if not pushed:
                break

            n += 1

        return values

# ================================================================
# PARAMETER SPACE
# ================================================================
class ParameterSpace:
    def __init__(self, filename):
        self.filename = filename
        self.params = {}

    def load(self):
        with open(self.filename) as f:
            raw = json.load(f)
        for k, v in raw.items():
            self.params[k] = Parameter(k, v)

    def active(self):
        return sorted(
            (p for p in self.params.values() if p.enabled),
            key=lambda x: x.priority
        )

    def initial_config(self):
        return {k: p.initial for k, p in self.params.items()}

# ================================================================
# BEST
# ================================================================
class BestConfig:
    def __init__(self, filename):
        self.filename = filename
        self.config = None
        self.pnl = float('-inf')

    def load(self, space):
        if not os.path.exists(self.filename):
            self.config = space.initial_config()
            return self.config

        with open(self.filename) as f:
            d = json.load(f)

        self.config = d["config"]
        self.pnl = d["pnl"]
        return self.config.copy()

    def update(self, cfg, pnl):
        if pnl > self.pnl:
            self.pnl = pnl
            self.config = cfg.copy()
            with open(self.filename, "w") as f:
                json.dump({"pnl": pnl, "config": cfg}, f, indent=4)
            Display.success(f"Nouveau record global : {pnl:.2f}")

# ================================================================
# OPTIMIZER — HILL CLIMB EXPAND
# ================================================================
class ParamOptimizer:
    def __init__(self, sim, param_file, cache_file, best_file):
        self.sim = sim
        self.space = ParameterSpace(param_file)
        self.cache = ResultCache(cache_file)
        self.best = BestConfig(best_file)

    def evaluate(self, cfg):
        cached = self.cache.get(cfg)
        if cached is not None:
            return cached

        pnl = self.sim.run(cfg)
        self.cache.store(cfg, pnl)
        return pnl

    # 1D expanded hill climb
    def explore_param(self, cfg, param):
        center = cfg[param.name]

        best_cfg = cfg.copy()
        best_pnl = self.evaluate(cfg)

        for v in param.generate_expanded(center):
            test = cfg.copy()
            test[param.name] = v
            pnl = self.evaluate(test)

            if pnl > best_pnl:
                best_pnl = pnl
                best_cfg = test.copy()

        return best_cfg, best_pnl

    # 2D pair exploration (breaks local maxima)
    def explore_pair(self, cfg, p1, p2):
        values1 = p1.generate_expanded(cfg[p1.name])
        values2 = p2.generate_expanded(cfg[p2.name])

        best_cfg = cfg.copy()
        best_pnl = self.evaluate(cfg)

        for v1 in values1:
            for v2 in values2:
                c = cfg.copy()
                c[p1.name] = v1
                c[p2.name] = v2

                pnl = self.evaluate(c)
                if pnl > best_pnl:
                    best_pnl = pnl
                    best_cfg = c.copy()

        return best_cfg, best_pnl

    # INFINITE LOOP — STOP with CTRL-C
    def optimize(self):
        self.space.load()
        cfg = self.best.load(self.space)
        pnl = self.evaluate(cfg)

        params = self.space.active()
        iteration = 0

        while True:
            iteration += 1
            Display.title(f"Itération {iteration}")

            improved = False

            # Phase 1 : expanded hill climb 1D
            for p in params:
                new_cfg, new_pnl = self.explore_param(cfg, p)
                if new_pnl > pnl:
                    cfg = new_cfg
                    pnl = new_pnl
                    improved = True

            # Phase 2 : 2D exploration
            for i in range(len(params)):
                for j in range(i + 1, len(params)):
                    p1, p2 = params[i], params[j]
                    new_cfg, new_pnl = self.explore_pair(cfg, p1, p2)
                    if new_pnl > pnl:
                        cfg = new_cfg
                        pnl = new_pnl
                        improved = True

            self.best.update(cfg, pnl)

            if not improved:
                Display.warn("Aucune amélioration → expansion continue...")

        return cfg


# ================================================================
# MAIN
# ================================================================
def main():
    param_file = "params.json"
    cache_file = "results.csv"
    best_file = "best_config.json"

    simulator = TradingSimulator(parallel=True)
    opt = ParamOptimizer(simulator, param_file, cache_file, best_file)

    opt.optimize()  # boucle infinie jusqu’à CTRL-C


if __name__ == "__main__":
    main()
