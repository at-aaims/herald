"""
src/site/ornl/frontier/db_test.py - Frontier (ORNL) system specific data access methods
"""
import os
import pytest
from sqlalchemy.sql import text
from .db import get_engine, create_sql_database
from .db import (
    JOBSUMMARY_DATA,
    META_BASE,
)


def no_datasets():
    """Condition that tests whether we have all datasets"""
    return not os.access(JOBSUMMARY_DATA, os.F_OK)


@pytest.fixture
def tmp_engine(tmpdir):
    """
    A Fixture that creates a temporary SQLAlchemy Engine object
    """
    db_filepath = tmpdir.join("sql.db")
    engine = get_engine(db_filepath=str(db_filepath))
    yield engine, db_filepath
 

@pytest.mark.integration
@pytest.mark.skipif(no_datasets(), reason="all datasets are not accessible")
def test_get_engine(tmp_engine):
    """Test whether the views to the parquet files are created properly"""
    engine, db_filepath = tmp_engine

    # The Engine object should know the db path
    # but the DB shouldn't be created yet.
    assert str(engine.url) == f"duckdb:///{str(db_filepath)}"


@pytest.mark.integration
@pytest.mark.skipif(no_datasets(), reason="all datasets are not accessible")
def test_create_sql_database():
    """
    Test whether we can create the SQLDatabase object with all the necessary
    tables registered as views.  This test actually tests the fixture
    """
    db = create_sql_database()

    # Check whether we can actually access the tables we intend
    with db._engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM jobstat LIMIT 10"))
        rows = result.fetchall()
        assert len(rows) > 0


def test_import_col_desc_pairs_basic():
    """
    Test whether we can import simple column description pairs
    """
    from .db import import_simple_col_desc_pairs

    # Get the column description pairs and do basic tests
    result = import_simple_col_desc_pairs(META_BASE / "desc_job_pred_var_description.csv") 
    assert len(result) > 0
    assert isinstance(result, dict)
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in result.items())
    assert 'project' in result


def test_import_col_desc_pairs_case_different_column_key():
    """
    Test whether we can import simple column description pairs
    """
    from .db import import_simple_col_desc_pairs

    # Get the column description pairs and do basic tests
    result = import_simple_col_desc_pairs(META_BASE / "desc_science_domains.csv", "Domain", "Description") 
    assert len(result) > 0
    assert isinstance(result, dict)
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in result.items())
    assert 'PHY' in result



def test_import_table_desc_all():
    from .db import import_table_desc_all
    table_desc_all= import_table_desc_all()
    assert table_desc_all is not None
    lines = table_desc_all.split('\n')

    # # At least check that we have the right number of tables and their primary keys
    TOTAL_TABLES = 4
    TOTAL_RELATIONS = 2
    assert len([l for l in lines if 'PRIMARY' in l]) == TOTAL_TABLES
    assert len([l for l in lines if 'REFERENCES' in l]) == TOTAL_RELATIONS