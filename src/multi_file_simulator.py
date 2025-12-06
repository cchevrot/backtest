#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MultiFileSimulator — VERSION MODIFIÉE AVEC nb_trades + roi
"""

import os
import json
import lz4.frame
import pandas as pd
from concurrent.futures import ProcessPoolExecutor
from single_file_simulator import SingleFileSimulator


class MultiFileSimulator:

    def __init__(self, data_files, parallel=True, verbose=False):
        self.data_files = data_files
        self.parallel = parallel
        self.verbose = verbose

    def _simulate_single_file(self, filename, config):
        """
        Simulation réelle : appelle SingleFileSimulator.run_single_file
        """
        try:
            result = SingleFileSimulator.run_single_file(filename, config, verbose=False)
            return result   # contient file_pnl, num_traded, ...
        except Exception:
            return {
                "file_pnl": 0.0,
                "num_traded": 0
            }

    def run_all_files(self, config):
        """
        Retourne :
        {
            "total_pnl": ...,
            "total_trades": ...,
            "roi": ...
        }
        """
        if self.parallel:
            with ProcessPoolExecutor() as executor:
                results = list(executor.map(
                    self._simulate_single_file,
                    self.data_files,
                    [config] * len(self.data_files)
                ))
        else:
            results = [
                self._simulate_single_file(f, config)
                for f in self.data_files
            ]

        total_pnl = sum(r["file_pnl"] for r in results)
        total_trades = sum(r["num_traded"] for r in results)

        roi = (total_pnl / total_trades) if total_trades > 0 else 0.0

        return {
            "total_pnl": total_pnl,
            "total_trades": total_trades,
            "roi": roi
        }
