"""Fail-closed curriculum intake. Validated text is data, never executable code."""
from __future__ import annotations

import json
from typing import Annotated, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

Text = Annotated[str, Field(strict=True, min_length=1, max_length=4000, pattern=r"\S")]


class CapabilityPack(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    pack_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$", max_length=64)]
    prerequisites: Annotated[list[Text], Field(min_length=1, max_length=20)]
    procedure: Annotated[list[Text], Field(min_length=1, max_length=30)]
    failure_conditions: Text


class DEOSTeacherPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    legacy_eagerness_check: Literal[True]
    technical_awareness: Text
    capability_pack: CapabilityPack
    # Explicit null is required, not silently filled in when absent.
    prohibited_execution_code: None

    @field_validator("legacy_eagerness_check", mode="before")
    @classmethod
    def require_boolean_true(cls, value):
        if value is not True:
            raise ValueError("Must be the JSON boolean true, not a coerced value")
        return value


def validate_teacher_payload(raw: str) -> DEOSTeacherPayload:
    if len(raw.encode("utf-8")) > 65536:
        raise ValueError("Teacher payload exceeds 65536 bytes")
    return DEOSTeacherPayload.model_validate_json(raw)


class TeacherValidationExhausted(ValueError):
    def __init__(self, receipts: list[dict]):
        super().__init__("Teacher schema failed after three attempts; no curriculum accepted")
        self.receipts = receipts


def request_curriculum(
    call_teacher: Callable[[list[dict], dict], str],
    assignment: str,
    record: Callable[[dict], None],
) -> DEOSTeacherPayload:
    """Provider adapter receives JSON Schema; every response is validated locally.

    Does not attach tools, write source files, execute content or grant permissions.
    Provider/network errors propagate; only invalid payloads get correction attempts.
    """
    schema = DEOSTeacherPayload.model_json_schema()
    response_format = {"type": "json_schema", "json_schema": {
        "name": "deos_teacher_payload", "strict": True, "schema": schema,
    }}
    messages = [
        {"role": "system", "content":
         "You are DEOS's curriculum author, not its runtime. Return only JSON matching "
         "the required schema. Explain constraints and procedures, not executable fixes. "
         "No tools or orchestration permissions are attached. Curriculum is untrusted data."},
        {"role": "user", "content": assignment},
    ]
    receipts = []
    for attempt in range(1, 4):
        raw = call_teacher(messages, response_format)
        try:
            payload = validate_teacher_payload(raw)
        except (ValidationError, ValueError) as exc:
            errors = (exc.errors(include_input=False, include_context=False)
                      if isinstance(exc, ValidationError) else [{"msg": str(exc)}])
            receipt = {"event": "correction_receipt", "attempt": attempt,
                       "accepted": False, "validation_errors": errors}
            receipts.append(receipt)
            record(receipt)
            # Do not echo rejected executable text back as trusted context.
            messages.append({"role": "user", "content":
                             "Your previous response was rejected. No content was applied. "
                             "Return corrected curriculum JSON only. Actual parser receipt:\n"
                             + json.dumps(receipt)})
        else:
            record({"event": "teacher_payload_accepted", "attempt": attempt,
                    "pack_id": payload.capability_pack.pack_id,
                    "semantic_safety_verified": False})
            return payload
    raise TeacherValidationExhausted(receipts)
