"""Pydantic schema for a machine's knowledge.yaml file.

This is the single source of truth for the shape of machine knowledge data.
It is imported by the validator, build_index.py, and the MCP server itself,
so there is exactly one place that defines what a valid knowledge file looks like.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator, model_validator

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class MachineMeta(BaseModel):
    slug: str
    brand: str
    model: str
    aliases: list[str] = Field(default_factory=list)
    manual_pdf: str
    manual_version: str | None = None
    source_pages: int | None = None
    notes: str | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError(
                f"slug {v!r} must be lowercase alphanumeric with hyphens, e.g. 'pfaff-quilt-expression-720'"
            )
        return v


class SpecItem(BaseModel):
    label: str
    value: str
    category: str | None = None


class Setting(BaseModel):
    number: int
    title: str
    page: int | None = None
    description: str
    spec: str | None = None
    service_menu_path: str | None = None
    related_settings: list[int] = Field(default_factory=list)


class TouchArea(BaseModel):
    label: str
    description: str
    check_procedure: str | None = None


class Submenu(BaseModel):
    letter: str
    name: str
    touch_areas: list[TouchArea] = Field(default_factory=list)


class Menu(BaseModel):
    number: int
    name: str
    submenus: list[Submenu] = Field(default_factory=list)

    @field_validator("submenus")
    @classmethod
    def unique_letters(cls, v: list[Submenu]) -> list[Submenu]:
        letters = [s.letter for s in v]
        if len(letters) != len(set(letters)):
            raise ValueError(f"duplicate submenu letters in menu: {letters}")
        return v


class ServiceProgram(BaseModel):
    menus: list[Menu] = Field(default_factory=list)

    @field_validator("menus")
    @classmethod
    def unique_menu_numbers(cls, v: list[Menu]) -> list[Menu]:
        numbers = [m.number for m in v]
        if len(numbers) != len(set(numbers)):
            raise ValueError(f"duplicate menu numbers: {numbers}")
        return v


class DisassemblyProcedure(BaseModel):
    component: str
    page: int | None = None
    tools_needed: list[str] = Field(default_factory=list)
    dismantle_steps: list[str] = Field(default_factory=list)
    mount_steps: list[str] = Field(default_factory=list)
    settings_to_recheck: list[int] = Field(default_factory=list)


class FaultFindingEntry(BaseModel):
    symptom: str
    checks: list[str] = Field(default_factory=list)
    replace_order: list[str] = Field(default_factory=list)
    notes: str | None = None


class MachineKnowledge(BaseModel):
    schema_version: int
    machine: MachineMeta
    specifications: list[SpecItem] = Field(default_factory=list)
    settings: list[Setting] = Field(default_factory=list)
    service_program: ServiceProgram = Field(default_factory=ServiceProgram)
    disassembly: list[DisassemblyProcedure] = Field(default_factory=list)
    fault_finding: list[FaultFindingEntry] = Field(default_factory=list)

    @field_validator("settings")
    @classmethod
    def unique_setting_numbers(cls, v: list[Setting]) -> list[Setting]:
        numbers = [s.number for s in v]
        if len(numbers) != len(set(numbers)):
            raise ValueError(f"duplicate setting numbers: {numbers}")
        return v

    @model_validator(mode="after")
    def cross_references_resolve(self) -> "MachineKnowledge":
        known_numbers = {s.number for s in self.settings}
        for setting in self.settings:
            for ref in setting.related_settings:
                if ref not in known_numbers:
                    raise ValueError(
                        f"setting {setting.number} ({setting.title!r}) references "
                        f"unknown related_settings number {ref}"
                    )
        for proc in self.disassembly:
            for ref in proc.settings_to_recheck:
                if ref not in known_numbers:
                    raise ValueError(
                        f"disassembly component {proc.component!r} references "
                        f"unknown settings_to_recheck number {ref}"
                    )
        return self
