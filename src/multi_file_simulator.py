#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MultiFileSimulator — VERSION AVEC nb_trades, roi, win_rate, drawdown
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
            return result  # contient file_pnl, num_traded, etc.
        except Exception:
            return {
                "file_pnl": 0.0,
                "num_traded": 0
            }


    def _compute_drawdown(self, daily_pnls):
        """
        Drawdown global basé sur l'équity cumulée entre les jours.
        """
        equity = []
        total = 0
        for pnl in daily_pnls:
            total += pnl
            equity.append(total)

        if not equity:
            return 0.0

        peak = equity[0]
        max_dd = 0

        for value in equity:
            if value > peak:
                peak = value
            dd = peak - value
            if dd > max_dd:
                max_dd = dd

        return max_dd


    def run_all_files(self, config):
        """
        Retourne maintenant :
        {
            total_pnl,
            total_trades,
            roi,
            win_rate,
            drawdown
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

        # Extraction des daily metrics
        daily_pnls = [r["file_pnl"] for r in results]
        daily_trades = [r["num_traded"] for r in results]

        total_pnl = sum(daily_pnls)
        total_trades = sum(daily_trades)

        # ROI défini comme demandé
        roi = (total_pnl / total_trades) if total_trades > 0 else 0.0

        # Win rate = % de journées positives
        positive_days = sum(1 for pnl in daily_pnls if pnl > 0)
        total_days = len(daily_pnls)
        win_rate = (positive_days / total_days * 100.0) if total_days > 0 else 0.0

        # Drawdown global basé sur l'equity cumulée jour/jour
        drawdown = self._compute_drawdown(daily_pnls)

        return {
            "total_pnl": total_pnl,
            "total_trades": total_trades,
            "roi": roi,
            "win_rate": win_rate,
            "drawdown": drawdown
        }
