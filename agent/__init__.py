#
# Copyright (c) nexB Inc. and others. All rights reserved.
# VulnerableCode.ai is a trademark of nexB Inc.
# SPDX-License-Identifier: Apache-2.0
# See http://www.apache.org/licenses/LICENSE-2.0 for the license text.
# See https://github.com/aboutcode-org/vulnerablecode for support or download.
# See https://aboutcode.org for more information about nexB OSS projects.
#

import os
from typing import List
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from univers.version_range import RANGE_CLASS_BY_SCHEMES

from packageurl import PackageURL
from pydantic.functional_validators import field_validator
from dotenv import load_dotenv

load_dotenv()

OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME")

class Purl(BaseModel):
    string: str

    @field_validator('string')
    def check_valid_purl(cls, v: str) -> str:
        try:
            PackageURL.from_string(v)
        except Exception as e:
            raise ValueError(f"Invalid PURL '{v}': {e}")
        return v

class Versions(BaseModel):
    affected_versions: List[str]
    fixed_versions:   List[str]


prompt_purl_from_summary = f"""
You are a highly specialized Vulnerability Analysis Assistant. Your task is to analyze the provided vulnerability summary or package name and extract a single valid Package URL (PURL) that conforms to the official PURL specification:

**Component Definitions (Required by PURL Specification):**
- **scheme**: Constant value `pkg`
- **type**: Package type or protocol (e.g., maven, npm, nuget, gem, pypi, rpm, etc.) — must be a known valid type
- **namespace**: A name prefix such as a Maven groupId, Docker image owner, or GitHub user/org (optional and type-specific)
- **name**: Package name (required)
- **version**: Version of the package (optional)
- **qualifiers**: Extra data like OS, arch, etc. (optional and type-specific)
- **subpath**: Subpath within the package (optional)

**Output Instructions:**
- Identify the most appropriate and valid PURL type for the package if possible.
- If a valid and complete PURL can be constructed, return only:
  `{{ "string": "pkg:type/namespace/name@version?qualifiers#subpath" }}`
- If no valid PURL can be constructed or the type is unknown, return:
  `{{}}`
- Do not include any other output (no explanation, formatting, or markdown).

please don't Hallucinate
"""

prompt_version_from_summary = f"""
        You are a highly specialized Vulnerability Analysis Assistant. Your task is to analyze the following vulnerability summary and accurately extract the affected and fixed versions of the software.
        
        Instructions:
        - Affected Version: Use one of the following formats:
          - >= <version>, <= <version>, > <version>, < <version>
          - A specific range like <version1> - <version2>
        - Fixed Version: Use one of the following formats:
          - >= <version>, <= <version>, > <version>, < <version>
          - "Not Fixed" if no fixed version is mentioned.
        - Ensure accuracy by considering different ways affected and fixed versions might be described in the summary.
        - Extract only version-related details without adding any extra information.
        
        Output Format:
        ```json
        {{
            "affected_versions": ["<version_condition>", "<version_condition>"],
            "fixed_versions": ["<version_condition>", "<version_condition>"]
        }}
        ```
        Example:
        {{
            "affected_versions": [">=1.2.3", "<2.0.0"],
            "fixed_versions": ["2.0.0"]
        }}
        
        Return only the JSON object without any additional text.
        """

prompt_purl_from_cpe = f"""
You are a specialized Vulnerability Analysis Assistant. Your task is to analyze the provided vulnerability CPE or Known Affected Software Configurations and extract a single, valid Package URL (PURL) that strictly conforms to the official PURL specification.

**PURL Format:**  
pkg:type/namespace/name@version

- **type**: The package type (e.g., maven, npm, pypi, gem, nuget, rpm, deb, docker, etc.)
- **namespace**: The namespace, organization, or group (optional, use only if present and verifiable)
- **name**: The package name
- **version**: The package version (if available)

**Instructions:**
- Use only verifiable, extractable data from the CPE or software configuration input.
- Construct the most accurate PURL string based on the input.
- The PURL must be syntactically valid and follow the required format.
- Output only:
  {{ "string": "pkg:type/namespace/name@version" }}
- If a valid PURL cannot be reliably generated, output: {{}}
- Do not provide explanations, additional text, or markdown formatting.
- Do not assume or hallucinate any values.

"""


class VulnerabilitySummaryParser:
    def __init__(self):
        if OLLAMA_MODEL_NAME and OLLAMA_BASE_URL:
            self.model = OpenAIModel(
                model_name=OLLAMA_MODEL_NAME,
                provider=OpenAIProvider(openai_client=OLLAMA_BASE_URL)
            )
        else:
            self.model = OpenAIModel(
                model_name=OPENAI_MODEL_NAME,
                provider=OpenAIProvider(api_key=OPENAI_API_KEY),
            )

        self.purl_agent = Agent(self.model,
                           system_prompt=prompt_purl_from_summary,
                           model_settings=ModelSettings(temperature=0, seed=42),
                           output_type=Purl)

        self.versions_agent = Agent(self.model,
                               system_prompt=prompt_version_from_summary,
                               model_settings=ModelSettings(temperature=0, seed=42),
                               output_type=Versions)

    def get_version_ranges(self, summary, supported_ecosystem):
        """Extract affected and fixed version ranges from a vulnerability summary."""
        result = self.versions_agent.run_sync(user_prompt=f"""
        **Vulnerability Summary:**
        {summary}
        """)

        affected_version_ranges = result.output.affected_versions
        fixed_version_ranges = result.output.fixed_versions

        affected_version_objs = [RANGE_CLASS_BY_SCHEMES[supported_ecosystem].from_string(f"vers:{supported_ecosystem}/" + affected_version_range) for affected_version_range in affected_version_ranges]
        fixed_version_objs = [RANGE_CLASS_BY_SCHEMES[supported_ecosystem].from_string(f"vers:{supported_ecosystem}/" + fixed_version_version_range) for fixed_version_version_range in fixed_version_ranges]
        return affected_version_objs, fixed_version_objs


    def get_purl(self, summary):
        """
        Analyze the vulnerability summary and extract a valid Package URL (PURL).
        Returns the extracted PURL string or None if not found.
        """
        result = self.purl_agent.run_sync(user_prompt=f"""
        **Vulnerability Summary:**
        {summary}
        """)
        return PackageURL.from_string(result.output.string)


class CPEParser:
    def __init__(self):
        if OLLAMA_MODEL_NAME and OLLAMA_BASE_URL:
            self.model = OpenAIModel(
                model_name=OLLAMA_MODEL_NAME,
                provider=OpenAIProvider(openai_client=OLLAMA_BASE_URL)
            )
        else:
            self.model = OpenAIModel(
                model_name=OPENAI_MODEL_NAME,
                provider=OpenAIProvider(api_key=OPENAI_API_KEY),
            )

        self.purl_agent = Agent(self.model,
                           system_prompt=prompt_purl_from_cpe,
                           model_settings=ModelSettings(temperature=0, seed=42),
                           output_type=Purl)

    def get_purl(self, cpe):
        """
        Analyze the vulnerability summary and extract a valid Package URL (PURL).
        Returns the extracted PURL string or None if not found.
        """
        result = self.purl_agent.run_sync(user_prompt=f"""
        **Vulnerability Known Affected Software Configurations CPE:**
        {cpe}
        """)
        return PackageURL.from_string(result.output.string)