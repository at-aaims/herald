"""
src/site/ornl/frontier/db_test.py - Frontier (ORNL) system specific data access methods
"""
import os, csv
from typing import List
from textwrap import dedent
from os.path import join
from pathlib import Path
from sqlalchemy import create_engine, Engine
from src.config import get_settings
from src.tools.sql import JSONSQLDatabase
from src.sql.sql import make_table_description
import pandas as pd

# Load settings
settings = get_settings()


# Key directories
PRIV_BASE = Path(settings.data_priv_base)
META_BASE = Path(__file__).parent / "metadata"


# Job summary table
JOBSUMMARY_DATA = PRIV_BASE / "ornl" / "frontier" / "jobsummary"
JOBSUMMARY_DATA_DESC = META_BASE / "desc_job_summary.csv"


#
# Import tables into the namespace
#


def import_db_job_stat(conn) -> dict:
    """
    Read the jobstat table

    Map the parquet files for the jobsummary_data to the jobstat table for duckdb
    """
    conn.exec_driver_sql(f"CREATE VIEW IF NOT EXISTS jobstat AS SELECT * FROM '{JOBSUMMARY_DATA}/*/*.parquet';")
    return {"jobstat": JOBSUMMARY_DATA}


def import_db_project_description(conn) -> dict:
    """
    Read the project_description table
    """
    conn.exec_driver_sql(f"CREATE VIEW IF NOT EXISTS project_description AS SELECT DISTINCT account, SUBSTRING(account, 1, 3) as project_code, SUBSTRING(account, 1, 3) as project_domain FROM jobstat")
    return {"project_description": JOBSUMMARY_DATA}


def import_db_sched_policy(conn) -> dict:
    """
    Read the scheduling_policy table
    """
    conn.exec_driver_sql(f"CREATE VIEW IF NOT EXISTS scheduling_policy AS SELECT * FROM '{META_BASE}/table_scheduling_policy.csv';")
    return {"scheduling_policy": META_BASE / "table_scheduling_policy.csv"}


def import_db_users(conn) -> dict:
    """
    Read the users table
    """
    conn.exec_driver_sql(f"CREATE VIEW IF NOT EXISTS users AS SELECT DISTINCT user , 'user description' as description FROM jobstat;")
    return {"project_description": JOBSUMMARY_DATA}


def import_all(conn):
    """Import all tables using a transaction"""
    ret = {}
    ret.update(import_db_job_stat(conn))
    ret.update(import_db_project_description(conn))
    ret.update(import_db_sched_policy(conn))
    ret.update(import_db_users(conn))
    return ret

#
# Import table column & descriptions pair
#

def import_simple_col_desc_pairs(file_path: str, column_key='Column', description_key='Description') -> dict:
    """
    Read a CSV file and return a dictionary of column names and their descriptions

    Use for the most simple column description pairs that are needed to fill in LLM contexts
    """
    # Read the CSV file using the standard library
    result = {}
    with open(file_path, mode='r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # Extract the column name and description
            column_name = row[column_key]
            description = row[description_key]
            # Add to the result dictionary
            result[column_name] = description
    return result


def import_job_pred_variable_description() -> dict:
    """
    Read the job prediction variable description table

    FIXME: Potential overlap with the desc_jobstat.csv file - need a way to 
    limit the columns to the ones we are interested in
    """
    # Read the CSV file
    return import_simple_col_desc_pairs(META_BASE / "desc_job_pred_var_description.csv")


def import_science_domain_description() -> dict:
    """
    Read the science domain description table
    """
    # Read the CSV file using the standard library
    return import_simple_col_desc_pairs(META_BASE / "desc_science_domains.csv",
                                        column_key="Domain", description_key="Description")


def import_table_desc_all() -> str:
    """
    Import all table descriptions
    """
    result = []
    tables = [
        {
           'table_name': 'jobstat',
           'relationships': [
                "table: 'project_description', key: 'account'"
                "table: 'users', key: 'user'"
            ],
        },
        {
           'table_name': 'project_description',
           'relationships': []
        },
        {
           'table_name': 'scheduling_policy',
           'relationships': []
        },
        {
           'table_name': 'users',
           'relationships': []
        },
    ]
    for args in tables:
        metadata_file = META_BASE / f"desc_{args['table_name']}.csv"
        result.append(make_table_description(**args, metadata_file=metadata_file))
    return "\n".join(result)


def get_engine(db_filepath: str|None=None,
                  config: dict={},
                  read_only=False) -> Engine:
    """
    Connect to the database

    The URI defaults to duckdb:///{settings.scratch_base}/ornl/frontier/sql.db however can be overridden by
    db_filepath pointing to a specific *.db file existing or to be created.

    If the path is relative, the settings.scratch_base path will be prefixed.
    """
    # Overlay connect args
    db_connect_args = {
        'read_only': read_only,
        'config': {
            'memory_limit': '2000mb'
        }
    }
    db_connect_args["config"].update(config)

    # Setup the target DB URI - defaults to an in-memory DB
    if db_filepath:
        # Create the base directory
        if db_filepath.startswith('/'):
            pass
        elif db_filepath.startswith('./'):
            db_filepath = join(settings.scratch_base, db_filepath[2:])
        else:
            # If we have a relative directory, anchor it to the settings
            db_filepath = join(settings.scratch_base, "ornl", "frontier" , db_filepath)
    else:
        db_filepath = join(settings.scratch_base, "ornl", "frontier" , "sql.db")

    # Create the directories required before creating
    os.makedirs(os.path.dirname(db_filepath), exist_ok=True)
    db_uri = f"duckdb:///{db_filepath}"

    return create_engine(db_uri, connect_args=db_connect_args)


def create_sql_database():
    """
    Factory for the SQLDatabase Object
    """
    engine = get_engine()

    with engine.connect() as conn:
        with conn.begin():
            _ = import_all(conn)

    return JSONSQLDatabase(engine,
        max_result_length = settings.query_output_limit,
        view_support = True,
    )


def render_sql_prompt(
    *,
    question: str,
    conversation: list[dict] | None = None,
    dialect: str = "duckdb",
) -> list[dict]:
    """Render Frontier's SQL prompt as OpenAI chat-completion messages."""
    create_table_statements = import_table_desc_all()
    system = f"You are an expert {dialect} SQL programmer."
    user = dedent(f"""
        ### Task
        Generate a SQL query to answer [question]{question}[/question]

        ### Instructions
        - Create a syntactically correct {dialect} query to run.
        - If the question cannot be answered given the database schema, return "I do not know".
        - The given database schema is of Frontier system.
        - Recall the date format is YYYY-MM-DD
        - Please do not use "TO_CHAR" or "DATE" sql function, instead use "DATE_TRUNC" function.
        - For AVG function remember it can not be executed for time interval data, instead first use DATEDIFF function and then then use AVG function.
        - Datetime fields are stored in UTC already — do NOT apply any timezone conversion (no CONVERT_TZ, no timezone() calls) when comparing, filtering, or grouping by them.
        - Be careful of the upper bound and lower bound when comparing datetime fields.
        - Return only 'SQL' statement, no explanation.

        ### Database Schema
        The query will run on a database with the following schema:
        {create_table_statements}

        ### Task
        Given the database schema, write a {dialect} SQL query that answers: {question}
    """).strip()

    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    if conversation:
        messages.extend(conversation)
    return messages
