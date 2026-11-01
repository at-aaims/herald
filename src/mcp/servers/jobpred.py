"""
src/mcp/servers/jobpred.py — MCP server for HPC job power/energy prediction.

Run standalone:
    python -m src.mcp.servers.jobpred

Or via MCP CLI:
    mcp run src/mcp/servers/jobpred.py
"""
import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "herald-jobpred",
    instructions=(
        "Predict power, temperature, and energy statistics for HPC jobs. "
        "Accepts natural language descriptions of job parameters and returns "
        "regression-model predictions for all requested input combinations."
    ),
)


@mcp.tool()
async def predict_job_stats(question: str) -> str:
    """
    Predict power and energy statistics for one or more HPC job configurations.

    Extracts structured job parameters (domain, node count, runtime,
    utilization type) from natural language, then runs the regression model
    over all combinations of the supplied values.

    Args:
        question: Natural language description of the job(s) to predict.

    Returns:
        JSON string with keys:
          - features: extracted input parameters (X dict and Y output list)
          - results: list of prediction dicts, one per input combination,
                     each containing the input fields plus a 'prediction' dict
          - error: present only when feature extraction fails
    """
    from src.models.configured import get_small_model_client, get_small_model_name
    from src.job_pred.regression import run_job_prediction

    result = await run_job_prediction(
        client=get_small_model_client(),
        model_name=get_small_model_name(),
        question=question,
    )
    return json.dumps(result)


if __name__ == "__main__":
    mcp.run()
