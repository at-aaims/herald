#!/usr/bin/env python3
"""
Script to analyze jobsummary data from frontier and do some simple linear regressions to use for
rough estimations of the stats data. This generates the stats.json file used in
generate_frontier_job_data.py for the ranges and distribution of each field.
"""

import argparse
from pathlib import Path
import pandas as pd
import scipy
import scipy.stats
from loguru import logger
import json


def analyze_data(job_summary: Path) -> dict:
    def read_job_summary(columns):
        if "time_start" not in columns:
            columns = ["time_start", *columns]
        df = pd.read_parquet(job_summary,
            columns = columns,
            engine = "pyarrow",
            dtype_backend = 'numpy_nullable',
        )
        df = df[df['time_start'].notnull()]
        return df
    
    def get_basic_stats(series: pd.Series):
        return {
            'min': float(series.min()),
            'max': float(series.max()),
            'mean': float(series.mean()),
            'std': float(series.std()),
            'median': float(series.median()),
            'mad': float(scipy.stats.median_abs_deviation(series)),
        }

    results = {}

    logger.info("Fitting node_count...")
    df = read_job_summary(['node_count'])
    data = df['node_count']
    params = scipy.stats.halfgennorm.fit(data, method='MM')
    results["node_count"] = {}
    results["node_count"]['dist'] = {
        "dist": "halfgennorm",
        "params": [round(p, 5) for p in params],
    }
    results['node_count'].update(get_basic_stats(data))
    
    logger.info("Fitting runtime...")
    df = read_job_summary(['time_start', 'time_end'])
    df['runtime'] = (df['time_end'] - df['time_start']).dt.total_seconds()
    data = df['runtime']
    params = scipy.stats.halfgennorm.fit(data, method='MM')
    results["runtime"] = {}
    results['runtime']['dist'] = {
        "dist": "halfgennorm",
        "params": [round(p, 5) for p in params],
    }
    results['runtime'].update(get_basic_stats(data))

    # Read empty parquet to get column list
    all_columns = list(pd.read_parquet(job_summary, filters=[("allocation_id", "==", "X")]).columns)
    stats_fields = [
        c
        for c in all_columns
        if c.startswith("stats_") and c != 'stats_telemetry_node_hours'
    ]
    results['stats'] = {}

    for stat_field in stats_fields:
        logger.info(f"Analyzing {stat_field} ...")
        stat_result: dict = {
            "linear_regression" : {},
            "dist": [],
        }

        df = read_job_summary(["node_count", "time_start", "time_end", stat_field])
        df = df[df[stat_field].notnull()]
        df['runtime'] = (df['time_end'] - df['time_start']).dt.total_seconds()
        df['node_hours'] = df['node_count'] * (df['runtime'] / (60 * 60))

        for x_field in ["node_count", "runtime", "node_hours"]:
            reg = scipy.stats.linregress(df[x_field], df[stat_field])
            stat_result['linear_regression'][x_field] = {
                "slope": float(round(reg.slope, 5)),
                "intercept": float(round(reg.intercept, 5)),
                "rvalue": float(round(reg.rvalue, 5)),
                "pvalue": float(round(reg.rvalue, 5)),
                "stderr": float(round(reg.stderr, 5)),
                "intercept_stderr": float(round(reg.intercept_stderr, 5)),
            }

        # params = scipy.stats.halfgennorm.fit(data, method='MM')
        # stat_result["dist"].append({
        #   "dist": "halfgennorm",
        #   "params": [round(p, 5) for p in params],
        # })

        # params = scipy.stats.gennorm.fit(data, method='MM')
        # stat_result["dist"].append({
        #   "dist": "gennorm",
        #   "params": [round(p, 5) for p in params],
        # })

        stat_result.update(get_basic_stats(df[stat_field]))

        results["stats"][stat_field] = stat_result

    logger.info("Done!")

    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description = __doc__.strip(),
        # By default argparse allows prefixes of options which is an issue for backwards compatibility
        allow_abbrev = False,
        formatter_class = argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("job_summary", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    output = analyze_data(args.job_summary)
    Path(args.out).write_text(json.dumps(output, indent=4))
