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

from utils.database import create_db_engine


def test_shared_memory_schema_attachments_do_not_create_literal_files(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    engine = create_db_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")
    engine.dispose()

    assert list(tmp_path.glob("file:*mode=memory*cache=shared*")) == []
