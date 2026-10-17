import json
from pathlib import Path

from jsonschema import Draft202012Validator


# =========================================================
# FULL APPLICATION SCHEMA
# =========================================================

SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "schemas"
    / "dfd_schema.json"
)

SCHEMA = json.loads(
    SCHEMA_PATH.read_text(
        encoding="utf-8"
    )
)


# =========================================================
# GEMINI RESPONSE SCHEMA
# =========================================================
#
# IMPORTANT:
#
# Gemini structured output uses its own schema format.
#
# Do NOT use:
#
# "type": ["string", "null"]
#
# Instead, use:
#
# "type": "string"
#
# We handle null values after Gemini responds.
#
# =========================================================

GEMINI_SCHEMA = {
    "type": "object",

    "properties": {

        "project_name": {
            "type": "string"
        },

        "diagram_type": {
            "type": "string"
        },

        "levels": {
            "type": "array",

            "items": {
                "type": "object",

                "properties": {

                    "level": {
                        "type": "integer"
                    },

                    "description": {
                        "type": "string"
                    },

                    "expanded_process": {
                        "type": "string"
                    },

                    "external_entities": {
                        "type": "array",

                        "items": {
                            "type": "object",

                            "properties": {

                                "id": {
                                    "type": "string"
                                },

                                "name": {
                                    "type": "string"
                                },

                                "description": {
                                    "type": "string"
                                }
                            },

                            "required": [
                                "id",
                                "name",
                                "description"
                            ]
                        }
                    },

                    "processes": {
                        "type": "array",

                        "items": {
                            "type": "object",

                            "properties": {

                                "id": {
                                    "type": "string"
                                },

                                "name": {
                                    "type": "string"
                                },

                                "parent_process": {
                                    "type": "string"
                                },

                                "description": {
                                    "type": "string"
                                }
                            },

                            "required": [
                                "id",
                                "name",
                                "parent_process",
                                "description"
                            ]
                        }
                    },

                    "data_stores": {
                        "type": "array",

                        "items": {
                            "type": "object",

                            "properties": {

                                "id": {
                                    "type": "string"
                                },

                                "name": {
                                    "type": "string"
                                },

                                "description": {
                                    "type": "string"
                                }
                            },

                            "required": [
                                "id",
                                "name",
                                "description"
                            ]
                        }
                    },

                    "data_flows": {
                        "type": "array",

                        "items": {
                            "type": "object",

                            "properties": {

                                "id": {
                                    "type": "string"
                                },

                                "source": {
                                    "type": "string"
                                },

                                "destination": {
                                    "type": "string"
                                },

                                "data": {
                                    "type": "string"
                                },

                                "description": {
                                    "type": "string"
                                }
                            },

                            "required": [
                                "id",
                                "source",
                                "destination",
                                "data",
                                "description"
                            ]
                        }
                    }
                },

                "required": [
                    "level",
                    "description",
                    "external_entities",
                    "processes",
                    "data_stores",
                    "data_flows"
                ]
            }
        },

        "metadata": {
            "type": "object",

            "properties": {

                "created_from": {
                    "type": "string"
                },

                "confidence": {
                    "type": "number"
                },

                "notes": {
                    "type": "string"
                }
            },

            "required": [
                "created_from",
                "confidence",
                "notes"
            ]
        }
    },

    "required": [
        "project_name",
        "diagram_type",
        "levels",
        "metadata"
    ]
}

# =========================================================
# NORMALIZE GEMINI OUTPUT
# =========================================================

def normalize_dfd(data: dict) -> dict:
    """
    Normalize Gemini output so that it always matches
    the application's fixed DFD JSON format.
    """

    # =====================================================
    # 1. Force diagram_type to the fixed value
    # =====================================================

    data["diagram_type"] = "DFD"


    # =====================================================
    # 2. Normalize levels
    # =====================================================

    levels = data.get("levels", [])

    for level in levels:

        level_number = level.get("level")


        # -------------------------------------------------
        # Level 0
        # -------------------------------------------------

        if level_number == 0:

            for process in level.get(
                "processes",
                []
            ):

                # Level 0 must have no parent
                process["parent_process"] = None


        # -------------------------------------------------
        # Level 1
        # -------------------------------------------------

        elif level_number == 1:

            for process in level.get(
                "processes",
                []
            ):

                # If Gemini forgot the parent,
                # use P0 as the Level 0 parent.

                if not process.get(
                    "parent_process"
                ):

                    process["parent_process"] = "P0"


        # -------------------------------------------------
        # Level 2+
        # -------------------------------------------------

        elif level_number >= 2:

            expanded_process = level.get(
                "expanded_process"
            )

            for process in level.get(
                "processes",
                []
            ):

                if not process.get(
                    "parent_process"
                ):

                    # Try to determine parent from ID.
                    #
                    # Example:
                    # P3.1 -> P3

                    process_id = process.get(
                        "id",
                        ""
                    )

                    if "." in process_id:

                        process["parent_process"] = (
                            process_id.rsplit(
                                ".",
                                1
                            )[0]
                        )

                    elif expanded_process:

                        process["parent_process"] = (
                            expanded_process
                        )

                    else:

                        process["parent_process"] = ""


        # -------------------------------------------------
        # expanded_process
        # -------------------------------------------------

        if (
            level_number >= 2
            and not level.get("expanded_process")
        ):

            # Try to identify the parent from
            # the first Level 2 process.

            processes = level.get(
                "processes",
                []
            )

            if processes:

                parent = processes[0].get(
                    "parent_process"
                )

                if parent:

                    level["expanded_process"] = parent


        # -------------------------------------------------
        # Remove empty expanded_process from Level 0/1
        # -------------------------------------------------

        if level_number < 2:

            level.pop(
                "expanded_process",
                None
            )


    # =====================================================
    # 3. Normalize metadata
    # =====================================================

    metadata = data.get(
        "metadata"
    )

    if not isinstance(
        metadata,
        dict
    ):

        metadata = {}

        data["metadata"] = metadata


    metadata["created_from"] = "image"


    if not isinstance(
        metadata.get("confidence"),
        (int, float)
    ):

        metadata["confidence"] = 0.0


    if metadata.get("notes") is None:

        metadata["notes"] = ""


    return data


# =========================================================
# VALIDATE DFD
# =========================================================

def validate_dfd(
    data: dict
) -> list[str]:

    errors = []


    # -----------------------------------------------------
    # Normalize first
    # -----------------------------------------------------

    data = normalize_dfd(
        data
    )


    # -----------------------------------------------------
    # Full JSON Schema validation
    # -----------------------------------------------------

    validator = Draft202012Validator(
        SCHEMA
    )

    for error in validator.iter_errors(
        data
    ):

        path = ".".join(
            str(x)
            for x in error.absolute_path
        )

        if not path:

            path = "root"

        errors.append(
            f"{path}: {error.message}"
        )


    # -----------------------------------------------------
    # DFD Relationship Validation
    # -----------------------------------------------------

    for level in data.get(
        "levels",
        []
    ):

        level_number = level.get(
            "level"
        )


        # -------------------------------------------------
        # Collect IDs
        # -------------------------------------------------

        node_ids = set()


        for group in [
            "external_entities",
            "processes",
            "data_stores"
        ]:

            for obj in level.get(
                group,
                []
            ):

                obj_id = obj.get(
                    "id"
                )

                if not obj_id:

                    errors.append(
                        f"Level {level_number}: "
                        f"object is missing an ID."
                    )

                    continue


                if obj_id in node_ids:

                    errors.append(
                        f"Level {level_number}: "
                        f"duplicate ID '{obj_id}'."
                    )

                node_ids.add(
                    obj_id
                )


        # -------------------------------------------------
        # Validate Data Flows
        # -------------------------------------------------

        for flow in level.get(
            "data_flows",
            []
        ):

            flow_id = flow.get(
                "id"
            )

            source = flow.get(
                "source"
            )

            destination = flow.get(
                "destination"
            )


            if source not in node_ids:

                errors.append(
                    f"Level {level_number}: "
                    f"flow '{flow_id}' has "
                    f"invalid source '{source}'."
                )


            if destination not in node_ids:

                errors.append(
                    f"Level {level_number}: "
                    f"flow '{flow_id}' has "
                    f"invalid destination "
                    f"'{destination}'."
                )


        # -------------------------------------------------
        # Validate Parent Processes
        # -------------------------------------------------

        process_ids = {

            process.get("id")

            for process in level.get(
                "processes",
                []
            )

        }


        for process in level.get(
            "processes",
            []
        ):

            parent = process.get(
                "parent_process"
            )


            if parent is not None and parent != "":

                # Parent can exist in a previous level,
                # so only perform a basic ID check.

                if not parent.startswith(
                    "P"
                ):

                    errors.append(
                        f"Level {level_number}: "
                        f"invalid parent process "
                        f"'{parent}'."
                    )


        # -------------------------------------------------
        # Validate Expanded Process
        # -------------------------------------------------

        expanded = level.get(
            "expanded_process"
        )


        if expanded:

            if not expanded.startswith(
                "P"
            ):

                errors.append(
                    f"Level {level_number}: "
                    f"invalid expanded process "
                    f"'{expanded}'."
                )


    return errors