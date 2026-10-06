from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class DataStrategy(ABC):
    """Strategy interface for data synthesis by field type."""

    @abstractmethod
    def positive(self, field_name: str, scenario_id: str) -> List[Any]:
        raise NotImplementedError

    @abstractmethod
    def negative(self, field_name: str, scenario_id: str) -> List[Any]:
        raise NotImplementedError

    @abstractmethod
    def boundary(self, field_name: str, scenario_id: str) -> List[Any]:
        raise NotImplementedError

    @abstractmethod
    def validation(self, field_name: str, scenario_id: str) -> List[Any]:
        raise NotImplementedError


@dataclass
class TextStrategy(DataStrategy):
    def positive(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["John", "Michael"]

    def negative(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", "@@@@@"]

    def boundary(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["A", "ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMNOPQRSTUVWXYZ"]

    def validation(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", " ", " John", "John ", "@@@@@", "<script>alert('test')</script>"]


@dataclass
class EmailStrategy(DataStrategy):
    def positive(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["john.doe@example.com", "michael@example.org"]

    def negative(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["not-an-email", "john@@example.com"]

    def boundary(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["a" * 64 + "@example.com", "b" * 63 + "@example.org"]

    def validation(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", "user@", "@gmail.com", "user@@gmail.com", "user gmail.com"]


@dataclass
class PasswordStrategy(DataStrategy):
    def positive(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["StrongPass123!", "ComplexPassword#456"]

    def negative(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["123", "password"]

    def boundary(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["Abc123!", "LongPasswordWithMinimumEightChars1!"]

    def validation(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", "   "]


@dataclass
class NumberStrategy(DataStrategy):
    def positive(self, field_name: str, scenario_id: str) -> List[Any]:
        return [24, 56]

    def negative(self, field_name: str, scenario_id: str) -> List[Any]:
        return [-1, 999999999999999]

    def boundary(self, field_name: str, scenario_id: str) -> List[Any]:
        return [0, 1000000]

    def validation(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["abc", "-"]


@dataclass
class DateStrategy(DataStrategy):
    def positive(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["2026-08-11", "2026-01-31"]

    def negative(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["2026-13-99", "2026-08-32"]

    def boundary(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["1900-01-01", "9999-12-31"]

    def validation(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", "32/13/2025", "invalid-date"]


@dataclass
class PhoneStrategy(DataStrategy):
    def positive(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["9876543210", "9123456789"]

    def negative(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["12345", "abcdefghij"]

    def boundary(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["0000000000", "9999999999"]

    def validation(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", "abcdefghij", "123abc", "123", "123456789012345"]


@dataclass
class RadioStrategy(DataStrategy):
    def positive(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["option_a", "option_b"]

    def negative(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", "unknown_option"]

    def boundary(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["option_a"]

    def validation(self, field_name: str, scenario_id: str) -> List[Any]:
        return [None]


@dataclass
class CheckboxStrategy(DataStrategy):
    def positive(self, field_name: str, scenario_id: str) -> List[Any]:
        return [True]

    def negative(self, field_name: str, scenario_id: str) -> List[Any]:
        return [False]

    def boundary(self, field_name: str, scenario_id: str) -> List[Any]:
        return [False, True]

    def validation(self, field_name: str, scenario_id: str) -> List[Any]:
        return [None]


@dataclass
class FileStrategy(DataStrategy):
    def positive(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["document.pdf", "avatar.png"]

    def negative(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["executable.exe", "invoice.txt"]

    def boundary(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["large_document.pdf", "10MB_limit_file.pdf"]

    def validation(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", "virus.exe", "largefile.zip"]


@dataclass
class UrlStrategy(DataStrategy):
    def positive(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["https://example.com", "https://www.test.com/path"]

    def negative(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["htp:/invalid", "www.example"]

    def boundary(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["https://" + "a" * 200 + ".example.com", "https://example.com/" + "a" * 200]

    def validation(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", "not a url"]


@dataclass
class TextAreaStrategy(DataStrategy):
    def positive(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["This is a detailed description of the product.", "Additional notes and comments go here."]

    def negative(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", "@@@@@@@@@@@@@"]

    def boundary(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["A", "A" * 500 + "\nMultiple lines of text\nspanning several rows"]

    def validation(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", "   ", "<script>alert('test')</script>", "\n\n", "Special chars: @#$%^&*()"]


@dataclass
class AddressStrategy(DataStrategy):
    def positive(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["123 Main Street, Springfield, IL 62701", "456 Oak Avenue, Chicago, IL 60601"]

    def negative(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", "Invalid Address!@#$"]

    def boundary(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["1", "999999 Very Long Street Name With Many Words That Spans A Very Long Distance, Very Long City Name, Very Long State 99999"]

    def validation(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", "   ", "123", "@@@", "<script>alert('test')</script>"]


@dataclass
class MultilineStrategy(DataStrategy):
    def positive(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["Line one\nLine two\nLine three", "Multi-line\ntext\ninput\nhere"]

    def negative(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", "@@@@@"]

    def boundary(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["A", "A" * 200 + "\n" + "B" * 200]

    def validation(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", "   ", "<script>alert('test')</script>"]


@dataclass
class GenderStrategy(DataStrategy):
    def positive(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["Male", "Female", "Other"]

    def negative(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", "Unknown"]

    def boundary(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["Other"]

    def validation(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", "Invalid gender"]


@dataclass
class DropdownStrategy(DataStrategy):
    def positive(self, field_name: str, scenario_id: str) -> List[Any]:
        normalized_name = str(field_name or "").lower()
        if "state" in normalized_name:
            return ["NCR", "Uttar Pradesh", "Haryana", "Rajasthan"]
        if "city" in normalized_name:
            return ["Delhi", "Gurgaon", "Noida", "Agra"]
        if "country" in normalized_name:
            return ["India", "United States", "United Kingdom"]
        return ["Option 1", "Option 2"]

    def negative(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", "Invalid option"]

    def boundary(self, field_name: str, scenario_id: str) -> List[Any]:
        normalized_name = str(field_name or "").lower()
        if "state" in normalized_name:
            return ["NCR"]
        if "city" in normalized_name:
            return ["Delhi"]
        if "country" in normalized_name:
            return ["India"]
        return ["Option 1"]

    def validation(self, field_name: str, scenario_id: str) -> List[Any]:
        return ["", "Invalid option"]


FIELD_STRATEGIES = {
    "text": TextStrategy(),
    "email": EmailStrategy(),
    "password": PasswordStrategy(),
    "number": NumberStrategy(),
    "date": DateStrategy(),
    "phone": PhoneStrategy(),
    "phone_number": PhoneStrategy(),
    "radio": RadioStrategy(),
    "gender": GenderStrategy(),
    "checkbox": CheckboxStrategy(),
    "file": FileStrategy(),
    "url": UrlStrategy(),
    "search": TextStrategy(),
    "username": TextStrategy(),
    "dropdown": DropdownStrategy(),
    "select": DropdownStrategy(),
    "textarea": TextAreaStrategy(),
    "address": AddressStrategy(),
    "multiline": MultilineStrategy(),
}


class TestDataRulesEngine:
    """Strategy-based rules engine for Agent 2 test-data synthesis."""

    def __init__(self, strategies: Optional[Dict[str, DataStrategy]] = None):
        self.strategies = strategies or FIELD_STRATEGIES

    def generate_for_field(self, field_type: str, field_name: str, scenario_id: str) -> Dict[str, List[Any]]:
        key = str(field_type or "text").strip().lower()
        key = {
            "phone_number": "phone",
            "phone": "phone",
            "email": "email",
            "username": "text",
            "search": "text",
            "text": "text",
            "textarea": "textarea",
            "address": "address",
            "multiline": "multiline",
            "password": "password",
            "number": "number",
            "date": "date",
            "url": "url",
            "radio": "radio",
            "gender": "gender",
            "checkbox": "checkbox",
            "file": "file",
            "dropdown": "dropdown",
            "select": "dropdown",
        }.get(key, key)

        # Use the field name as a final safeguard when upstream metadata is
        # generic or incorrect.
        normalized_name = str(field_name or "").strip().lower()
        if "email" in normalized_name:
            key = "email"
        elif any(token in normalized_name for token in ("mobile", "phone", "telephone")):
            key = "phone"
        elif "gender" in normalized_name or normalized_name == "sex":
            key = "gender"
        elif any(token in normalized_name for token in ("state", "city", "country")):
            key = "dropdown"

        if key == "radio" and "gender" in str(field_name or "").lower():
            strategy = self.strategies.get("gender")
        else:
            strategy = self.strategies.get(key)
        if strategy is None:
            strategy = TextStrategy()

        return {
            "positive": strategy.positive(field_name, scenario_id),
            "negative": strategy.negative(field_name, scenario_id),
            "boundary": strategy.boundary(field_name, scenario_id),
            "validation": strategy.validation(field_name, scenario_id),
        }

    def generate_many(self, scenario_id: str, field_specs: List[Dict[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "scenario_id": scenario_id,
            "generated_data": {
                "positive": {},
                "negative": {},
                "boundary": {},
                "validation": {},
            },
        }

        for spec in field_specs:
            if not isinstance(spec, dict):
                continue
            field_name = str(spec.get("field_name") or spec.get("name") or "target_field").strip()
            field_type = str(spec.get("field_type") or spec.get("type") or "text").strip().lower()
            if not field_name:
                continue
            bundle = self.generate_for_field(field_type, field_name, scenario_id)
            result["generated_data"]["positive"][field_name] = bundle["positive"]
            result["generated_data"]["negative"][field_name] = bundle["negative"]
            result["generated_data"]["boundary"][field_name] = bundle["boundary"]
            result["generated_data"]["validation"][field_name] = bundle["validation"]

        return result
