"""Agent 2 Pydantic domain layer.

This package owns Agent 2's public contract and normalization types so the service
layer and API handlers can work with stable, schema-validated data objects.
"""

from .schemas import (
    Agent2DataSet,
    Agent2GeneratedDataBundle,
    Agent2GeneratedDataValue,
    Agent2GenerationRequest,
    Agent2GenerationResponse,
    Agent2ScenarioInput,
    Agent2ScenarioOutput,
    Agent2TestDataPayload,
)

__all__ = [
    "Agent2DataSet",
    "Agent2GeneratedDataBundle",
    "Agent2GeneratedDataValue",
    "Agent2GenerationRequest",
    "Agent2GenerationResponse",
    "Agent2ScenarioInput",
    "Agent2ScenarioOutput",
    "Agent2TestDataPayload",
]
