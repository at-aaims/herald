"""
src/job_pred/regression.py — Inference pipeline for job prediction.

"""
import json
import re
from textwrap import dedent
from loguru import logger
import pandas as pd
import numpy as np
import joblib
import torch
from pathlib import Path
from openai import AsyncOpenAI
from .model import RegressionModel
from src.utils.utils import normalize_np


# Paths to the model files
model_data_dir = Path(__file__).parent / 'model_data'
ENCODER_FILENAME = model_data_dir / 'encoder.joblib'
INPUT_SCALERS_FILENAME = model_data_dir / 'input_scalers.joblib'
OUTPUT_SCALERS_FILENAME = model_data_dir / 'output_scalers.joblib'
DECISION_TREE_FILENAME = model_data_dir / 'decision_tree.joblib'
MODEL_FILENAME = model_data_dir / 'model_latest.pth'
TEST_LOSS_FILENAME = model_data_dir / "test_loss.txt"

# Every artifact jobstat_inference needs. A sample model (fabricated
# synthetic data, not real Frontier measurements — see
# model_data/README.md) ships by default, but these files could be
# missing — deleted to drop in a real model, a minimal checkout, etc. —
# so callers should check models_available() before invoking inference
# and surface a clear message instead of a raw FileNotFoundError from
# deep inside joblib/torch.
REQUIRED_MODEL_FILES = [
    ENCODER_FILENAME, INPUT_SCALERS_FILENAME, OUTPUT_SCALERS_FILENAME,
    DECISION_TREE_FILENAME, MODEL_FILENAME,
]


def models_available() -> bool:
    """True iff every trained model artifact job prediction needs is present."""
    return all(p.exists() for p in REQUIRED_MODEL_FILES)

INPUT_FEATURE_DEFAULTS = {
    "utilization_type": ['cpu','gpu'],
    "time_elapsed": [3600, 43200, 86400],
    "node_count": [1, 1024, 4096, 9000],
    "domain": ["CSC", "MAT", "PHY"]
}

def _handle_user_input(user_input, output_feature_list_all, output_feature):
    """
    Handles user input with potential combinations and prepares data for prediction.

    Args:
        user_input: Dictionary containing user input features (domain, node_count, time_elapsed, utilization_type).
        output_feature_list_all: List of all possible output features.
        output_feature: List of desired output features.

    Returns:
        List of dictionaries, each representing a combination of input features 
        and corresponding indices of output features.
    """

    user_input = {
        k: v if v else INPUT_FEATURE_DEFAULTS[k]
        for k, v in user_input.items()
    }

    input_combinations = []
    for domain in user_input['domain'] if isinstance(user_input['domain'], list) else [user_input['domain']]:
        for node_count in user_input['node_count'] if isinstance(user_input['node_count'], list) else [user_input['node_count']]:
            for time_elapsed in user_input['time_elapsed'] if isinstance(user_input['time_elapsed'], list) else [user_input['time_elapsed']]:
                for utilization_type in user_input['utilization_type']:
                    input_combinations.append({
                        'domain': domain,
                        'node_count': node_count,
                        'time_elapsed': time_elapsed,
                        'utilization_type': utilization_type
                    })

    input_data = []
    for combination in input_combinations:
        indices_to_pass = [output_feature_list_all.index(feature) for feature in output_feature]
        input_data.append({
            'input_dict': combination,
            'indices': indices_to_pass
        })

    return input_data


def _encode_user_input(encoder, user_input_dict, categorical_cols, numerical_cols):
    """Encode user input for the regression model
    """
    try:
        user_input_df = pd.DataFrame([user_input_dict])

        # 1. Categorical Encoding:
        encoded_cat = encoder.transform(user_input_df[categorical_cols])
        encoded_cat_df = pd.DataFrame(encoded_cat, columns=encoder.get_feature_names_out(categorical_cols))

        # 2. Numerical Columns:
        numerical_values = user_input_df[numerical_cols].values
        numerical_df = pd.DataFrame(numerical_values, columns=numerical_cols)

        # 3. Concatenate:
        final_df = pd.concat([numerical_df,encoded_cat_df], axis=1)
        return final_df.values

    except KeyError as e:
        print(f"Error: Missing column in user input: {e}")
        return None
    except ValueError as e:
        print(f"Error during encoding: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None


def _extract_json_info(text):
    """Extracts project, X, and Y information, from LLM text."""

    try:
        project_match = re.search(r'"project"\s*:\s*"?([^",{}]+)"?', text)
        project = project_match.group(1).strip() if project_match else None
        if project == "null":
            project = None

        x_match = re.search(r'"X"\s*:\s*{(.*?)}', text, re.DOTALL)
        x_str = x_match.group(1).strip() if x_match else "{}"
        x = {}

        # Improved X parsing: Use json.loads to parse the entire X object string
        x_parsed = json.loads("{" + x_str + "}") # Load the x string as a json
        for key in INPUT_FEATURE_DEFAULTS: # ignore extra keys
            if not x_parsed.get(key): # normalize missing, null, and []
                x[key] = None
            elif not isinstance(x_parsed[key], list): # Convert single items to list
                x[key] = [x_parsed[key]]
            else:
                x[key] = x_parsed[key]

        if all((v is None) for v in x.values()):
            raise Exception("No input features found")

        y_match = re.search(r'"Y"\s*:\s*\[(.*?)\]', text)
        y_str = y_match.group(1).strip() if y_match else "[]"
        y = [item.strip().replace('"','') for item in y_str.split(',')] if y_str else []

        return {"project": project, "X": x, "Y": y}
    except Exception as e:
        print(f"Error extracting information: {e}")
        return None


def _load_and_predict_pt(
    user_input, categorical_cols, numerical_cols, 
    filename=ENCODER_FILENAME, input_scalers_filename=INPUT_SCALERS_FILENAME,
    model_filename=MODEL_FILENAME, output_scalers_filename=OUTPUT_SCALERS_FILENAME,
):
    """Loads the encoder, input scalers, output scalers, and model, and predicts the output.

    Args:
        user_input: Dictionary containing user input features (domain, node_count, time_elapsed, utilization_type).
        categorical_cols: List of categorical columns.
        numerical_cols: List of numerical columns.
        filename: Path to the encoder file.
        input_scalers_filename: Path to the input scalers file.
        output_scalers_filename: Path to the output scalers file.

    Returns:
        List of predictions.
    """
    loaded_encoder = joblib.load(filename)
    input_scalers = joblib.load(input_scalers_filename)
    output_scalers = joblib.load(output_scalers_filename)

    # Load the PyTorch model
    input_dim = len(numerical_cols) + len(loaded_encoder.get_feature_names_out(categorical_cols)) # Get input dimension
    output_dim = len(output_scalers.mean_) # Get output dimension
    model = RegressionModel(input_dim, output_dim) # Initialize model
    model.load_state_dict(torch.load(model_filename)) # Load state dict
    model.eval()  # Set to evaluation mode

    input_feature_names=numerical_cols+categorical_cols

    encoded_input = _encode_user_input(loaded_encoder, user_input, categorical_cols, numerical_cols)
    if encoded_input is not None:
        for col_name in numerical_cols:
            scaler = input_scalers[col_name]
            col_index = input_feature_names.index(col_name)
            value_to_scale = encoded_input[0, col_index].reshape(1, -1)

            if np.isnan(value_to_scale):
                if hasattr(scaler, 'mean_'):
                    replacement_value = scaler.mean_
                elif hasattr(scaler, 'median_'):
                    replacement_value = scaler.median_
                else:
                    replacement_value = 0

                value_to_scale = replacement_value

            value_to_scale = np.array(value_to_scale).reshape(1, -1)
            scaled_value = scaler.transform(value_to_scale)
            encoded_input[0, col_index] = scaled_value[0, 0]

        # Convert to PyTorch tensor
        encoded_input_tensor = torch.tensor(encoded_input, dtype=torch.float32)

        with torch.no_grad():
            prediction_scaled = model(encoded_input_tensor) # Pass tensor input
            prediction_scaled = prediction_scaled.numpy() # Convert back to numpy
            prediction = output_scalers.inverse_transform(prediction_scaled)

        return prediction
    else:
        print("Could not encode user input.")
        return None


def _load_and_predict_dt(
    user_input, categorical_cols, numerical_cols, 
    filename=ENCODER_FILENAME, input_scalers_filename=INPUT_SCALERS_FILENAME,
    model_filename=DECISION_TREE_FILENAME, output_scalers_filename=OUTPUT_SCALERS_FILENAME,
):
    loaded_encoder = joblib.load(filename)
    input_scalers = joblib.load(input_scalers_filename)
    output_scalers = joblib.load(output_scalers_filename)

    # Load the Decision Tree model
    model = joblib.load(model_filename)

    input_feature_names=numerical_cols+categorical_cols

    encoded_input = _encode_user_input(loaded_encoder, user_input, categorical_cols, numerical_cols)

    if encoded_input is not None:
        for col_name in numerical_cols:
            scaler = input_scalers[col_name]
            col_index = input_feature_names.index(col_name)
            value_to_scale = encoded_input[0, col_index].reshape(1, -1)

            if np.isnan(value_to_scale):
                if hasattr(scaler, 'mean_'):
                    replacement_value = scaler.mean_
                elif hasattr(scaler, 'median_'):
                    replacement_value = scaler.median_
                else:
                    replacement_value = 0
                
                value_to_scale = replacement_value

            value_to_scale = np.array(value_to_scale).reshape(1, -1)
            scaled_value = scaler.transform(value_to_scale)
            encoded_input[0, col_index] = scaled_value[0, 0]

        prediction_scaled = model.predict(encoded_input)
        prediction = output_scalers.inverse_transform(prediction_scaled)

        return prediction
    else:
        print("Could not encode user input.")
        return None


def jobstat_inference(user_input: dict, output_feature: list[str]):
    """Jobstat inference function

    Based on a structured user input, predict the values of a certain field

    Args:
        user_input: dict - A structured input of the job chracteristics we're predicting
        output_feature: list[str] - A list of statistics we're predicting
    Returns:
        dictionary of the predictions

    Examples
        input: one single input that is parsed from a natural language input
            user_input = {
                'domain': ['STF', 'CFD'], 
                'node_count': [1024, 2048], 
                'time_elapsed': [7200], 
                'utilization_type': ['cpu', 'gpu'] 
            }

        Output data example that predicts various aspects of a job
            results = [
                {
                    'domain': 'STF',
                    'node_count': 1024,
                    'time_elapsed': 7200,
                    'utilization_type': 'cpu',
                    'prediction': {
                        'stats_total_node_energy': 1232124.0,
                        'stats_total_gpu_energy': 129127123,
                    }
                },
                ...
            ]
    """
    # FIXME: Static values associated to Frontier that needs to come from elsewhere
    output_feature_list_all = ['stats_node_power_node_max', 'stats_node_power_node_mean', 
                            'stats_node_power_node_stddev', 'stats_cpu_memory_power_node_max',
                            'stats_gpu_power_node_max', 'stats_gpu_power_node_mean',
                            'stats_gpu_power_node_stddev', 'stats_node_temp_node_max',
                            'stats_node_temp_node_stddev', 'stats_total_node_energy',
                            'stats_total_node_energy_node_max', 'stats_total_node_energy_node_mean',
                            'stats_total_cpu_memory_energy', 'stats_total_gpu_energy',
                            'stats_total_gpu_energy_node_max', 'stats_total_gpu_energy_node_mean']
    numerical_cols = ['time_elapsed', 'node_count']
    categorical_cols = ['utilization_type', 'domain']

    assert "domain" in user_input
    assert "node_count" in user_input
    assert "time_elapsed" in user_input
    assert "utilization_type" in user_input

    prepared_data = _handle_user_input(user_input, output_feature_list_all, output_feature)
    indices_to_pass = [output_feature_list_all.index(feature) for feature in output_feature] 

    #
    # Example of "prepared_data"
    #
    # [{'indices': [9, 13],
    # 'input_dict': {'domain': 'STF',
    #                 'node_count': 1024,
    #                 'time_elapsed': 7200,
    #                 'utilization_type': 'cpu'}},
    # {'indices': [9, 13],
    # 'input_dict': {'domain': 'STF',
    #                 'node_count': 1024,
    #                 'time_elapsed': 7200,
    #                 'utilization_type': 'gpu'}},
    # {'indices': [9, 13],
    # 'input_dict': {'domain': 'STF',
    #                 'node_count': 2048,
    #                 'time_elapsed': 7200,
    #                 'utilization_type': 'cpu'}}]
    #

    # Now you can iterate through prepared_data and call your prediction function
    # TODO: Prepare this as an output dictionary and ultimately a string that can be exposed to an LLM for synthesis
    results = []
    for data in prepared_data:
        prediction_result_pt = _load_and_predict_pt(data['input_dict'], categorical_cols, numerical_cols) 
        prediction_result_dt = _load_and_predict_dt(data['input_dict'], categorical_cols, numerical_cols)

        # Create a prediction entry and passthrough the input_dictionary
        entry = {}
        entry.update(data["input_dict"])

        # Create an output
        prediction = {}
        if prediction_result_pt is not None and prediction_result_dt is not None:
            for i in indices_to_pass:
                # energy feature indices: 9-15 for decision tree
                X = output_feature_list_all[i]
                if i >= 9:
                    Y = prediction_result_dt[0][i]
                else:
                    Y = prediction_result_pt[0][i]
                prediction[X] = Y
        entry["prediction"] = prediction
        results.append(entry)
    return results


async def extract_relevant_features_from_query(
    question: str, *,
    client: AsyncOpenAI,
    model_name: str,
    feature_list_str: str|None=None,
    domain_list_str: str|None=None,
) -> tuple[dict|None, dict]:
    """Extract structured feature variables from a natural-language question.

    Returns:
        (features_dict_or_None, usage_dict)
    """
    """Generates a prompt for Llama and parses the JSON response to identify relevant feature variables 
       and their values based on a user-provided question.

        Args:
            question (str): The user-provided question that needs to be translated into feature variables.
            feature_list_str (str | None, optional): A string containing a list of available feature variables 
                and their descriptions. If None, a default list specific to Frontier will be imported. Defaults to None.
            domain_list_str (str | None, optional): A string containing a list of available science domains 
                and their descriptions. If None, a default list specific to Frontier will be imported. Defaults to None.
            generator (Pipeline | None, optional): A text generation pipeline (e.g., from Hugging Face) used to 
                generate the response based on the prompt. Defaults to None.
        Returns:
            dict: A dictionary containing the parsed JSON response with input features ("X") and output variables ("Y").
            None: if there was an error or the question was bad (not related to HPC compute)
    """

    # FIXME: This is Frontier specific - make this generic
    if domain_list_str is None:
        from src.site.ornl.frontier.db import import_science_domain_description
        domains = import_science_domain_description()
        domain_list_str = "\n".join([f"* `{k}`: {v}" for k, v in domains.items()])

    # FIXME: This is Frontier specific - make this generic
    if feature_list_str is None:
        from src.site.ornl.frontier.db import import_job_pred_variable_description
        features = import_job_pred_variable_description()
        feature_list_str = "\n".join([f"* `{k}`: {v}" for k, v in features.items()])

    # The primary prompt — works with Meta-Llama-3.1-8B-Instruct or similar.
    # Serve the model via vLLM and use type='vllm' in ModelConfig.
    prompt = dedent(f"""
        ## Prompt for Feature Variable Translation (Regression Model)

        **Instructions:** 
        You are a helpful assistant that translates user questions related to HPC compute jobs into feature variables suitable for input into
        a regression model.  You will receive a question and a list of available feature variables with their descriptions.  Your task is to
        identify the relevant feature variables *and their values as provided in the question*.

        Input features are fixed values: [domain, time_elapsed, node_count, utilization_type]. 
        If 'utilization_type' not found in question set it to null.
        If 'time_elapsed' is missing in question set it to null.
        If 'node_count' is missing in question set it to null.
        For science domains match it to the closest value in {domain_list_str}, only choose value from this list, do not add values that are
        not here. Multiple values can be added if they match the domain. Add multiple values doing substring match.
        If domain is unspecified, set it to null.
        For output variables match it to the closest feature in {feature_list_str}. If 'mean/max' is not specified in question, return both.
        If 'node/gpu' 'power/energy' is not specified in question, return relevant 'node' 'power/energy' feature.
        
        If you cannot infer any feature variables from the question because it is NOT relevant to HPC compute jobs, then return an empty
        JSON string `{{}}`.

        Return the answer in the following JSON format:

        ```json
        {{
        "project": "project_name",  // If project is mentioned, otherwise omit
        "X": {{  // Input features with values from the question
            "feature_1": value_1,
            "feature_2": value_2,
            ...
        }},
        "Y": ["output_variable_1", "output_variable_2", ...] // Output variable(s)
        }}
        ```

        When returning final output json do not include the comments in respose starting with //

        **Available Feature Variables:**

        {feature_list_str}

        **Available Domain Names:**

        {domain_list_str}

        **Few-Shot Examples:**

        **Question 1:** For a job from science domain 'STF', project is 12345 and on 200 nodes, will run for 2 hours, will consume how much energy?

        ```json
        {{
            "project": 12345,
            "X": {{
                "domain": "STF",
                "node_count": 200,
                "time_elapsed": 7200,
                "utilization_type": null
            }},
            "Y": ["stats_total_node_energy"]  // Assuming this is the total energy feature
        }}
        ```
        Here, time_elapsed is converted to seconds. utilization_type is not specified in the question
        so it is left null.

        **Question 2:** What would be the maximum temperature for a typical job from certain domain with 10 nodes?

        ```json
        {{
            "X": {{
                "domain": null,
                "node_count": 10,
                "time_elapsed": null,
                "utilization_type": null,
            }},
            "Y": ["stats_node_temp_node_max"]
        }}
        ```

        **Question 3:** What is the mean node power for a job in earth science domain with project 67890 and runtime 3600 seconds utilizing gpu?

        ```json
        {{
            "project": 67890,
            "X": {{
                "domain": ["GEO", "CLI", "ATM"],
                "node_count": null,
                "time_elapsed": 3600,
                "utilization_type": "gpu"
            }},
            "Y": ["stats_node_power_node_mean"]
        }}
        ```

        **Question 4:** What is the name of the dog in the movie Benji?

        ```json
        {{}}
        ```
        Here, the question is not related to HPC compute jobs.

        **Your Question:** {question}

        **IMPORTANT:** Return ONLY the JSON object. Do not include explanations, tables, or additional text.
        AI Assistant: ```json
    """).lstrip()

    response = await client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,    # caps JSON output, prevents runaway generation
        temperature=0.1,   # more deterministic parsing
        stop=["\n\n"],
    )
    usage = {
        "input_tokens": (response.usage.prompt_tokens if response.usage else 0) or 0,
        "output_tokens": (response.usage.completion_tokens if response.usage else 0) or 0,
    }
    json_string: str = (response.choices[0].message.content or "").strip()

    try:
        json_string = json_string.removeprefix("```json").removesuffix("```").strip()
        if json_string.startswith("{}"):
            return None, usage
        return _extract_json_info(json_string), usage
    except Exception as e:
        logger.error(f"Job-pred feature extraction failed: {e}")
        logger.trace("Raw generated text: {}", json_string)
        return None, usage


async def run_job_prediction(
    *,
    client: AsyncOpenAI,
    model_name: str,
    question: str,
) -> dict:
    """End-to-end job prediction: extract features from NL, run regression, return results.

    Returns:
        {"features": {...}, "results": [...], "usage": {...}}   on success
        {"error": "...", "usage": {...}}                         on feature-extraction or missing-model failure
    """
    if not models_available():
        return {
            "error": "Job prediction is unavailable: no trained model is installed in this "
                     "build. You'll need to train and add a prediction model first.",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
    features, usage = await extract_relevant_features_from_query(
        question, client=client, model_name=model_name,
    )
    if not features:
        return {
            "error": "Could not extract HPC job features from the question. "
                     "Specify domain, node count, runtime, or utilization type.",
            "usage": usage,
        }
    results = jobstat_inference(features["X"], output_feature=features["Y"])
    # Surfaced to the LLM (this dict becomes the tool's returned JSON), so it
    # naturally gets relayed to the user rather than only living in repo docs
    # someone reading the source would find — see model_data/README.md.
    return normalize_np({
        "features": features,
        "results": results,
        "usage": usage,
        "note": "Sample model trained on fabricated synthetic data, not real "
                "Frontier measurements — illustrative only, not for operational use.",
    })

