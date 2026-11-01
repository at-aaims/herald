"""
inference_test.py - Test the inference pipeline for job prediction
"""
import pytest
from .regression import jobstat_inference


@pytest.mark.integration
def test_jobstat_inference():
    output_feature = ['stats_total_node_energy','stats_total_gpu_energy']
    user_input = {
        'domain': ['STF', 'CFD'], 
        'node_count': [1024, 2048], 
        'time_elapsed': [7200], 
        'utilization_type': ['cpu', 'gpu'] 
    }

    result = jobstat_inference(user_input, output_feature)

    # See if we did get something from the inference
    assert result is not []
    assert len(result) > 0

    # Test the shape of the first element
    for entry in result:
        assert "domain" in entry
        assert "node_count" in entry
        assert "time_elapsed" in entry
        assert "utilization_type" in entry
        assert "prediction" in entry

        # All output features should be found in the predictions
        for feature in output_feature:
            assert feature in entry["prediction"]

        # All predictions should be in what we have asked for
        for feature in entry["prediction"].keys():
            assert feature in output_feature

