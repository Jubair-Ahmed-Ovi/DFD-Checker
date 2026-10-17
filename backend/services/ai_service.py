
import time
import os
import json
import base64

from google import genai
from .json_validator import GEMINI_SCHEMA


SYSTEM_PROMPT = """
You are an expert Data Flow Diagram (DFD) image analyzer.

Analyze the uploaded image and return the DFD in the
required JSON structure.

RULES:

1. Identify external entities, processes, data stores,
   data flows, and DFD levels 0, 1, and 2 when visible.

2. ID formats:
   External entities: E1, E2, E3...
   Processes: P0, P1, P2...
   Level 2 processes: P3.1, P3.2...
   Data stores: D1, D2, D3...
   Data flows: F1, F2, F3...

3. The final JSON must contain exactly:
   "diagram_type": "DFD"

4. source and destination MUST contain IDs, never names.

   Correct:
   {"source": "E1", "destination": "P1"}

5. Level 0:
   Main process normally uses P0.
   parent_process must be an empty string.

6. Level 1:
   parent_process must reference P0.

7. Level 2:
   Processes must reference their Level 1 parent.
   Example: P3.1 has parent_process "P3".
   expanded_process must contain "P3".

8. Preserve the direction of every visible arrow.

9. The data field contains the label on the arrow.
   If no label is visible, use an empty string.

10. Do not invent entities, processes, data stores,
    flows, or DFD levels that are not supported by the image.

11. Each flow's source and destination must reference
    an existing node in the appropriate diagram level.

12. Keep all required fields in the JSON structure.

13. Return only a valid JSON object.
    No Markdown, comments, or explanations.
"""


def extract_dfd(image_path: str) -> dict:

    # -----------------------------------------------------
    # 1. Load API key and model configuration
    # -----------------------------------------------------

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. "
            "Add it to your project .env file."
        )

    primary_model = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.6-flash"
    )

    fallback_model = os.getenv(
        "GEMINI_FALLBACK_MODEL",
        "gemini-3.5-flash-lite"
    )

    models = list(dict.fromkeys([
        primary_model,
        fallback_model
    ]))

    client = genai.Client(api_key=api_key)

    # -----------------------------------------------------
    # 2. Read the image
    # -----------------------------------------------------

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    image_base64 = base64.b64encode(
        image_bytes
    ).decode("utf-8")

    input_data = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT
        },
        {
            "type": "image",
            "data": image_base64,
            "mime_type": "image/png"
        }
    ]

    # -----------------------------------------------------
    # 3. Retry and fallback between configured models
    # -----------------------------------------------------

    interaction = None
    last_error = None

    for model_name in models:

        print(f"Trying Gemini model: {model_name}")

        for attempt in range(3):

            try:
                interaction = client.interactions.create(
                    model=model_name,
                    input=input_data,
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": GEMINI_SCHEMA
                    }
                )

                print(
                    f"Gemini response received from {model_name}"
                )
                break

            except Exception as exc:

                last_error = exc
                message = str(exc).lower()

                # Errors that may resolve by retrying
                retryable = any(term in message for term in [
                    "503",
                    "service_unavailable",
                    "high demand",
                    "429",
                    "rate_limit",
                    "500",
                    "502",
                    "504",
                    "timeout",
                    "temporarily"
                ])

                # A model name that is unavailable
                unavailable = any(term in message for term in [
                    "404",
                    "not_found",
                    "not found",
                    "no longer available"
                ])

                if unavailable:
                    print(
                        f"{model_name} is unavailable. "
                        "Trying the fallback model."
                    )
                    break

                if retryable and attempt < 2:

                    delay = 2 ** (attempt + 1)

                    print(
                        f"Temporary error. Retrying in "
                        f"{delay} seconds "
                        f"(attempt {attempt + 1}/3)."
                    )

                    time.sleep(delay)
                    continue

                if retryable:
                    print(
                        f"{model_name} failed after 3 attempts."
                    )
                    break

                raise RuntimeError(
                    f"Gemini API request failed: {exc}"
                ) from exc

        if interaction is not None:
            break

    if interaction is None:
        raise RuntimeError(
            "Gemini conversion failed for all configured "
            f"models. Last error: {last_error}"
        )

    # -----------------------------------------------------
    # 4. Extract response text
    # -----------------------------------------------------

    output_text = getattr(
        interaction,
        "output_text",
        None
    )

    if not output_text or not output_text.strip():

        print("Gemini returned no text.")
        print("Response:", interaction)

        raise RuntimeError(
            "Gemini returned an empty response. "
            "Try another image or model."
        )

    output_text = output_text.strip()

    # -----------------------------------------------------
    # 5. Remove Markdown fences if present
    # -----------------------------------------------------

    if output_text.startswith("```"):

        lines = output_text.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        output_text = "\n".join(lines).strip()

    # -----------------------------------------------------
    # 6. Parse JSON
    # -----------------------------------------------------

    try:
        result = json.loads(output_text)

    except json.JSONDecodeError as exc:

        print("Invalid Gemini JSON response:")
        print(output_text)

        raise RuntimeError(
            f"Gemini returned invalid JSON: {exc}"
        ) from exc

    if not isinstance(result, dict):
        raise RuntimeError(
            "Gemini response must be a JSON object."
        )

    # -----------------------------------------------------
    # 7. Normalize fixed fields
    # -----------------------------------------------------

    result["diagram_type"] = "DFD"

    metadata = result.get("metadata")

    if not isinstance(metadata, dict):
        metadata = {}
        result["metadata"] = metadata

    metadata["created_from"] = "image"

    if not isinstance(
        metadata.get("confidence"),
        (int, float)
    ):
        metadata["confidence"] = 0.0

    if not isinstance(metadata.get("notes"), str):
        metadata["notes"] = ""

    # Level 0 uses null for parent_process in final JSON.
    for level in result.get("levels", []):

        if level.get("level") == 0:
            for process in level.get("processes", []):
                process["parent_process"] = None

        # Remove expanded_process from Level 0 and Level 1.
        if level.get("level", 0) < 2:
            level.pop("expanded_process", None)

    return result
