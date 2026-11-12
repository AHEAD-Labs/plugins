"""Authored release manifest (Git) — validated by the common checks."""
import re
from typing import Literal

import yaml
from pydantic import BaseModel, field_validator, model_validator


class Owner(BaseModel):
    team: str
    contact: str


class Auth(BaseModel):
    type: Literal["os-user", "oauth2-bearer"]
    issuer: str | None = None
    audience: str | None = None
    scopes: list[str] = []


class Package(BaseModel):
    type: Literal["python-wheel"]
    entrypoint: str


class Deployment(BaseModel):
    id: str
    transport: Literal["stdio", "streamable-http"]
    package: Package | None = None
    endpoint: str | None = None
    auth: Auth

    @model_validator(mode="after")
    def _shape(self):
        if self.transport == "stdio" and not self.package:
            raise ValueError("stdio deployment needs a package")
        if self.transport == "streamable-http" and not self.endpoint:
            raise ValueError("streamable-http deployment needs an endpoint")
        return self


class Manifest(BaseModel):
    capability_id: str
    python_package: str
    name: str
    description: str
    owner: Owner
    version: str
    audience: list[str]
    classification: Literal["public", "internal", "confidential", "restricted"]
    tools: list[str]
    deployments: list[Deployment]
    distribution: list[Literal["oasis", "openai-codex-plugin"]]

    @field_validator("version")
    @classmethod
    def _semver(cls, v):
        if not re.fullmatch(r"\d+\.\d+\.\d+", v):
            raise ValueError("version must be MAJOR.MINOR.PATCH")
        return v

    def deployment(self, transport: str) -> Deployment:
        return next(d for d in self.deployments if d.transport == transport)


def load(path: str) -> Manifest:
    with open(path) as f:
        return Manifest.model_validate(yaml.safe_load(f))
