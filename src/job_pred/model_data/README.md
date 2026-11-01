# model_data/

A **sample** job-prediction model — regression weights + decision tree +
encoder/scalers, trained entirely on fabricated synthetic data.

**Not real.** No raw or aggregate Frontier telemetry went into training
these. See `scripts/train_sample_job_pred_model.py` for the exact
generation formulas (base per-component wattage × a GPU/CPU multiplier ×
a small per-domain jitter × noise) — plausible orders of magnitude, not
measurements. `run_job_prediction()` includes a `"note"` field in every
successful response saying as much, so this isn't just documented here —
it's visible in the actual chat response too.

Good enough to make the job-prediction feature demonstrably work (returns
real numbers in sensible ranges, not an error or random noise). Not good
enough to predict anything about an actual job. Swap in a model trained on
real data before using this for anything operational — same five files
(`encoder.joblib`, `input_scalers.joblib`, `output_scalers.joblib`,
`decision_tree.joblib`, `model_latest.pth`), same schema (see
`src/job_pred/regression.py`'s `jobstat_inference()` for the exact input/
output columns), is all `run_job_prediction()` needs to pick it up —
nothing else to wire up.

To regenerate this sample model (e.g. after changing the schema):

```bash
.venv/bin/python scripts/train_sample_job_pred_model.py
```
