from setuptools import setup, find_packages

setup(
    name='herald-app',
    version='0.1.0',
    packages=find_packages(include=['src', 'src.*', 'pipelines', 'pipelines.*']),
    entry_points={
        'console_scripts': [
            # `epc` (and `epc chat`) removed with the Chainlit deletion —
            # the new stack starts via `make api` + `make frontend`.
            'epc-eval-sql=pipelines.sql_eval.main:cli',
            'epc-eval-chat=pipelines.chat_eval.main:cli',
            'epc-eval-job-pred=pipelines.job_pred.main:cli',
            'epc-eval-rag=pipelines.rag.evaluate:cli',
            'epc-rag-ingest=pipelines.rag.ingest:cli',
        ],
    },
)
