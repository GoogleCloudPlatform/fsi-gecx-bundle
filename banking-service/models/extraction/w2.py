# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pydantic import BaseModel, Field
from .wrapper import ExtractionWrapper

class W2Extraction(BaseModel):
    employer_name: ExtractionWrapper[str] = Field(..., description="Employer's name, address, and ZIP code.")
    employee_social_security_number: ExtractionWrapper[str] = Field(..., description="Employee's social security number (Box a).")
    wages_tips_other_comp: ExtractionWrapper[float] = Field(..., description="Wages, tips, other compensation (Box 1).")
    social_security_wages: ExtractionWrapper[float] = Field(..., description="Social security wages (Box 3).")
    medicare_wages_and_tips: ExtractionWrapper[float] = Field(..., description="Medicare wages and tips (Box 5).")
