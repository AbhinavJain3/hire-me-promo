"""Validate payloads against component schemas in contracts/openapi/*.yaml (cross-file $refs resolve)."""
from __future__ import annotations

from functools import lru_cache

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from engage.contract.catalog import CONTRACTS_DIR

OPENAPI_DIR = CONTRACTS_DIR / "openapi"


@lru_cache(maxsize=1)
def registry() -> Registry:
    reg = Registry()
    for path in sorted(OPENAPI_DIR.glob("*.yaml")):
        reg = reg.with_resource(path.resolve().as_uri(),
                                Resource(contents=yaml.safe_load(path.read_text()), specification=DRAFT202012))
    return reg


@lru_cache(maxsize=None)
def validator(file: str, schema: str) -> Draft202012Validator:
    """validator("promo-api.v1.yaml", "PromoCreate")"""
    uri = (OPENAPI_DIR / file).resolve().as_uri()
    return Draft202012Validator({"$ref": f"{uri}#/components/schemas/{schema}"}, registry=registry())


def errors(file: str, schema: str, value) -> list[str]:
    out = []
    for e in sorted(validator(file, schema).iter_errors(value), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in e.absolute_path) or "(root)"
        out.append(f"{where}: {e.message[:200]}")
    return out
