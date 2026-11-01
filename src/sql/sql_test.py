"""
src/site/ornl/frontier/db_test.py - Frontier (ORNL) system specific data access methods
"""
from .sql import make_table_description
from src.site.ornl.frontier.db import META_BASE


def test_make_table_description():
    """
    Test whether we can run the telemetry inference on a question
    """
    inputs = [
        {
           'table_name': 'jobstat',
           'relationships': ["table: 'project_description', key: 'account'"]
        },
        {
           'table_name': 'project_description',
           'relationships': []
        },
        {
           'table_name': 'scheduling_policy',
           'relationships': []
        },
    ]

    for args in inputs:
        metadata_file = META_BASE / f"desc_{args['table_name']}.csv"
        table_desc = make_table_description(**args, metadata_file = metadata_file)
        table_desc_lines = table_desc.split('\n')
        assert table_desc_lines is not None
        assert args['table_name'] in table_desc_lines[0]
        assert 'PRIMARY' in table_desc
        if args['relationships']:
            assert 'REFERENCES' in table_desc
        else:
            assert 'REFERENCES' not in table_desc

