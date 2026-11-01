#!/usr/bin/env python3
"""
Generate synthetic frontier job data as parquets, in the format of the jobsummary dataset.

Example usage, generate one month of fake data:
    ./scripts/generate_frontier_job_data.py --start=2024-01-01T00:00:00+00:00 --end=2024-02-01T00:00:00+00:00 --out data

Omitting --start/--end defaults to a rolling "last 3 months through today"
window (1st of the month, 2 months back, through now) so the demo data
stays current without anyone needing to remember a date to pass in.

Statistical distributions come from stats.json (next to this file; override
with --stats). That file is a fabricated placeholder, not fit to any real
measurement — see scripts/build_placeholder_job_stats.py.
"""
from typing import Iterable, Optional
import argparse, re, json
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta, timezone
from ClusterShell.NodeSet import NodeSet
import faker, random, base64, itertools
import scipy
import pandas as pd
from loguru import logger
import csv


def clamped_rvs(dist, low, high):
    while True:
        v = dist.rvs()
        if low <= v < high:
            return v


def summarize_ranges(nodes: list[str]):
    """
    Converts a list of node names like ["frontier00001", "frontier00002"] into a range string
    like "frontier[00001-00002]".
    ClusterShell can do this as well but it is really really slow, so I've reimplemented it here
    """
    if len(nodes) == 0:
        return ""
    elif len(nodes) == 1:
        return nodes[0]
    else:
        prefix, num = re.fullmatch(r"([a-zA-Z_]+)(\d+)", nodes[0]).groups()
        w = len(num)

        ranges = []
        start, end = None, None
        for node in nodes:
            num = int(node.removeprefix(prefix))
            if start is None or end is None:
                start, end = num, num
            elif num == end + 1:
                end = num
            else:
                ranges.append(f"{start:0{w}}-{end:0{w}}" if start != end else f"{start:0{w}}")
                start, end = num, num
        ranges.append(f"{start:0{w}}-{end:0{w}}" if start != end else f"{start:0{w}}")

        return f"{prefix}[{','.join(ranges)}]"

def generate_accounts_from_csv(rand):
    """Generate accounts based on science domains from CSV file"""
    # Path to the CSV file relative to the script
    csv_path = csv_path = Path(__file__).parent.parent.joinpath("src/site/ornl/frontier/metadata/desc_science_domains.csv")
    accounts_dict = {}
    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                domain_code = row['Domain'].strip()
                # Generate accounts per domain - some domains more popular than others
                # Common domains get more accounts
                if domain_code in ['CSC', 'ENG', 'PHY', 'CHM']:  # Popular domains
                    num_accounts_per_domain = rand.randint(12, 20)
                elif domain_code in ['CFD', 'MAT', 'AST', 'GEO']:  # Medium popularity
                    num_accounts_per_domain = rand.randint(8, 12)
                else:  # Less common domains
                    num_accounts_per_domain = rand.randint(3, 8)
                for i in range(num_accounts_per_domain):
                    # Create account name using domain code + random number
                    account_name = f"{domain_code}{rand.randint(0, 999):03}"
                    # Assign weight (some domains might be more popular)
                    weight = rand.randint(1, 100)
                    accounts_dict[account_name] = weight
                    
    except FileNotFoundError:
        print(f"Warning: CSV file not found at {csv_path}")
        print("Falling back to random account generation")
        # Fallback to original random generation
        accounts_dict = {
            f"{rand.choice(['PHY', 'CFD', 'CSC', 'CHM', 'ENG'])}{rand.randint(0, 999):03}": rand.randint(1, 100)
            for i in range(300)
        }
    
    return accounts_dict

def get_users_and_accounts(random_accounts: bool = False):
    """ Get users and accountswith a set seed so they are consistent """
    fake = faker.Faker()
    fake.seed_instance(1)
    rand = random.Random(2)

    # Generate a set of users with weights so some some users show up more than others
    users_dict = {
        f"{fake.profile()['username']}": rand.randint(1, 10)
        for i in range(1000)
    }
    users = list(users_dict.keys())
    user_weights = list(users_dict.values())

    # Assign an account to each user
    if not random_accounts:
        accounts_dict = generate_accounts_from_csv(rand)
    else:
        accounts_dict = {
            f"{fake.word()[:3]}{rand.randint(0, 999):03}".upper(): rand.randint(1, 100)
            for i in range(300)
        }
    accounts = list(accounts_dict.keys())
    account_weights = list(accounts_dict.values())
    user_accounts = {
        user: rand.choices(accounts, weights = account_weights, k = 1)[0]
        for user in users
    }

    return dict(
        users = users,
        user_weights = user_weights,
        accounts = accounts,
        account_weights = account_weights,
        user_accounts = user_accounts,
    )


class RandomJobGenerator:
    def __init__(self, *,
        total_nodes = 9408, # TODO: Is this still correct?
        stats: Optional[dict] = None,
        seed = None,
    ):
        self.fake = faker.Faker()
        if seed:
            random.seed(seed)
            self.fake.seed_instance(seed)
            np.random.seed(seed=seed)

        self.total_nodes = total_nodes
        if stats:
            self.stats = stats
        else:
            self.stats = json.loads((Path(__file__).resolve().parent / 'stats.json').read_text())

        # Some approximations of node_count and runtime distributions, based on our best fits to our data
        dist_type = self.stats['node_count']['dist']['dist']
        dist_params = self.stats['node_count']['dist']['params']
        self.node_count_dist = getattr(scipy.stats, dist_type)(*dist_params)
        
        dist_type = self.stats['runtime']['dist']['dist']
        dist_params = self.stats['runtime']['dist']['params']
        self.runtime_dist = getattr(scipy.stats, dist_type)(*dist_params)
        
        self.max_walltime = 24 * 60 * 60
        self.next_job_id = random.randint(1, 4_000_000)

        users_and_accounts = get_users_and_accounts()
        self.users = users_and_accounts['users']
        self.user_weights = users_and_accounts['user_weights']
        self.accounts = users_and_accounts['accounts']
        self.account_weights = users_and_accounts['account_weights']
        self.user_accounts = users_and_accounts['user_accounts']

        self.partitions = ['batch', 'batch-spi', 'cron', 'extended', 'testing']

        states = {
            "COMPLETED": 800,
            "FAILED": 100,
            "TIMEOUT": 50,
            "CANCELLED": 50,
            "NODE_FAIL": 1,
        }
        self.states = list(states.keys())
        self.state_weights = list(states.values())

        self.missing_cabinets = [
            "x2305", "x2600", "x2604", "x2605", "x2606", "x2607", "x2608",
            "x2603", # This is a TDS cabinet
        ]
        self.xnames_pattern = 'x[2000-2011,2100-2111,2200-2211,2300-2304,2306-2311,2400-2411,2500-2511,2600-2604,2606-2611]c[0-7]s[0-7]b[0-1]'
        self.hostname_prefix = "frontier"
        self.hostname_to_xname = {
            f"{self.hostname_prefix}{1 + i:05}": xname
            for i, xname in enumerate(NodeSet(self.xnames_pattern))
            if not any(xname.startswith(c) for c in self.missing_cabinets)
        }
        self.xname_to_hostname = {
            xname: hostname
            for hostname, xname in self.hostname_to_xname.items()
        }

        self.stat_ranges: dict[str, tuple[float, float]] = {}
        for field, field_stats in self.stats['stats'].items():
            mean = field_stats['mean']
            std = field_stats['std']
            # Set min/max based on 3 standard deviations from mean so we don't include the outlier
            # measurements in the dataset. Later we'll clean up the outliers in the original dataset
            # better and then we may switch to just using the original min/max
            self.stat_ranges[field] = (max(mean - 2 * std, 0), mean + 2 * std)


    def generate_job_placement(self) -> dict:
        """ Generate just the runtime and node_count so we can schedule the job """
        result = {
            "job_id": self.next_job_id,
            "runtime": int(clamped_rvs(self.runtime_dist, 1, self.max_walltime)),
            "node_count": int(clamped_rvs(self.node_count_dist, 1, self.total_nodes + 1)),
        }
        self.next_job_id += 1
        return result


    def populate_job_placement(self, placement: dict, time_start: datetime, xnames: list[str]) -> dict:
        runtime = placement['runtime']
        time_end = time_start + timedelta(seconds=runtime)
        time_submission = time_start - timedelta(seconds=random.randint(1, 24 * 60 * 60))
        time_hash = base64.b32encode(int(time_submission.timestamp() * 1000).to_bytes(6, 'big')).decode().rstrip('=')
        user = random.choices(self.users, weights = self.user_weights, k = 1)[0]
        state = random.choices(self.states, weights = self.state_weights, k = 1)[0]
        nodes = [self.xname_to_hostname[xname] for xname in xnames]
        node_hours = (runtime / 60 / 60) * placement['node_count']

        result = {
            "slurm_version": "24.05.2",
            "job_id": str(placement['job_id']),
            "allocation_id": f"{placement['job_id']}.{time_hash}",

            "account": self.user_accounts[user],
            "group": user,
            "user": user,
            "name": self.fake.word(),
            "working_directory": f"{Path(self.fake.file_path(random.randint(2, 4))).parent}",
            "partition": random.choice(self.partitions),
            "time_limit": pd.Timedelta(seconds = runtime).ceil("h").total_seconds(),
            "constraints": random.choice(['', 'nvme']),
            "mcs": "",

            "time_submission": time_submission,
            "time_eligible": time_submission,
            "time_start": time_start,
            "time_end": time_end,
            "time_elapsed": runtime,

            "node_count": placement['node_count'],
            "node_ranges": summarize_ranges(nodes),
            "xnames": xnames,

            "state_current": state,
            "state_reason": "",

            "batch_time_start": time_start,
            "batch_time_end": time_end,
            "batch_time_elapsed": runtime,

            # Batch script states and results
            "batch_state": state,
            "batch_exit_code_return_code": 0 if state == "COMPLETED" else random.randint(1, 127),
            "batch_exit_code_status": "",

            "time_snapshot": time_end,

            'node_hours': node_hours,
            "stats_telemetry_node_hours": node_hours * min(1, random.uniform(0.50, 1.75)),
        }

        for stat_field, stat_range in self.stat_ranges.items():
            result[stat_field] = random.uniform(*stat_range)

        return result


    def generate_jobs(self, start: datetime, end: datetime) -> Iterable[dict]:
        # Generate a valid scheduling of jobs by a simple simulation of scheduling
        running: list[dict] = []
        queue: list[dict] = []
        completed = 0
        timestamp = start
        max_age = self.total_nodes // 2
        min_job_id = None
        idle_node_hours = 0
        step = timedelta(seconds=5)
        idle_nodes = list(self.xname_to_hostname.keys())

        while timestamp < end:
            # Remove completed jobs
            just_completed = [j for j in running if j['time_end'] < timestamp]
            if len(just_completed) > 0:
                running = [j for j in running if j['time_end'] >= timestamp]
                for job in just_completed:
                    idle_nodes.extend(job['xnames'])
                    completed += 1

            # schedule new jobs
            idle_node_hours += len(idle_nodes) * step.total_seconds() / 60 / 60

            while len(idle_nodes) > 0:
                # Submit jobs to the queue
                queue_needs_sort = False
                while min_job_id is None or self.next_job_id - min_job_id < max_age:
                    job = self.generate_job_placement()
                    queue.append(job)
                    if min_job_id is None:
                        min_job_id = job['job_id']
                    queue_needs_sort = True
                if queue_needs_sort:
                    queue = sorted(queue, key = lambda j: j['node_count'], reverse = True)

                # Find a job in the queue that fits
                job_to_schedule = None
                for job in queue:
                    if job['node_count'] <= len(idle_nodes):
                        job_to_schedule = job
                        break

                # Schedule the match, if there is one
                if job_to_schedule:
                    queue.remove(job_to_schedule)

                    if job_to_schedule['job_id'] == min_job_id:
                        min_job_id = min((j['job_id'] for j in queue), default = None)
                    
                    job_nodes = sorted(idle_nodes[-job_to_schedule['node_count']:])
                    # Remove from idle_nodes with slice assignment
                    idle_nodes[-job_to_schedule['node_count']:] = []

                    job_to_schedule = self.populate_job_placement(job_to_schedule, timestamp, job_nodes)

                    running.append(job_to_schedule)
                    yield job_to_schedule
                else:
                    break

            timestamp += step

        logger.info(f"Finished generation from {start.isoformat()} to {end.isoformat()}")
        possible_node_hours = self.total_nodes * (end - start).total_seconds() / 60 / 60
        idle_percentage = idle_node_hours / possible_node_hours * 100
        logger.info(f"job_count: {completed + len(running)}, idle_node_hours = {idle_node_hours:.0f} / {possible_node_hours:.0f} ({idle_percentage:.2f}%)")


    def jobs_to_pandas(self, jobs: list[dict]):
        dtypes = {
            'slurm_version': 'string',
            'job_id': 'string',
            'account': 'string',
            'group': 'string',
            'user': 'string',
            'name': 'string',
            'working_directory': 'string',
            'partition': 'string',
            'time_limit': 'Float64',
            'constraints': 'string',
            'mcs': 'string',
            'time_submission': 'datetime64[us, UTC]',
            'time_eligible': 'datetime64[us, UTC]',
            'time_start': 'datetime64[us, UTC]',
            'time_end': 'datetime64[us, UTC]',
            'time_elapsed': 'Float64',
            'node_count': 'Int64',
            'node_ranges': 'string',
            'xnames': 'object',
            'state_current': 'string',
            'state_reason': 'string',
            'batch_time_start': 'datetime64[us, UTC]',
            'batch_time_end': 'datetime64[us, UTC]',
            'batch_time_elapsed': 'Float64',
            'batch_state': 'string',
            'batch_exit_code_return_code': 'Int64',
            'batch_exit_code_status': 'string',
            'allocation_id': 'string',
            'time_snapshot': 'datetime64[us, UTC]',
            'node_hours': 'Float64',
            'stats_telemetry_node_hours': 'Float64',
            **{f: "Float64" for f in self.stat_ranges.keys()},
        }
        return pd.DataFrame(jobs, columns=[*dtypes.keys()]).astype(dtypes)


    def generate_parquets(self, start: datetime, end: datetime, out: Path):
        jobs = self.generate_jobs(start, end)

        for day, day_jobs in itertools.groupby(jobs, lambda j: j['time_start'].date()):
            dest = out / f"date={day.isoformat()}/data.parquet"
            logger.info(f"Generating {dest}...")
            dest.parent.mkdir(parents = True, exist_ok = True)
            df = self.jobs_to_pandas(list(day_jobs))
            df.to_parquet(dest, engine = "pyarrow", index = False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description = __doc__.strip(),
        # By default argparse allows prefixes of options which is an issue for backwards compatibility
        allow_abbrev = False,
        formatter_class = argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--start", type = datetime.fromisoformat, required = False,
                         help = "Default: 1st of the month, 2 months before --end's month.")
    parser.add_argument("--end", type = datetime.fromisoformat, required = False,
                         help = "Default: now.")
    parser.add_argument("--total-nodes", type = int, required = False)
    parser.add_argument("--stats", type = Path, required = False)
    parser.add_argument("--seed", type = int, required = False)
    parser.add_argument("--out", type = Path, required = True)
    args = parser.parse_args()

    if args.end is None:
        args.end = datetime.now(timezone.utc)
    if args.start is None:
        # 1st of the month, 2 months back from --end's month, so the window
        # covers --end's month plus the 2 before it ("last 3 months").
        year, month = args.end.year, args.end.month - 2
        while month < 1:
            month += 12
            year -= 1
        args.start = datetime(year, month, 1, tzinfo = timezone.utc)

    gen_args = {}
    if args.total_nodes:
        gen_args['total_nodes'] = args.total_nodes
    if args.stats:
        gen_args['stats'] = json.loads(Path(args.stats).read_text())
    if args.seed:
        gen_args['seed'] = args.seed

    gen = RandomJobGenerator(**gen_args)
    gen.generate_parquets(args.start, args.end, args.out)

