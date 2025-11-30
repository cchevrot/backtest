#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Param Optimizer — Version Spherical Distance Search (NO F-STRINGS)
Totally safe version: no f-strings, no multiline strings, no syntax ambiguity.
"""

import json
import csv
import os
import glob
import math
from itertools import product
from datetime import datetime, timedelta
from multi_file_simulator import MultiFileSimulator

# ================================================================
# DISPLAY (SAFE, NO F-STRINGS)
# ================================================================
class Display:
    @staticmethod
    def info(t):
        print("[INFO] " + str(t))

    @staticmethod
    def warn(t):
        print("[WARN] " + str(t))

    @staticmethod
    def success(t):
        print("[OK]   " + str(t))

    @staticmethod
    def title(t):
        print("\n==== " + str(t) + " ====")

# ================================================================
# SIMULATOR
# ================================================================
class TradingSimulator:
    def __init__(self, data_files=None, parallel=True):
        if data_files is None:
            data_files = glob.glob('../data/prices_data/dataset3/**/*.lz4', recursive=True)
        self.backend = MultiFileSimulator(data_files=data_files, parallel=parallel, verbose=False)

    def run(self, config):
        result = self.backend.run_all_files(config)
        return result["total_pnl"]

# ================================================================
# CACHE
# ================================================================
def _parse_value(v):
    try:
        return int(v)
    except:
        pass
    try:
        return float(v)
    except:
        return v

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
                cfg = {}
                for k, v in row.items():
                    cfg[k] = _parse_value(v)
                key = self.key(cfg)
                self.data[key] = pnl
        Display.info("Cache chargé : " + str(len(self.data)) + " entrées")

    def key(self, cfg):
        print("---------------------")
        print(cfg)
        print("-----------------------")
        return json.dumps(cfg, sort_keys=True)

    def get(self, cfg):
        key = self.key(cfg)
        return self.data.get(key)

    def store(self, cfg, pnl):
        key = self.key(cfg)
        self.data[key] = pnl
        write_header = not os.path.exists(self.filename)
        with open(self.filename, "a", newline="") as f:
            fieldnames = ["pnl"] + list(cfg.keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            row = {"pnl": pnl}
            row.update(cfg)
            writer.writerow(row)

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
        self.enabled = meta.get("enabled", True)

    def is_time(self):
        return isinstance(self.initial, str) and ":" in self.initial

    def apply_offset(self, center, units):
        if self.is_time():
            to_dt = lambda s: datetime.strptime(s, "%H:%M")
            ct = to_dt(center)
            new = ct + timedelta(minutes=int(units) * int(self.step))
            mn = to_dt(self.min)
            mx = to_dt(self.max)
            if new < mn or new > mx:
                return None
            return new.strftime("%H:%M")

        else:
            value = center + units * self.step
            if value < self.min or value > self.max:
                return None
            return value

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
        return [p for p in self.params.values() if p.enabled]

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
            Display.success("Nouveau record global : " + str(pnl))

# ================================================================
# OPTIMIZER — SPHERICAL SEARCH (NO F-STRINGS)
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

    def generate_spherical_offsets(self, params, R):
        n = len(params)
        for vector in product(range(-R, R+1), repeat=n):
            if all(v == 0 for v in vector):
                continue

            dist = math.sqrt(sum(v*v for v in vector))
            if abs(dist - R) < 1e-9 or int(dist) == R:
                yield vector

    def spherical_search(self):
        self.space.load()
        params = self.space.active()
        best_cfg = self.best.load(self.space)
        best_pnl = self.evaluate(best_cfg)

        R = 1
        while True:
            Display.title("Spherical Radius R = " + str(R))
            improved = False

            for offset_vec in self.generate_spherical_offsets(params, R):
                cfg = best_cfg.copy()
                valid = True

                for p, units in zip(params, offset_vec):
                    newv = p.apply_offset(cfg[p.name], units)
                    if newv is None:
                        valid = False
                        break
                    cfg[p.name] = newv

                if not valid:
                    continue

                pnl = self.evaluate(cfg)

                if pnl > best_pnl:
                    best_cfg = cfg.copy()
                    best_pnl = pnl
                    improved = True
                    self.best.update(best_cfg, best_pnl)

            if not improved:
                Display.warn("Aucune amélioration → extension du rayon")

            R += 1

# ================================================================
# MAIN
# ================================================================
def main():
    param_file = "params.json"
    cache_file = "results.csv"
    best_file = "best_config.json"

    simulator = TradingSimulator(parallel=True)
    opt = ParamOptimizer(simulator, param_file, cache_file, best_file)

    opt.spherical_search()   # boucle infinie, arrêt avec CTRL-C


if __name__ == "__main__":
    main()
