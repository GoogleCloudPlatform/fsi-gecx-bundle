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

FROM python:3.13-slim

# Setup security group and user
RUN groupadd -g 10001 appgroup && \
    useradd -r -u 10001 -g appgroup appuser

# Copy banking-service to keep same relative structure
COPY banking-service/ /app/banking-service/

# Copy voice agent package
COPY adk-agent/credit-support-agent/ /app/adk-agent/credit-support-agent/

WORKDIR /app/adk-agent/credit-support-agent

# Install minimal build essentials, then clean up cache to minimize image size
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install CPU-only PyTorch and Torchaudio to prevent CUDA dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# Install remaining dependencies
RUN pip install --no-cache-dir .

# Ensure the appuser owns the runtime files
RUN chown -R appuser:appgroup /app

# Switch to low-privilege user
USER appuser

ENTRYPOINT ["python", "voice_agent.py"]
